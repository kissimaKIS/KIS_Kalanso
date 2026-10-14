from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Sum
from django.shortcuts import render
from django.utils import timezone
from administration.models import School, SchoolYear, Teacher, HonorRollRule
from pedagogie.models import Enrollment, Classe, Teaching, Term, Grade, Evaluation
from finance.models import Invoice, Payment
from communication.models import Announcement
from pedagogie.models import SchoolYearTransition, PromotionProposal
from vie_scolaire.models import Attendance, DisciplineIncident, TeacherAttendance
from pedagogie.utils import moyenne_generale
from ..models import BudgetEntry
from pedagogie.models import BulletinItem
from pedagogie.permissions import TeacherScope
from django.urls import reverse
from common.years import viewed_year


def _format_dashboard_amount(value):
    """Format a dashboard amount for compact, readable display."""
    return f"{int(value or 0):,}".replace(",", " ")

def _teacher_dashboard_rows(teacher, year):
    """Affectations du professeur connecté pour l'année active."""
    if not teacher or not year:
        return []
    first_term = Term.objects.filter(school_year=year).order_by("order", "id").first()
    rows = []
    teachings = (
        Teaching.objects.filter(teacher=teacher, classe__school_year=year)
        .select_related("classe", "classe__education_level", "classe__pedagogical_track", "subject")
        .order_by("classe__education_level__order", "classe__group", "classe__name")
    )
    for teaching in teachings:
        classe = teaching.classe
        if teaching.subject_id:
            link = classe.applicable_subject_links().filter(subject=teaching.subject).first()
            subject_label = link.name if link else str(teaching.subject)
        else:
            subject_label = "Toutes les matières (titulaire)"
        results_url = None
        if first_term and BulletinItem.objects.filter(classe=classe, is_active=True).exists():
            results_url = reverse("class_results", args=[classe.id, first_term.id])
        rows.append({
            "classe": classe,
            "subject_label": subject_label,
            "students": Enrollment.objects.filter(classe=classe).values("student_id").distinct().count(),
            "results_url": results_url,
        })
    return rows


