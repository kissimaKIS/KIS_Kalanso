"""FeedbacksV4 — point 1 : sauvegarde automatique, manuelle et restauration."""
import datetime
import json
import zipfile

import pytest

from administration.models import Role, School
from common import backup

# La sauvegarde lit la base par l'API SQLite : elle ne doit pas être enveloppée
# dans la transaction de test (verrou permanent sur la base en mémoire).
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def data(settings, tmp_path):
    settings.KIS_DATA_DIR = tmp_path / "data"
    settings.MEDIA_ROOT = tmp_path / "data" / "media"
    settings.MEDIA_ROOT.mkdir(parents=True)
    (settings.MEDIA_ROOT / "students").mkdir()
    (settings.MEDIA_ROOT / "students" / "photo.jpg").write_bytes(b"photo")
    return tmp_path


def test_manual_backup_contains_database_media_and_manifest(data, school):
    path = backup.create_backup(backup.MANUAL)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
    assert "db.sqlite3" in names
    assert "media/students/photo.jpg" in names
    assert manifest["kind"] == "manuel"
    assert backup.list_backups()[0]["kind_label"] == "Manuelle"


def test_restore_brings_back_previous_state_and_keeps_a_safety_copy(data, school):
    path = backup.create_backup(backup.MANUAL)
    School.objects.filter(pk=school.pk).update(name="Nom modifié après la sauvegarde")
    (backup._media_root() / "students" / "photo.jpg").unlink()
    (backup._media_root() / "nouveau.txt").write_text("x")

    safety = backup.restore_backup(path)

    assert School.objects.get(pk=school.pk).name == "Lycée Test"
    assert (backup._media_root() / "students" / "photo.jpg").read_bytes() == b"photo"
    assert not (backup._media_root() / "nouveau.txt").exists()
    assert safety.exists() and "avant-restauration" in safety.name


def test_restore_rejects_files_that_are_not_backups(data, school, tmp_path):
    bad = tmp_path / "x.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("autre.txt", "rien")
    with pytest.raises(backup.BackupError):
        backup.restore_backup(bad)
    not_zip = tmp_path / "y.zip"
    not_zip.write_text("pas un zip")
    with pytest.raises(backup.BackupError):
        backup.restore_backup(not_zip)
    assert School.objects.filter(pk=school.pk).exists()


def test_auto_backup_runs_once_per_day(data, school):
    now = datetime.datetime(2026, 10, 2, 8, 0)
    assert backup.auto_backup_if_due(now=now) is not None
    assert backup.auto_backup_if_due(now=now + datetime.timedelta(hours=3)) is None
    assert backup.auto_backup_if_due(now=now + datetime.timedelta(hours=25)) is not None


def test_old_automatic_backups_are_pruned_but_never_manual_ones(data, school, monkeypatch):
    monkeypatch.setattr(backup, "AUTO_KEEP", 3)
    backup.create_backup(backup.MANUAL, now=datetime.datetime(2026, 1, 1))
    for day in range(1, 7):
        backup.create_backup(backup.AUTO, now=datetime.datetime(2026, 10, day))
    kinds = [b["kind"] for b in backup.list_backups()]
    assert kinds.count("auto") == 3
    assert kinds.count("manuel") == 1


def test_backup_is_copied_to_external_folder(data, school, tmp_path):
    usb = tmp_path / "usb"
    usb.mkdir()
    backup.set_copy_dir(str(usb))
    path = backup.create_backup(backup.MANUAL)
    assert (usb / "KIS Kalanso - sauvegardes" / path.name).exists()


def test_external_folder_must_exist(data):
    with pytest.raises(backup.BackupError):
        backup.set_copy_dir("Z:/dossier/inexistant")


def test_resolve_refuses_paths_outside_backup_folder(data):
    for name in ["../db.sqlite3", "kalanso_x/../../a.zip", "autre.zip"]:
        with pytest.raises(backup.BackupError):
            backup.resolve(name)


def test_backup_page_and_manual_backup(client, login, data, school):
    login(Role.ADMIN)
    assert client.get("/sauvegardes/").status_code == 200
    client.post("/sauvegardes/creer/")
    assert len(backup.list_backups()) == 1


def test_accountant_cannot_open_backups(client, login, data, school):
    login(Role.ACCOUNTANT)
    response = client.get("/sauvegardes/")
    assert response.status_code in (302, 403)
    assert not backup.list_backups()


def test_restore_requires_typed_confirmation(client, login, data, school):
    login(Role.ADMIN)
    path = backup.create_backup(backup.MANUAL)
    School.objects.filter(pk=school.pk).update(name="Changé")
    client.post(f"/sauvegardes/{path.name}/restaurer/", {"confirm": "oui"})
    assert School.objects.get(pk=school.pk).name == "Changé"
    response = client.post(f"/sauvegardes/{path.name}/restaurer/", {"confirm": "restaurer"})
    assert response.status_code == 302 and response.url.endswith("/login/")
    assert School.objects.get(pk=school.pk).name == "Lycée Test"


def test_restore_repairs_broken_links_of_an_old_backup(data, school):
    import sqlite3
    import zipfile as zf
    path = backup.create_backup(backup.MANUAL)
    # Simule une ancienne sauvegarde : rôle attribué à un utilisateur supprimé.
    with zf.ZipFile(path) as archive:
        archive.extractall(data / "x")
    con = sqlite3.connect(data / "x" / "db.sqlite3")
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("INSERT INTO administration_userroleassignment (user_id, role) VALUES (999, 'ADMIN')")
    con.commit()
    con.close()
    old = data / "ancienne.zip"
    with zf.ZipFile(old, "w") as archive:
        for f in (data / "x").rglob("*"):
            if f.is_file():
                archive.write(f, f.relative_to(data / "x").as_posix())
    backup.restore_backup(old)
    from administration.models import UserRoleAssignment
    assert not UserRoleAssignment.objects.filter(user_id=999).exists()
    assert School.objects.filter(pk=school.pk).exists()
