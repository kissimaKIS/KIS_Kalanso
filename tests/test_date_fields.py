"""Régression : les cases <input type="date"> exigent AAAA-MM-JJ. Avec le format
français (21/11/2010), le navigateur affichait une case vide et l'enregistrement
effaçait la date (ex. ajout d'une photo à une fiche élève)."""
import datetime
import re
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from administration.models import Role
from pedagogie.models import Student


def _date_value(html, name):
    m = re.search(r'<input[^>]*name="%s"[^>]*>' % name, html)
    return re.search(r'value="([^"]*)"', m.group(0)).group(1) if m and 'value="' in m.group(0) else ""


def test_student_edit_shows_iso_date_and_keeps_it_when_adding_a_photo(client, login, school, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    login(Role.ADMIN)
    s = Student.objects.create(first_name="Assitan", last_name="Magassouba", date_of_birth=datetime.date(2010, 11, 21))
    html = client.get(f"/students/{s.id}/edit/").content.decode()
    value = _date_value(html, "date_of_birth")
    assert value == "2010-11-21"
    buf = BytesIO()
    Image.new("RGB", (30, 40), "blue").save(buf, "JPEG")
    # Le navigateur renvoie ce qu'il affiche dans la case.
    client.post(f"/students/{s.id}/edit/", {"first_name": "Assitan", "last_name": "Magassouba", "date_of_birth": value,
                                            "photo": SimpleUploadedFile("p.jpg", buf.getvalue(), content_type="image/jpeg")})
    s.refresh_from_db()
    assert s.date_of_birth == datetime.date(2010, 11, 21) and s.photo


def test_every_date_widget_uses_iso_format():
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    bad = []
    apps = ("administration", "pedagogie", "finance", "vie_scolaire", "pilotage", "communication", "documents", "common")
    for path in (p for app in apps for p in (root / app).rglob("*.py")):
        if "migrations" in path.parts:
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "DateInput(" in line and 'format="%Y-%m-%d"' not in line:
                bad.append(f"{path.relative_to(root)}: {line.strip()}")
    assert not bad, bad
