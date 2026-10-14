"""FeedbacksV4 — point 3 : pas de nouvelle année avant la fin de la précédente."""
import datetime

import pytest
from django.core.exceptions import ValidationError

from administration.forms import SchoolYearForm
from administration.models import Role, SchoolYear

D = datetime.date


def _close(year):
    year.is_active = False
    year.is_closed = True
    year.save()


def test_model_refuses_new_year_while_previous_is_open(school):
    with pytest.raises(ValidationError):
        SchoolYear.objects.create(school=school, start_date=D(2027, 10, 1), end_date=D(2028, 6, 30))


def test_model_refuses_new_year_while_an_inactive_year_is_not_closed(school):
    """Une année désactivée mais jamais clôturée n'est pas terminée."""
    SchoolYear.objects.filter(school=school).update(is_active=False)
    with pytest.raises(ValidationError):
        SchoolYear.objects.create(school=school, start_date=D(2027, 10, 1), end_date=D(2028, 6, 30), is_active=True)


def test_model_refuses_overlapping_dates(school):
    _close(SchoolYear.objects.get(school=school))
    with pytest.raises(ValidationError):
        # Commence avant la fin (30/06/2027) de l'année précédente.
        SchoolYear.objects.create(school=school, start_date=D(2027, 6, 1), end_date=D(2028, 5, 31), is_active=True)


def test_model_refuses_year_before_existing_ones(school):
    _close(SchoolYear.objects.get(school=school))
    with pytest.raises(ValidationError):
        SchoolYear.objects.create(school=school, start_date=D(2025, 10, 1), end_date=D(2026, 6, 30), is_active=True)


def test_next_year_allowed_once_previous_is_closed_and_finished(school):
    _close(SchoolYear.objects.get(school=school))
    year = SchoolYear.objects.create(school=school, start_date=D(2027, 10, 1), end_date=D(2028, 6, 30), is_active=True)
    assert year.pk


def test_existing_year_can_still_be_saved(school):
    year = SchoolYear.objects.get(school=school)
    year.save()  # aucune règle de création ne doit bloquer une simple mise à jour


def test_form_reports_overlap(school):
    _close(SchoolYear.objects.get(school=school))
    form = SchoolYearForm(data={"start_date": "2027-06-01", "end_date": "2028-05-31"}, school=school)
    assert not form.is_valid()
    assert "30/06/2027" in str(form.errors)


def test_create_page_redirects_while_year_open(client, login, school):
    login(Role.ADMIN)
    response = client.get("/school-year/create/")
    assert response.status_code == 302
    response = client.post("/school-year/create/", {"start_date": "2027-10-01", "end_date": "2028-06-30"})
    assert SchoolYear.objects.filter(school=school).count() == 1


def test_list_hides_new_year_button_while_year_open(client, login, school):
    login(Role.ADMIN)
    html = client.get("/school-years/").content.decode()
    assert "/school-year/create/" not in html
