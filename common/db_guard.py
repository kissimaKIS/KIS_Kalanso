"""Protection de la base SQLite contre un fichier « -wal » qui ne lui appartient pas.

En mode WAL, les dernières saisies vivent un moment dans ``db.sqlite3-wal``.
Si l'on remplace à la main ``db.sqlite3`` par une autre base (ancienne copie,
base d'un autre poste) alors que ce fichier ``-wal`` est encore là, SQLite
l'applique à la nouvelle base et l'abîme (« database disk image is malformed »).

Parade :
- à chaque fermeture normale, KIS vide le ``-wal`` dans la base (checkpoint)
  et dépose un repère ``.kis_clean_exit`` ;
- au démarrage, si ce repère est présent, le ``-wal`` devrait être vide : s'il
  ne l'est pas, il vient d'ailleurs. Il est mis de côté dans ``sauvegardes``
  (jamais supprimé) au lieu d'être appliqué ;
- sans repère (coupure de courant, plantage), le ``-wal`` est légitime et
  SQLite le récupère normalement.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

MARKER = ".kis_clean_exit"


def _companions(db):
    return db.with_name(db.name + "-wal"), db.with_name(db.name + "-shm")


def guard_on_start(db_path, log=print):
    """À appeler avant toute ouverture de la base. Retourne True si un -wal étranger a été écarté."""
    db = Path(db_path)
    marker = db.with_name(MARKER)
    clean_exit = marker.exists()
    if clean_exit:
        try:
            marker.unlink()
        except OSError:
            pass
    wal, shm = _companions(db)
    if not (clean_exit and db.exists() and wal.exists() and wal.stat().st_size > 0):
        return False
    target = db.parent / "sauvegardes"
    target.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for f in (wal, shm):
        if f.exists():
            try:
                f.replace(target / f"ecarte-{stamp}-{f.name}")
            except OSError:
                pass
    log(f"[KIS Kalanso] {datetime.now():%d/%m/%Y %H:%M} Fichier {wal.name} étranger à la base mis de côté "
        f"dans {target} : la base a sans doute été remplacée à la main.")
    return True


def checkpoint_on_exit(db_path):
    """Vide le -wal dans la base et dépose le repère de fermeture propre."""
    db = Path(db_path)
    if not db.exists():
        return
    try:
        from django.db import connections
        connections.close_all()
    except Exception:
        pass
    try:
        connection = sqlite3.connect(str(db), timeout=5)
        try:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            connection.close()
        db.with_name(MARKER).write_text(datetime.now().isoformat(), encoding="utf-8")
    except (sqlite3.Error, OSError):
        pass