@login_required
def dashboard(request):
    year=viewed_year()
    if not year: return render(request,"pilotage/dashboard/index.html",{"school_year":None})
    scope = TeacherScope(request.user)
    if not scope.unrestricted and not request.user.is_superuser:
        from administration.permissions import user_has_permission
        if not user_has_permission(request.user, "students.view"):
            # Professeur : tableau de bord limité à ses affectations, sans
            # aucun chiffre financier ni effectif global.
            return render(request, "pilotage/dashboard/index.html", {
                "school_year": year, "current_date": timezone.localdate(),
                "teacher_scope": True, "teacher_profile": scope.teacher or None,
                "my_teachings": _teacher_dashboard_rows(scope.teacher, year),
                "upcoming_announcements": list(
                    Announcement.objects.filter(is_active=True, published_at__gt=timezone.now()).order_by("published_at", "id")[:5]
                ),
                "upcoming_year": SchoolYear.objects.filter(school=year.school, start_date__gt=timezone.localdate()).order_by("start_date").first(),
            })
    school = year.school
    enrollments=Enrollment.objects.filter(school_year=year)
    boys_count=enrollments.filter(student__sex="M").values("student_id").distinct().count()
    girls_count=enrollments.filter(student__sex="F").values("student_id").distinct().count()
    unknown_sex_count=enrollments.filter(student__sex__isnull=True).values("student_id").distinct().count()
    invoices=Invoice.objects.filter(enrollment__school_year=year)
    payments=Payment.objects.filter(invoice__enrollment__school_year=year)
    revenue=BudgetEntry.objects.filter(school_year=year,kind="REVENUE").aggregate(v=Sum("amount"))["v"] or Decimal("0")
    expenses=BudgetEntry.objects.filter(school_year=year,kind="EXPENSE").aggregate(v=Sum("amount"))["v"] or Decimal("0")
    today_records=Attendance.objects.filter(enrollment__school_year=year)
    latest_day=today_records.order_by("-date").values_list("date",flat=True).first()
    today=today_records.filter(date=latest_day) if latest_day else today_records.none()
    present=today.filter(status="PRESENT").count()+today.filter(status="LATE").count()
    total_today=today.count()

    teacher_records=TeacherAttendance.objects.filter(school_year=year, teacher__is_active=True)
    teacher_latest_day=teacher_records.order_by("-date").values_list("date", flat=True).first()
    teacher_latest=teacher_records.filter(date=teacher_latest_day) if teacher_latest_day else teacher_records.none()
    teacher_present=teacher_latest.filter(status__in=["PRESENT", "LATE"]).count()
    teacher_total=teacher_latest.count()

    cumulative_invoices=Invoice.objects.filter(enrollment__classe__school_id=school.id)
    cumulative_due=cumulative_invoices.aggregate(v=Sum("total_amount"))["v"] or Decimal("0")
    cumulative_paid=cumulative_invoices.aggregate(v=Sum("paid_amount"))["v"] or Decimal("0")
    cumulative_remaining=max(Decimal("0"), cumulative_due-cumulative_paid)
    cumulative_unpaid_count=cumulative_invoices.filter(paid_amount__lt=F("total_amount")).count()

    now = timezone.now()
    current_date = timezone.localdate()
    recent_announcements = list(
        Announcement.objects.filter(is_active=True, published_at__lte=now)
        .order_by("-published_at", "-id")[:5]
    )
    upcoming_announcements = list(
        Announcement.objects.filter(is_active=True, published_at__gt=now)
        .order_by("published_at", "id")[:5]
    )

    # Tableau d'honneur : calculé exactement comme le bulletin imprimé
    # (ClassTermResults : notes du bulletin, lignes personnalisées, coefficients
    # du programme), sur la dernière période de chaque classe qui a des notes.
    # Auparavant seules les « compositions de période » saisies via une
    # évaluation étaient lues : les notes saisies dans « Notes du bulletin »
    # étaient ignorées et le tableau restait vide malgré des moyennes ≥ seuil.
    from pedagogie.models import BulletinItemResult
    from pedagogie.services.class_results import ClassTermResults

    honor_students_by_class = []
    honor_missing_rules = []
    honor_rules = {
        (rule.school_type, rule.scale): rule
        for rule in HonorRollRule.objects.filter(school=school, is_active=True)
    }
    terms = {t.id: t for t in Term.objects.filter(school_year=year)}
    terms_with_data = {}
    for classe_id, term_id in (
        Grade.objects.filter(enrollment__school_year=year, evaluation__isnull=True, composition__isnull=False)
        .values_list("enrollment__classe_id", "term_id").distinct()
    ):
        terms_with_data.setdefault(classe_id, set()).add(term_id)
    for classe_id, term_id in (
        BulletinItemResult.objects.filter(enrollment__school_year=year)
        .values_list("enrollment__classe_id", "term_id").distinct()
    ):
        terms_with_data.setdefault(classe_id, set()).add(term_id)

    def term_key(term_id):
        term = terms[term_id]
        return (term.order, term.id)

    latest_term = None
    honor_threshold = None
    for classe in Classe.objects.filter(school_year=year, pk__in=list(terms_with_data)).select_related(
        "education_level", "pedagogical_track"
    ).order_by("education_level__order", "education_level__name", "group", "name"):
        school_type = classe.education_level.school_type
        # Le barème est une propriété du secteur : aucune conversion /10 ↔ /20.
        scale = 10 if school_type in {"preschool", "fundamental_1"} else 20
        term = terms[max((t for t in terms_with_data[classe.id] if t in terms), key=term_key)]
        if latest_term is None or term_key(term.id) > term_key(latest_term.id):
            latest_term = term
        rule = honor_rules.get((school_type, scale))
        if rule is None:
            label = classe.education_level.get_school_type_display()
            if label not in honor_missing_rules:
                honor_missing_rules.append(label)
            continue
        threshold = float(rule.threshold)
        honor_threshold = rule.threshold
        results = ClassTermResults(classe, term)
        laureates = []
        for enrollment in results.enrollments:
            if not results.grades.get(enrollment.id) and not results.direct.get(enrollment.id):
                continue  # aucune note : pas de moyenne à classer
            score = float(results.average(enrollment.id))
            if score >= threshold:
                laureates.append((score, enrollment))
        for score, enrollment in sorted(laureates, key=lambda x: -x[0]):
            honor_students_by_class.append({
                "classe": classe,
                "term": term,
                "student": enrollment.student,
                "score": score,
                "score_display": f"{score:.2f}".replace(".", ","),
                "honor_threshold": rule.threshold,
                "honor_scale": scale,
            })
    pending_proposals = PromotionProposal.objects.filter(
        transition__target_year=year, decision=PromotionProposal.Decision.PENDING
    ).count()
    unresolved_discipline = DisciplineIncident.objects.filter(
        enrollment__school_year=year, resolved=False
    ).count()
    # Hiérarchie réelle du pilotage : établissement → secteur → niveau →
    # parcours → classe. On part exclusivement des classes effectivement
    # ouvertes dans l'année scolaire : aucun niveau/parcours fictif n'est
    # ajouté pour remplir le tableau de bord.
    hierarchy = []
    classes = list(
        Classe.objects.filter(school_year=year)
        .select_related("education_level", "pedagogical_track")
        .order_by("education_level__school_type", "education_level__order", "education_level__name", "pedagogical_track__order", "pedagogical_track__name", "group", "name")
    )
    enrollment_counts = dict(
        enrollments.values("classe_id")
        .annotate(total=Count("student_id", distinct=True))
        .values_list("classe_id", "total")
    )

    sectors = {}
    for classe in classes:
        sector_code = classe.education_level.school_type
        sector_label = dict(School.SchoolType.choices).get(sector_code, sector_code)
        sector = sectors.setdefault(
            sector_code,
            {"code": sector_code, "label": sector_label, "students": 0, "classes": 0, "levels": {}}
        )
        sector["classes"] += 1
        sector["students"] += enrollment_counts.get(classe.id, 0)

        level_key = classe.education_level_id
        level = sector["levels"].setdefault(
            level_key,
            {
                "id": level_key,
                "name": classe.education_level.name,
                "order": classe.education_level.order,
                "students": 0,
                "classes": 0,
                "tracks": {},
            },
        )
        level["classes"] += 1
        level["students"] += enrollment_counts.get(classe.id, 0)

        track_key = classe.pedagogical_track_id
        track_label = classe.pedagogical_track.name if classe.pedagogical_track else "Sans parcours"
        track = level["tracks"].setdefault(
            track_key,
            {"id": track_key, "name": track_label, "students": 0, "classes": []},
        )
        track["students"] += enrollment_counts.get(classe.id, 0)
        track["classes"].append(
            {
                "id": classe.id,
                "name": classe.name,
                "group": classe.group,
                "students": enrollment_counts.get(classe.id, 0),
            }
        )

    for sector in sectors.values():
        sector["levels"] = sorted(
            sector["levels"].values(), key=lambda item: (item["order"], item["name"])
        )
        for level in sector["levels"]:
            level["tracks"] = sorted(
                level["tracks"].values(),
                key=lambda item: (item["id"] is None, item["name"]),
            )
    hierarchy = list(sectors.values())
    hierarchy.sort(key=lambda item: item["label"])

    # Vue synthétique des effectifs par niveau, destinée au dashboard.
    # Elle reprend uniquement les niveaux réellement ouverts dans l'année active.
    level_distribution = []
    for sector in hierarchy:
        for level in sector["levels"]:
            level_distribution.append({
                "sector": sector["label"],
                "level": level["name"],
                "students": level["students"],
                "classes": level["classes"],
            })

    upcoming_year = SchoolYear.objects.filter(
        school=school, start_date__gt=current_date
    ).order_by("start_date").first()
    upcoming_transition = SchoolYearTransition.objects.filter(
        source_year=year
    ).select_related("target_year").order_by("target_year__start_date").first()

    total_billed = invoices.aggregate(v=Sum("total_amount"))["v"] or Decimal("0")
    total_paid = payments.aggregate(v=Sum("amount"))["v"] or Decimal("0")

    return render(request,"pilotage/dashboard/index.html",{
      "school_year":year,"students_count":enrollments.values("student_id").distinct().count(),
      "hierarchy": hierarchy, "level_distribution": level_distribution,
      "boys_count":boys_count,"girls_count":girls_count,"unknown_sex_count":unknown_sex_count,
      "classes_count":Classe.objects.filter(school_year=year).count(),
      "teachers_count":Teacher.objects.filter(is_active=True).count(),"teaching_count":Teaching.objects.filter(classe__school_year=year).count(),
      "total_billed":total_billed,"total_paid":total_paid,
      "total_paid_display": _format_dashboard_amount(total_paid),
      "unpaid_count":cumulative_unpaid_count,"cumulative_remaining":cumulative_remaining,
      "cumulative_remaining_display": _format_dashboard_amount(cumulative_remaining),
      "revenue":revenue,"expenses":expenses,"budget_balance":revenue-expenses,
      "attendance_date":latest_day,"attendance_rate":round(present*100/total_today,1) if total_today else 0,
      "teacher_attendance_date":teacher_latest_day,
      "teacher_attendance_rate":round(teacher_present*100/teacher_total,1) if teacher_total else 0,
      "discipline_open":unresolved_discipline,
      "recent_announcements":recent_announcements, "upcoming_announcements":upcoming_announcements,
      "pending_proposals":pending_proposals, "upcoming_year":upcoming_year,
      "upcoming_transition":upcoming_transition, "current_date":current_date,
      "latest_term": latest_term, "honor_students_by_class": honor_students_by_class, "honor_roll_threshold": honor_threshold,
      "honor_missing_rules": honor_missing_rules,
      # Compte cumulant un rôle Professeur : sa carte « Mes affectations ».
      "teacher_scope": bool(scope.teacher), "teacher_profile": scope.teacher or None,
      "my_teachings": _teacher_dashboard_rows(scope.teacher, year) if scope.teacher else [],
    })
