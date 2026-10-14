from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from administration.forms.initial_configuration import InitialConfigurationForm, InitialBaseFeesForm, InitialOptionFormSet
from administration.models import HonorRollRule, School, SchoolTypeActivation, SchoolYear
from pedagogie.models import EducationLevel
from finance.models import FeeType


def _threshold(form, school_type):
    return {
        School.SchoolType.PRESCHOOL: (form.cleaned_data.get("threshold_preschool_10"), 10),
        School.SchoolType.FUNDAMENTAL_1: (form.cleaned_data.get("threshold_f1_10"), 10),
        School.SchoolType.FUNDAMENTAL_2: (form.cleaned_data.get("threshold_f2_20"), 20),
        School.SchoolType.HIGH_SCHOOL: (form.cleaned_data.get("threshold_high_20"), 20),
        School.SchoolType.VOCATIONAL: (form.cleaned_data.get("threshold_voc_20"), 20),
    }[school_type]


@login_required
def initial_configuration(request):
    if School.objects.filter(is_active=True).exists():
        return redirect("startup")

    form = InitialConfigurationForm(request.POST or None, request.FILES or None)
    # Le catalogue des niveaux est référentiel et existe avant toute école.
    # On prépare les choix selon le périmètre choisi, sans dépendre des classes.
    posted_level = request.POST.get("license_level", "")
    posted_secondary = request.POST.get("secondary_choice", "")
    if posted_level == School.LicenseLevel.FUNDAMENTAL:
        enabled_types = [School.SchoolType.PRESCHOOL, School.SchoolType.FUNDAMENTAL_1, School.SchoolType.FUNDAMENTAL_2]
    elif posted_level == School.LicenseLevel.SECONDARY_OR_VOCATIONAL and posted_secondary in (School.SchoolType.HIGH_SCHOOL, School.SchoolType.VOCATIONAL):
        enabled_types = [posted_secondary]
    elif posted_level == School.LicenseLevel.SECONDARY_AND_VOCATIONAL:
        enabled_types = [School.SchoolType.HIGH_SCHOOL, School.SchoolType.VOCATIONAL]
    elif posted_level == School.LicenseLevel.COMPLEX:
        enabled_types = [School.SchoolType.PRESCHOOL, School.SchoolType.FUNDAMENTAL_1, School.SchoolType.FUNDAMENTAL_2, School.SchoolType.HIGH_SCHOOL, School.SchoolType.VOCATIONAL]
    else:
        enabled_types = [School.SchoolType.PRESCHOOL, School.SchoolType.FUNDAMENTAL_1, School.SchoolType.FUNDAMENTAL_2]

    levels = EducationLevel.objects.filter(is_active=True, school_type__in=enabled_types).order_by("school_type", "order", "id")

    base_fee_form = InitialBaseFeesForm(
        request.POST or None,
        school_types=enabled_types,
        prefix="basefees",
    )
    option_data_present = "options-TOTAL_FORMS" in request.POST
    option_formset = InitialOptionFormSet(
        request.POST if option_data_present else None,
        prefix="options",
    )
    option_formset_valid = (not option_data_present) or option_formset.is_valid()

    if request.method == "POST" and form.is_valid() and base_fee_form.is_valid() and option_formset_valid:
        with transaction.atomic():
            types = form.selected_types()
            school = School.objects.create(
                name=form.cleaned_data["name"], code=form.cleaned_data["code"],
                license_level=form.cleaned_data["license_level"], school_type=types[0],
                ministry_name=form.cleaned_data["ministry_name"], academy_name=form.cleaned_data["academy_name"],
                cap_name=form.cleaned_data["cap_name"], address=form.cleaned_data["address"], city=form.cleaned_data["city"],
                phone=form.cleaned_data["phone"], email=form.cleaned_data["email"], logo=form.cleaned_data.get("logo"),
                motto=form.cleaned_data["motto"], currency=form.cleaned_data["currency"], language="Français",
            )
            for school_type in types:
                SchoolTypeActivation.objects.create(school=school, school_type=school_type, is_active=True, is_legacy=False)
                threshold, scale = _threshold(form, school_type)
                if threshold is not None:
                    HonorRollRule.objects.create(school=school, school_type=school_type, scale=scale, threshold=threshold)
            year = SchoolYear.objects.create(
                school=school, start_date=form.cleaned_data["school_year_start"], end_date=form.cleaned_data["school_year_end"], is_active=True
            )

            # Les deux frais de base sont définis une fois par secteur pédagogique
            # et s'appliquent automatiquement à tous ses niveaux.
            for school_type in enabled_types:
                registration = FeeType.objects.create(
                    name="Inscription", category=FeeType.Category.REGISTRATION,
                    amount=base_fee_form.cleaned_data[f"{school_type}_registration"],
                    is_required=True, registration_scope=FeeType.RegistrationScope.ANNUAL,
                    school_year=year, education_level=None, school_type=school_type,
                    classe=None, is_active=True,
                )
                parts = base_fee_form.registration_parts(school_type)
                if parts:
                    from finance.services.components import save_components
                    save_components(registration, [(None, name, amount) for name, amount in parts])
                FeeType.objects.create(
                    name="Scolarité", category=FeeType.Category.TUITION,
                    amount=base_fee_form.cleaned_data[f"{school_type}_tuition"],
                    is_required=True, registration_scope=FeeType.RegistrationScope.ANNUAL,
                    school_year=year, education_level=None, school_type=school_type,
                    classe=None, is_active=True,
                )

            # Les options sont transversales : elles ne dépendent d'aucun niveau.
            if option_data_present:
                for row in option_formset.cleaned_data:
                    if not row or row.get("DELETE"):
                        continue
                    if not row.get("name") or row.get("amount") is None:
                        continue
                    FeeType.objects.create(
                        name=row["name"].strip(), category=FeeType.Category.OPTIONAL, amount=row["amount"],
                        is_required=False, registration_scope=FeeType.RegistrationScope.ANNUAL,
                        school_year=year, education_level=None, classe=None, is_active=True,
                    )

        messages.success(
            request,
            "Configuration initiale enregistrée. Vérifiez maintenant le référentiel pédagogique "
            "proposé pour votre établissement, puis validez-le — vous pourrez toujours le modifier "
            "ensuite depuis l'application.",
        )
        return redirect("school_year_catalog", pk=year.pk)
    base_fee_rows = [
        {
            "school_type": school_type,
            "label": dict(School.SchoolType.choices).get(school_type, school_type),
            "registration": base_fee_form[f"{school_type}_registration"],
            "tuition": base_fee_form[f"{school_type}_tuition"],
            "parts": base_fee_form.part_fields(school_type),
            "has_parts": bool(any(base_fee_form.data.get(f"basefees-{school_type}_part_name_{i}") for i in range(base_fee_form.PARTS))),
        }
        for school_type, _label in School.SchoolType.choices
    ]
    return render(request, "administration/initial_configuration.html", {
        "form": form, "base_fee_form": base_fee_form, "base_fee_rows": base_fee_rows,
        "option_formset": option_formset, "fee_levels": levels, "enabled_types": enabled_types,
    })
