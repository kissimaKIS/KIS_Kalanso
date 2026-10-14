"""Aller-retour réel : paquet de pointage KIS → logique de l'application mobile (Node) → relevé appliqué."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from vie_scolaire.models import Attendance, OtherPersonnelAttendance, TeacherAttendance
from vie_scolaire.services import pointage as svc

from .test_pointage import ctx  # noqa: F401 (fixture)

APP = Path(__file__).resolve().parent.parent / "mobile_app" / "KIS_Kalanso_Notes"
pytestmark = pytest.mark.skipif(shutil.which("node") is None or not (APP / "tests" / "scan_package.js").exists(),
                                reason="Node.js ou application mobile absents")


def test_mobile_day_of_pointage_is_applied(ctx, tmp_path):
    package = svc.build_package(ctx["school"])
    path = tmp_path / "paquet.json"
    path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    out = subprocess.run(["node", str(APP / "tests" / "scan_package.js"), str(path), ctx["day"].isoformat()],
                         capture_output=True, text=True, check=True)
    summary = svc.apply_export(json.loads(out.stdout))
    assert summary["applied"] == 6 and summary["unknown"] == 1          # 2 personnels × 2 passages + 2 élèves
    t = TeacherAttendance.objects.get(teacher=ctx["teacher"], date=ctx["day"])
    assert t.entry_time.hour == 7 and t.exit_time.hour == 17
    assert OtherPersonnelAttendance.objects.get(personnel=ctx["guard"], date=ctx["day"]).exit_time.hour == 17
    assert Attendance.objects.filter(date=ctx["day"], status="PRESENT").count() == 2
