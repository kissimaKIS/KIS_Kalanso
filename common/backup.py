"""Sauvegarde et restauration de KIS Kalanso.

Une sauvegarde est une archive ZIP contenant :
- ``db.sqlite3`` : copie cohérente de la base, faite avec l'API de sauvegarde
  de SQLite (et non une simple copie de fichier : en mode WAL, les dernières
  saisies peuvent encore se trouver dans ``db.sqlite3-wal``) ;
- ``media/`` : photos des élèves, logos, documents joints ;
- ``manifest.json`` : date, type (automatique / manuelle), version.

Les archives sont rangées dans ``<dossier de données>/sauvegardes``. Une copie
peut en plus être déposée dans un dossier choisi par l'utilisateur (clé USB,
disque externe, dossier synchronisé) pour survivre à une panne du disque.
"""
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection, connections

AUTO = "auto"
MANUAL = "manuel"
BEFORE_RESTORE = "avant-restauration"
KIND_LABELS = {AUTO: "Automatique", MANUAL: "Manuelle", BEFORE_RESTORE: "Avant restauration"}

AUTO_INTERVAL = timedelta(hours=24)
AUTO_KEEP = 30
PREFIX = "kalanso_"

_lock = threading.Lock()


class BackupError(Exception):
    """Erreur présentée telle quelle à l'utilisateur."""


def data_dir():
    return Path(settings.KIS_DATA_DIR)


def backup_dir():
    path = data_dir() / "sauvegardes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _config_path():
    return data_dir() / "sauvegarde.json"


