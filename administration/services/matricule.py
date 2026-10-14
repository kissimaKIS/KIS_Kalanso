"""Matricule automatique des élèves (retours du 08/10).

Format : AA + SIGLE + N° d'ordre + Genre, par exemple ``22IQRA1M`` :
- AA : les deux derniers chiffres de l'année de recrutement (2022-2023 → 22) ;
- SIGLE : le sigle de l'établissement (à défaut, les 4 premières lettres de son nom) ;
- N° d'ordre : numéro qui continue sur toute l'école, sans repartir à 1 chaque année ;
- Genre : M (garçon) ou F (fille).
"""
import re
import unicodedata

from django.core.exceptions import ValidationError
from django.db import transaction


def school_sigle(school):
    raw = (school.code or "").strip() or school.name
    text = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii").upper()
    letters = re.sub(r"[^A-Z0-9]", "", text)
    if not (school.code or "").strip():
        letters = letters[:4]
    return letters or "ECOLE"


def pattern(sigle):
    return re.compile(r"^(\d{2})" + re.escape(sigle) + r"(\d+)([MF])$")


def build(year, sigle, number, sex):
    return f"{int(year) % 100:02d}{sigle}{int(number)}{sex}"


def next_number(sigle, exclude_student=None):
    from pedagogie.models import Student
    regex = pattern(sigle)
    highest = 0
    qs = Student.objects.exclude(matricule__isnull=True).exclude(matricule="")
    if exclude_student is not None and exclude_student.pk:
        qs = qs.exclude(pk=exclude_student.pk)
    for value in qs.values_list("matricule", flat=True):
        match = regex.match(value.strip())
        if match:
            highest = max(highest, int(match.group(2)))
    return highest + 1


def propose(school, year, sex, student=None):
    """Matricule proposé pour un nouvel élève (ou None s'il manque l'année ou le genre)."""
    if not year or sex not in ("M", "F"):
        return None
    sigle = school_sigle(school)
    return build(year, sigle, next_number(sigle, exclude_student=student), sex)


def is_auto(value, school):
    return bool(value and pattern(school_sigle(school)).match(value.strip()))


def first_enrollment_year(student):
    starts = [d for d in student.enrollments.values_list("school_year__start_date", flat=True) if d]
    return min(starts).year if starts else None


def plan(school):
    """Prévision de la renumérotation de toute l'école.

    Retourne (lignes prêtes, élèves incomplets). L'ordre suit l'année de recrutement,
    puis la date de la première inscription, puis l'ordre de création des fiches.
    """
    from pedagogie.models import Student

    sigle = school_sigle(school)
    students = list(Student.objects.prefetch_related("enrollments__school_year").order_by("pk"))
    incomplete, ready = [], []
    for s in students:
        year = s.recruitment_year
        if not year or s.sex not in ("M", "F"):
            incomplete.append({"student": s, "proposed_year": year or first_enrollment_year(s)})
            continue
        dates = [e.enrollment_date for e in s.enrollments.all() if e.enrollment_date]
        ready.append((year, min(dates) if dates else None, s.created_at, s.pk, s))
    ready.sort(key=lambda t: (t[0], t[1] or t[2].date(), t[2], t[3]))
    rows = []
    for number, (year, _, _, _, s) in enumerate(ready, 1):
        rows.append({"student": s, "old": s.matricule or "", "new": build(year, sigle, number, s.sex)})
    return rows, incomplete


@transaction.atomic
def regenerate_all(school, user=None):
    """Remplace tous les matricules par le nouveau format. Refusé s'il reste des fiches incomplètes."""
    from administration.models import CorrectionLog
    from pedagogie.models import Student

    rows, incomplete = plan(school)
    if incomplete:
        raise ValidationError(f"{len(incomplete)} élève(s) sans année de recrutement ou sans genre : complétez-les d'abord.")
    # Deux temps pour ne jamais heurter l'unicité des matricules pendant l'échange.
    ids = [r["student"].pk for r in rows]
    for pk in ids:
        Student.objects.filter(pk=pk).update(matricule=f"__tmp_{pk}")
    changed = 0
    for r in rows:
        Student.objects.filter(pk=r["student"].pk).update(matricule=r["new"])
        changed += r["old"] != r["new"]
    CorrectionLog.objects.create(
        action=CorrectionLog.Action.MATRICULES,
        description=f"Matricules regénérés au format AA{school_sigle(school)}N°Genre : {len(rows)} élève(s), {changed} modifié(s).",
        reason="Génération automatique des matricules",
        user=user if getattr(user, "pk", None) else None,
    )
    return len(rows), changed
