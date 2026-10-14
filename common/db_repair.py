"""Réparation des liens cassés d'une base SQLite avant sa mise à jour.

Les anciennes bases ont été remplies avant l'activation du contrôle des clés
étrangères (PRAGMA foreign_keys). Elles peuvent donc contenir des lignes
orphelines : par exemple un rôle encore attribué à un utilisateur supprimé.
Lors d'une mise à jour, Django vérifie tous ces liens et s'arrête au premier
lien cassé : l'application ne démarre plus.

Ce module répare ces lignes avant la migration :
- lien facultatif (colonne pouvant être vide) : le lien est simplement vidé ;
- lien obligatoire : la ligne orpheline est supprimée (elle désigne une
  donnée qui n'existe plus et ne peut pas être affichée).
Chaque correction est journalisée. Aucune autre donnée n'est touchée.
"""
import sqlite3
from pathlib import Path

MAX_PASSES = 20


def _quote(name):
    return '"' + str(name).replace('"', '""') + '"'


def _fk_columns(con, table):
    """{id de clé étrangère : (colonne, nullable)} pour une table."""
    nullable = {row[1]: not row[3] for row in con.execute(f"PRAGMA table_info({_quote(table)})")}
    columns = {}
    for row in con.execute(f"PRAGMA foreign_key_list({_quote(table)})"):
        fk_id, column = row[0], row[3]
        columns[fk_id] = (column, nullable.get(column, False))
    return columns


def repair_foreign_keys(db_path, log=print):
    """Répare les liens cassés du fichier ``db_path``. Retourne le nombre de corrections."""
    db_path = Path(db_path)
    if not db_path.exists():
        return 0
    fixed = 0
    con = sqlite3.connect(str(db_path), timeout=30)
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        for _ in range(MAX_PASSES):
            problems = con.execute("PRAGMA foreign_key_check").fetchall()
            if not problems:
                break
            columns = {}
            for table, rowid, parent, fk_id in problems:
                if rowid is None:
                    continue  # table sans rowid : ne concerne pas les tables Django
                if table not in columns:
                    columns[table] = _fk_columns(con, table)
                column, nullable = columns[table].get(fk_id, (None, False))
                if column and nullable:
                    con.execute(f"UPDATE {_quote(table)} SET {_quote(column)} = NULL WHERE rowid = ?", (rowid,))
                    log(f"[KIS Kalanso] Lien vers {parent} inexistant vidé : {table}.{column} (ligne {rowid}).")
                else:
                    con.execute(f"DELETE FROM {_quote(table)} WHERE rowid = ?", (rowid,))
                    log(f"[KIS Kalanso] Ligne orpheline supprimée : {table} (ligne {rowid}, renvoyait vers {parent} inexistant).")
                fixed += 1
            con.commit()
            # Une suppression peut rendre orphelines des lignes qui en dépendaient :
            # on recommence jusqu'à ce que la base soit cohérente.
    finally:
        con.close()
    return fixed
