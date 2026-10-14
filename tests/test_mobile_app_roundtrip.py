"""Aller-retour réel avec la logique de l'application mobile (exécutée par Node)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pedagogie import mobile_grades as mg
from pedagogie.models import BulletinItem, BulletinItemResult, Grade, Teaching

from .test_mobile_grades import setup  # noqa: F401 (fixture)

APP = Path(__file__).resolve().parent.parent / "mobile_app" / "KIS_Kalanso_Notes"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js absent")


def test_package_filled_by_the_mobile_logic_is_accepted(setup, tmp_path):
    conduite = BulletinItem.objects.create(classe=setup["classe"], label="Conduite", order=99, coefficient=1, max_score=20)
    Teaching.objects.filter(teacher=setup["teacher"]).update(subject=None)  # matières + Conduite
    package, _ = mg.build_package(setup["teacher"], setup["term"])
    path = tmp_path / "paquet.json"
    path.write_text(mg.package_json(package), encoding="utf-8")
    out = subprocess.run(["node", str(APP / "tests" / "fill_package.js"), str(path)],
                         capture_output=True, text=True, check=True)
    submission = mg.read_submission(out.stdout.encode("utf-8"), "notes.json")
    report = mg.analyse(submission)
    assert report.line_errors == 0
    expected = sum(len(s["students"]) for s in package.content["sheets"])
    assert report.to_apply == expected
    assert mg.apply(submission) == expected
    assert Grade.objects.filter(term=setup["term"]).count() == expected - len(setup["enrollments"])
    assert BulletinItemResult.objects.filter(bulletin_item=conduite).count() == len(setup["enrollments"])
    json.loads(out.stdout)
