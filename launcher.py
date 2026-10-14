import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

HOST = "127.0.0.1"          # adresse utilisée par la fenêtre de ce poste
PORT = 8000
APP_URL = f"http://{HOST}:{PORT}/"
BIND_HOST = HOST            # adresse d'écoute : 0.0.0.0 en mode serveur (réseau local)
SERVER_MODE = False


def app_data_dir():
    if sys.platform == "win32":
        root = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return Path(root) / "KIS Kalanso" / "data"
    return Path.home() / ".kis_kalanso" / "data"


if getattr(sys, "frozen", False):
    data_dir = app_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "media").mkdir(parents=True, exist_ok=True)
    os.environ["KIS_DATA_DIR"] = str(data_dir)
    # Application installée : jamais de mode développement (pages d'erreur
    # techniques, journalisation de toutes les requêtes SQL en mémoire).
    os.environ.setdefault("DJANGO_DEBUG", "0")



def _ensure_std_streams():
    """Fournit stdout/stderr quand l'exécutable est compilé sans console.

    Avec PyInstaller ``console=False``, Windows ne fournit aucune sortie
    standard : ``sys.stdout`` et ``sys.stderr`` valent None et Django plante
    dès sa première écriture (migrate, runserver). On redirige alors ces
    sorties vers un journal dans le dossier de données.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    log_dir = Path(os.environ.get("KIS_DATA_DIR") or app_data_dir())
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log = open(log_dir / "kis_kalanso.log", "a", encoding="utf-8", buffering=1)
    except OSError:
        log = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log


_ensure_std_streams()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.management import execute_from_command_line


def find_app_browser():
    """Cherche un navigateur Chromium capable du mode application (--app).

    Microsoft Edge est présent sur tous les Windows 10/11 ; Chrome est utilisé
    en priorité s'il est installé. Retourne le chemin de l'exécutable ou None.
    """
    if sys.platform != "win32":
        return None
    roots = [
        os.environ.get("PROGRAMFILES", r"C:\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    relatives = [
        r"Google\Chrome\Application\chrome.exe",
        r"Microsoft\Edge\Application\msedge.exe",
    ]
    for relative in relatives:
        for root in roots:
            if not root:
                continue
            candidate = Path(root) / relative
            if candidate.exists():
                return str(candidate)
    return None


def browser_profile_dir():
    """Profil navigateur propre à KIS Kalanso.

    Un profil dédié garantit une fenêtre indépendante du navigateur personnel
    de l'utilisateur (pas d'onglets, pas de barre d'adresse, pas d'extensions)
    et permet de savoir quand la fenêtre de l'application est fermée.
    """
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    path = Path(base) / "KIS Kalanso" / "browser_profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def wait_for_server(timeout=60):
    """Attend que le serveur local réponde (au lieu d'une pause fixe)."""
    import socket

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def open_app_window():
    """Ouvre l'interface dans une fenêtre d'application, sans barre du navigateur.

    Si aucun navigateur compatible n'est trouvé, on retombe sur le navigateur
    par défaut (comportement historique).
    """
    wait_for_server()
    browser = find_app_browser()
    if not browser:
        webbrowser.open(APP_URL)
        return

    args = [
        browser,
        f"--app={APP_URL}",
        f"--user-data-dir={browser_profile_dir()}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate",
        "--window-size=1366,860",
    ]
    try:
        started = time.monotonic()
        process = subprocess.Popen(args)
    except OSError:
        webbrowser.open(APP_URL)
        return

    # Fermer la fenêtre de l'application arrête le serveur local : à la
    # prochaine ouverture, tout redémarre proprement (et la session est
    # purgée, voir clear_sessions). Si le navigateur rend la main presque
    # immédiatement (fenêtre déjà ouverte avec ce profil), on ne coupe rien.
    process.wait()
    if time.monotonic() - started > 8 and not SERVER_MODE:
        # En mode serveur (réseau local), les autres postes restent connectés :
        # fermer la fenêtre de ce poste n'arrête pas KIS Kalanso.
        shutdown_cleanly()
        os._exit(0)


def shutdown_cleanly():
    """Fermeture normale : la base est remise d'aplomb (voir common.db_guard)."""
    try:
        from django.conf import settings
        from common.db_guard import checkpoint_on_exit
        checkpoint_on_exit(settings.DATABASES["default"]["NAME"])
    except Exception:
        pass


def _app_migration_names():
    """Migrations livrées avec l'application, lues sur le disque (sans Django)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    names = set()
    for app in ("administration", "common", "communication", "documents", "finance",
                "pedagogie", "pilotage", "vie_scolaire"):
        folder = base / app / "migrations"
        if not folder.is_dir():
            continue
        for entry in folder.iterdir():
            if entry.suffix in (".py", ".pyc") and entry.stem[:4].isdigit():
                names.add((app, entry.stem))
    return names


def migrations_needed(db_path):
    """Vrai si la base n'a pas encore toutes les migrations de l'application.

    ``migrate`` charge tout le graphe des migrations et relance les contrôles
    système : 2 à 4 s perdues à CHAQUE démarrage alors qu'il n'y a presque
    jamais rien à appliquer. On compare donc directement la table
    django_migrations aux fichiers livrés, plus la version de Django (pour
    ses propres migrations). En cas de doute, on migre.
    """
    import sqlite3

    import django

    db_path = Path(db_path)
    if not db_path.exists():
        return True
    expected = _app_migration_names()
    if not expected:
        return True
    marker = db_path.with_name(".kis_migrations")
    signature = f"django={django.__version__};count={len(expected)}"
    try:
        if marker.read_text(encoding="utf-8") != signature:
            return True
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
            applied = set(connection.execute("SELECT app, name FROM django_migrations"))
    except (OSError, sqlite3.Error):
        return True
    return not expected <= applied


def remember_migrations(db_path):
    import django

    marker = Path(db_path).with_name(".kis_migrations")
    try:
        marker.write_text(f"django={django.__version__};count={len(_app_migration_names())}", encoding="utf-8")
    except OSError:
        pass


def serve():
    """Serveur local. Waitress (multi-threads, sans contrôles de développement)
    s'il est disponible, sinon le serveur de développement de Django."""
    try:
        from waitress import serve as waitress_serve
    except ImportError:
        execute_from_command_line(["manage.py", "runserver", f"{BIND_HOST}:{PORT}", "--noreload", "--skip-checks"])
        return
    from django.core.wsgi import get_wsgi_application

    waitress_serve(get_wsgi_application(), host=BIND_HOST, port=PORT, threads=16 if SERVER_MODE else 8, ident="KIS Kalanso")


def clear_sessions():
    """Force la déconnexion de tout le monde à chaque lancement de l'application.

    KIS Kalanso distingue plusieurs rôles utilisateurs. Sans cette purge, une
    session pourrait rester valable d'un lancement à l'autre (navigateur qui
    restaure l'onglet précédent, ordinateur non éteint, etc.) : la prochaine
    personne à ouvrir l'application reprendrait alors la session — et donc les
    droits — du dernier utilisateur connecté, ce qui viderait la distinction
    des rôles de son sens. Fermer l'application doit donc toujours entraîner
    une reconnexion au prochain lancement.
    """
    try:
        from django.contrib.sessions.models import Session
        Session.objects.all().delete()
    except Exception:
        # La base peut ne pas encore exister au tout premier lancement
        # (avant la première migration) : ce n'est pas bloquant.
        pass


def safe_backup():
    try:
        from common.backup import AUTO, create_backup
        create_backup(AUTO)
    except Exception as exc:
        print(f"[KIS Kalanso] Sauvegarde avant mise à jour impossible : {exc}")


def repair_database(db_path):
    try:
        from django.db import connections
        from common.db_repair import repair_foreign_keys
        connections.close_all()
        fixed = repair_foreign_keys(db_path)
        if fixed:
            print(f"[KIS Kalanso] {fixed} lien(s) cassé(s) réparé(s) avant la mise à jour de la base.")
    except Exception as exc:
        print(f"[KIS Kalanso] Réparation de la base impossible : {exc}")


def start_auto_backup():
    """Sauvegarde automatique à l'ouverture puis toutes les 24 h (voir common.backup)."""
    try:
        from common.backup import start_auto_backup_thread
        start_auto_backup_thread()
    except Exception as exc:
        print(f"[KIS Kalanso] Sauvegarde automatique indisponible : {exc}")


def acquire_single_instance(data_dir):
    """Verrou exclusif sur le dossier de données ; None si une autre instance le tient.

    Sans lui, deux lancements rapprochés (double clic pendant le premier
    démarrage, toujours long sur une base neuve) exécutaient « migrate » en
    même temps : le second tentait de recréer les tables déjà créées par le
    premier (« table … already exists ») et l'application ne s'ouvrait pas.
    Le verrou est libéré automatiquement par le système à la fin du processus.
    """
    path = Path(data_dir) / ".kis_instance.lock"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(path, "a+")
    except OSError:
        return True  # dossier non verrouillable : on ne bloque pas le démarrage
    try:
        if sys.platform == "win32":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


_instance_lock = None


def configure_network():
    """Mode réseau (common/network.py) : ce poste seul, ou serveur de l'école."""
    global PORT, APP_URL, BIND_HOST, SERVER_MODE
    try:
        from common.network import bind_host, load_config
        config = load_config()
    except Exception:
        return
    PORT = config["port"]
    APP_URL = f"http://{HOST}:{PORT}/"
    BIND_HOST = bind_host(config)
    SERVER_MODE = config["mode"] == "server"


def main():
    global _instance_lock
    import django
    from django.conf import settings

    django.setup()
    configure_network()
    _instance_lock = acquire_single_instance(settings.KIS_DATA_DIR)
    if _instance_lock is None:
        # KIS Kalanso démarre déjà (ou tourne) : on se contente d'ouvrir sa fenêtre.
        open_app_window()
        return
    db_path = settings.DATABASES["default"]["NAME"]
    try:
        from common.db_guard import guard_on_start
        guard_on_start(db_path)
    except Exception as exc:
        print(f"[KIS Kalanso] Contrôle de la base impossible : {exc}")
    threading.Thread(target=open_app_window, daemon=True).start()
    if migrations_needed(db_path):
        if Path(db_path).exists():
            # Mise à jour de l'application : on garde l'état d'avant migration,
            # puis on répare les liens cassés des anciennes bases, sans quoi la
            # migration s'arrête (« invalid foreign key »).
            safe_backup()
            repair_database(db_path)
        execute_from_command_line(["manage.py", "migrate", "--noinput"])
        remember_migrations(db_path)

    clear_sessions()
    start_auto_backup()
    serve()


if __name__ == "__main__":
    main()
