"""Verrouillage des bulletins par classe et période, et lignes personnalisées en saisie mobile."""
import json

import pytest
from django.core.exceptions import ValidationError

from administration.models import Role
from pedagogie import mobile_grades as mg
from pedagogie.models import BulletinItem, BulletinItemResult, BulletinLock, Grade, Teaching

from .test_mobile_grades import phone_file, setup  # noqa: F401 (fixture)


@pytest.fixture
def conduite(setup):
    return BulletinItem.objects.create(classe=setup["classe"], label="Conduite", order=99, coefficient=1, max_score=20)


def test_locked_term_refuses_any_bulletin_grade(setup, conduite):
    BulletinLock.objects.create(classe=setup["classe"], term=setup["term"])
    e = setup["enrollments"][0]
    with pytest.raises(ValidationError):
        Grade.objects.create(enrollment=e, subject=setup["subject"], term=setup["term"], class_average=10, composition=10)
    with pytest.raises(ValidationError):
        BulletinItemResult.objects.create(enrollment=e, bulletin_item=conduite, term=setup["term"], class_average=10, composition=10)


def test_other_term_stays_open(setup):
    from pedagogie.models import Term
    BulletinLock.objects.create(classe=setup["classe"], term=setup["term"])
    t2 = Term.objects.create(school_year=setup["year"], name="Trimestre 2", order=2)
    Grade.objects.create(enrollment=setup["enrollments"][0], subject=setup["subject"], term=t2, class_average=10, composition=10)


def test_lock_and_unlock_from_bulletins_page(client, login, setup):
    login(Role.STUDIES_DIRECTOR)
    url = f"/pedagogie/classes/{setup['classe'].id}/terms/{setup['term'].id}/bulletins/verrou/"
    client.post(url, {"action": "lock"})
    lock = BulletinLock.objects.get()
    assert lock.locked_by.username.startswith("u_")
    html = client.get(f"/pedagogie/classes/{setup['classe'].id}/terms/{setup['term'].id}/bulletins/").content.decode()
    assert "Bulletins verrouillés" in html
    client.post(url, {"action": "unlock"})
    assert not BulletinLock.objects.exists()


def test_screen_entry_is_refused_when_locked(client, login, setup):
    BulletinLock.objects.create(classe=setup["classe"], term=setup["term"])
    login(Role.STUDIES_DIRECTOR)
    item = BulletinItem.objects.get(classe=setup["classe"], subject=setup["subject"])
    e = setup["enrollments"][0]
    url = f"/pedagogie/classes/{setup['classe'].id}/terms/{setup['term'].id}/results/?item={item.id}"
    html = client.get(url).content.decode()
    assert "lecture seule" in html and "Enregistrer les notes" not in html
    client.post(url, {"item_id": item.id, f"composition_{e.id}_{setup['subject'].id}": "12",
                      f"class_average_{e.id}_{setup['subject'].id}": "12"})
    assert not Grade.objects.exists()


def test_bulletin_config_is_frozen_when_a_term_is_locked(client, login, setup):
    BulletinLock.objects.create(classe=setup["classe"], term=setup["term"])
    login(Role.STUDIES_DIRECTOR)
    before = BulletinItem.objects.count()
    client.post(f"/pedagogie/classes/{setup['classe'].id}/bulletin-config/", {"action": "add_custom", "label": "Sport"})
    assert BulletinItem.objects.count() == before


def test_teacher_cannot_lock(client, login, setup):
    login(Role.TEACHER)
    client.post(f"/pedagogie/classes/{setup['classe'].id}/terms/{setup['term'].id}/bulletins/verrou/", {"action": "lock"})
    assert not BulletinLock.objects.exists()


def test_mobile_package_skips_locked_classes_and_import_refuses_them(setup):
    package, _ = mg.build_package(setup["teacher"], setup["term"])
    submission = mg.read_submission(phone_file(package, {setup["enrollments"][0].id: (12, 12)}))
    BulletinLock.objects.create(classe=setup["classe"], term=setup["term"])
    report = mg.analyse(submission)
    assert "verrouillés" in report.sheets[0].error and report.to_apply == 0
    with pytest.raises(mg.MobileImportError, match="Aucune feuille"):
        mg.build_package(setup["teacher"], setup["term"])


def test_custom_lines_go_to_the_teacher_in_charge_of_the_whole_class(setup, conduite):
    sheets, _ = mg.teacher_sheets(setup["teacher"], setup["term"])
    assert all(s.item is None for s in sheets)  # spécialiste : pas de Conduite
    Teaching.objects.filter(teacher=setup["teacher"]).update(subject=None)
    sheets, _ = mg.teacher_sheets(setup["teacher"], setup["term"])
    assert any(s.item == conduite for s in sheets)


def test_custom_line_round_trip(setup, conduite):
    Teaching.objects.filter(teacher=setup["teacher"]).update(subject=None)
    package, _ = mg.build_package(setup["teacher"], setup["term"])
    index = next(i for i, s in enumerate(package.content["sheets"]) if s["kind"] == "item")
    assert package.content["sheets"][index]["subject"]["name"] == "Conduite"
    e = setup["enrollments"][0]
    submission = mg.read_submission(phone_file(package, {e.id: (15, 16)}, sheet_index=index))
    assert mg.apply(submission) == 1
    result = BulletinItemResult.objects.get(enrollment=e, bulletin_item=conduite)
    assert (float(result.class_average), float(result.composition)) == (15.0, 16.0)
    package2, _ = mg.build_package(setup["teacher"], setup["term"])
    student = next(s for s in package2.content["sheets"][index]["students"] if s["enrollment_id"] == e.id)
    assert (student["class_average"], student["composition"]) == (15.0, 16.0)
    json.dumps(package2.content)  # sérialisable (pas de Decimal)
