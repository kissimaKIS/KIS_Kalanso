"""Réparation des liens cassés des anciennes bases avant migration."""
import sqlite3

from common.db_repair import repair_foreign_keys


def make_db(path):
    con = sqlite3.connect(path)
    con.executescript("""
        PRAGMA foreign_keys=OFF;
        CREATE TABLE user (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE role (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES user(id), name TEXT);
        CREATE TABLE note (id INTEGER PRIMARY KEY, author_id INTEGER NULL REFERENCES user(id), text TEXT);
        CREATE TABLE detail (id INTEGER PRIMARY KEY, role_id INTEGER NOT NULL REFERENCES role(id));
        INSERT INTO user VALUES (1, 'admin');
        INSERT INTO role VALUES (1, 1, 'ADMIN'), (2, 2, 'ACCOUNTANT');   -- 2 : utilisateur supprimé
        INSERT INTO note VALUES (1, 1, 'ok'), (2, 2, 'auteur supprimé');
        INSERT INTO detail VALUES (1, 1), (2, 2);                         -- dépend du rôle orphelin
    """)
    con.commit()
    con.close()


def test_orphans_are_repaired_and_valid_rows_kept(tmp_path):
    db = tmp_path / "db.sqlite3"
    make_db(db)
    logs = []
    assert repair_foreign_keys(db, log=logs.append) == 3
    con = sqlite3.connect(db)
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    assert con.execute("SELECT id FROM role").fetchall() == [(1,)]            # orphelin obligatoire : supprimé
    assert con.execute("SELECT id, author_id FROM note ORDER BY id").fetchall() == [(1, 1), (2, None)]  # facultatif : vidé
    assert con.execute("SELECT id FROM detail").fetchall() == [(1,)]          # orphelin en cascade : supprimé
    assert con.execute("SELECT count(*) FROM user").fetchone() == (1,)
    assert any("role" in line for line in logs)


def test_clean_or_missing_database_is_untouched(tmp_path):
    assert repair_foreign_keys(tmp_path / "absente.sqlite3") == 0
    db = tmp_path / "db.sqlite3"
    make_db(db)
    repair_foreign_keys(db, log=lambda m: None)
    assert repair_foreign_keys(db, log=lambda m: None) == 0
