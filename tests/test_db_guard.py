"""La base n'est plus abîmée quand on la remplace à la main (erreur 500 du 08/10)."""
import sqlite3

from common.db_guard import MARKER, checkpoint_on_exit, guard_on_start


def _db(path, value):
    c = sqlite3.connect(path)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
    c.execute("INSERT INTO t VALUES (?)", (value,))
    c.commit()
    return c


def test_foreign_wal_is_set_aside_after_clean_exit(tmp_path):
    db = tmp_path / "db.sqlite3"
    _db(db, "a").close()
    checkpoint_on_exit(db)
    assert (tmp_path / MARKER).exists()
    assert not (tmp_path / "db.sqlite3-wal").exists() or (tmp_path / "db.sqlite3-wal").stat().st_size == 0
    # Un -wal venu d'ailleurs apparaît à côté de la base (base remplacée à la main).
    other = tmp_path / "autre"
    other.mkdir()
    c = sqlite3.connect(other / "db.sqlite3"); c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA wal_autocheckpoint=0")
    c.execute("CREATE TABLE x (v)"); c.execute("INSERT INTO x VALUES (1)"); c.commit()
    (tmp_path / "db.sqlite3-wal").write_bytes((other / "db.sqlite3-wal").read_bytes())
    c.close()
    assert guard_on_start(db, log=lambda *_: None) is True
    assert not (tmp_path / "db.sqlite3-wal").exists()
    assert list((tmp_path / "sauvegardes").glob("ecarte-*"))
    assert sqlite3.connect(db).execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_wal_after_crash_is_kept(tmp_path):
    db = tmp_path / "db.sqlite3"
    c = _db(db, "a")
    c.execute("PRAGMA wal_autocheckpoint=0")
    c.execute("INSERT INTO t VALUES ('saisie non encore versée')"); c.commit()
    # Plantage : pas de fermeture propre, pas de repère.
    assert guard_on_start(db, log=lambda *_: None) is False
    assert (tmp_path / "db.sqlite3-wal").exists()
    c.close()
    assert sqlite3.connect(db).execute("SELECT count(*) FROM t").fetchone()[0] == 2