def load_config():
    try:
        return json.loads(_config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(**values):
    config = load_config()
    config.update(values)
    _config_path().write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return config


def copy_dir():
    value = (load_config().get("copy_dir") or "").strip()
    return Path(value) if value else None


def set_copy_dir(value):
    value = (value or "").strip()
    if value:
        path = Path(value)
        if not path.is_dir():
            raise BackupError(f"Le dossier « {value} » est introuvable. Branchez le disque ou la clé, puis réessayez.")
        try:
            probe = path / ".kis_test_ecriture"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError:
            raise BackupError(f"Impossible d'écrire dans « {value} ».")
    save_config(copy_dir=value)


def _version():
    try:
        return (Path(settings.BASE_DIR) / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _media_root():
    return Path(settings.MEDIA_ROOT)


def _database_file():
    """Fichier de la base, ou None pour une base en mémoire (tests)."""
    name = str(connection.settings_dict["NAME"])
    if connection.vendor != "sqlite" or "memory" in name or name == ":memory:":
        return None
    return Path(name)


class _Live:
    """Connexion SQLite brute vers la base en service.

    Avec un fichier, on ouvre une connexion indépendante : elle ne dépend pas
    d'une éventuelle transaction en cours dans la requête. Sans fichier
    (base de test en mémoire), on réutilise la connexion de Django.
    """

    def __enter__(self):
        path = _database_file()
        if path is None:
            connection.ensure_connection()
            self.own = None
            return connection.connection
        self.own = sqlite3.connect(str(path), timeout=30)
        return self.own

    def __exit__(self, *exc):
        if self.own is not None:
            self.own.close()


def _dump_database(target):
    """Copie cohérente de la base courante dans ``target`` (fichier SQLite)."""
    destination = sqlite3.connect(str(target))
    try:
        with _Live() as live:
            live.backup(destination)
    finally:
        destination.close()


def create_backup(kind=MANUAL, now=None):
    """Crée une archive de sauvegarde et retourne son chemin."""
    now = now or datetime.now()
    with _lock:
        folder = backup_dir()
        name = f"{PREFIX}{now:%Y%m%d_%H%M%S}_{kind}.zip"
        target = folder / name
        counter = 1
        while target.exists():
            target = folder / f"{PREFIX}{now:%Y%m%d_%H%M%S}_{counter}_{kind}.zip"
            counter += 1
        partial = target.with_suffix(".tmp")
        with tempfile.TemporaryDirectory() as tmp:
            db_copy = Path(tmp) / "db.sqlite3"
            _dump_database(db_copy)
            with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.write(db_copy, "db.sqlite3")
                media = _media_root()
                if media.is_dir():
                    for file in media.rglob("*"):
                        if file.is_file():
                            archive.write(file, "media/" + file.relative_to(media).as_posix())
                archive.writestr("manifest.json", json.dumps({
                    "application": "KIS Kalanso", "version": _version(),
                    "created_at": now.isoformat(timespec="seconds"), "kind": kind,
                }, ensure_ascii=False))
        os.replace(partial, target)
    _copy_outside(target)
    if kind == AUTO:
        prune(AUTO, AUTO_KEEP)
    return target


def _copy_outside(path):
    """Dépose une copie dans le dossier externe choisi (sans bloquer en cas d'échec)."""
    folder = copy_dir()
    if not folder:
        return None
    try:
        destination = folder / "KIS Kalanso - sauvegardes"
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination / path.name)
        return destination / path.name
    except OSError:
        return None


def _parse(path):
    stem = path.stem[len(PREFIX):]
    parts = stem.split("_")
    try:
        created = datetime.strptime(parts[0] + parts[1], "%Y%m%d%H%M%S")
    except (IndexError, ValueError):
        created = datetime.fromtimestamp(path.stat().st_mtime)
    kind = parts[-1] if parts and parts[-1] in KIND_LABELS else MANUAL
    return created, kind


def list_backups():
    items = []
    for path in backup_dir().glob(f"{PREFIX}*.zip"):
        created, kind = _parse(path)
        items.append({
            "name": path.name, "path": path, "created_at": created, "kind": kind,
            "kind_label": KIND_LABELS[kind], "size": path.stat().st_size,
        })
    items.sort(key=lambda item: (item["created_at"], item["name"]), reverse=True)
    return items


def prune(kind, keep):
    for item in [b for b in list_backups() if b["kind"] == kind][keep:]:
        try:
            item["path"].unlink()
        except OSError:
            pass


def last_backup(kind=None):
    for item in list_backups():
        if kind is None or item["kind"] == kind:
            return item
    return None


def auto_backup_if_due(now=None):
    """Sauvegarde automatique si la dernière date de plus de 24 h. Retourne le chemin ou None."""
    now = now or datetime.now()
    last = last_backup(AUTO)
    if last and now - last["created_at"] < AUTO_INTERVAL:
        return None
    return create_backup(AUTO, now=now)


def resolve(name):
    """Chemin d'une sauvegarde du dossier, en refusant tout autre chemin."""
    if not name or "/" in name or "\\" in name or not name.startswith(PREFIX) or not name.endswith(".zip"):
        raise BackupError("Sauvegarde introuvable.")
    path = backup_dir() / name
    if not path.is_file():
        raise BackupError("Sauvegarde introuvable.")
    return path


def _check_database(path):
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as check:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupError("La base contenue dans cette sauvegarde est endommagée.")
            tables = {row[0] for row in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.DatabaseError:
        raise BackupError("Ce fichier n'est pas une sauvegarde KIS Kalanso valide.")
    if not {"django_migrations", "administration_school"} <= tables:
        raise BackupError("Ce fichier n'est pas une sauvegarde KIS Kalanso.")


def restore_backup(path):
    """Remplace les données actuelles par celles de la sauvegarde ``path``.

    Une sauvegarde « avant restauration » de l'état actuel est faite d'abord :
    une restauration par erreur peut donc toujours être annulée.
    """
    path = Path(path)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                if "db.sqlite3" not in names:
                    raise BackupError("Ce fichier n'est pas une sauvegarde KIS Kalanso (base absente).")
                for member in archive.infolist():
                    target = (tmp / member.filename).resolve()
                    if not str(target).startswith(str(tmp.resolve())):
                        raise BackupError("Archive refusée : chemin invalide.")
                archive.extractall(tmp)
        except zipfile.BadZipFile:
            raise BackupError("Ce fichier n'est pas une archive ZIP valide.")
        _check_database(tmp / "db.sqlite3")
        # Une ancienne sauvegarde peut contenir des liens cassés qui bloqueraient
        # sa mise à niveau : on les répare sur la copie, avant de l'installer.
        from .db_repair import repair_foreign_keys
        repair_foreign_keys(tmp / "db.sqlite3")

        safety = create_backup(BEFORE_RESTORE)
        with _lock:
            connections.close_all()
            source = sqlite3.connect(str(tmp / "db.sqlite3"))
            try:
                with _Live() as live:
                    source.backup(live)
            finally:
                source.close()
            connections.close_all()

            media = _media_root()
            restored_media = tmp / "media"
            if media.is_dir():
                shutil.rmtree(media, ignore_errors=True)
            if restored_media.is_dir():
                shutil.copytree(restored_media, media)
            else:
                media.mkdir(parents=True, exist_ok=True)

    # Une sauvegarde faite par une version plus ancienne est mise à niveau.
    from django.core.management import call_command
    call_command("migrate", interactive=False, verbosity=0)
    return safety


def start_auto_backup_thread(check_every=timedelta(hours=1)):
    """Sauvegarde automatique au démarrage puis toutes les 24 h tant que l'application tourne."""

    def run():
        import time
        while True:
            try:
                auto_backup_if_due()
            except Exception as exc:  # une sauvegarde ratée ne doit jamais arrêter l'application
                print(f"[KIS Kalanso] Sauvegarde automatique impossible : {exc}")
            finally:
                connections.close_all()
            time.sleep(check_every.total_seconds())

    thread = threading.Thread(target=run, name="kis-auto-backup", daemon=True)
    thread.start()
    return thread
