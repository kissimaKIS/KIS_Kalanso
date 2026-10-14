from django.core.exceptions import ValidationError
from django.db import transaction

from pedagogie.models import (Classe, Enrollment, PassageDecision, PassageDecisionLine, Grade, Term, Evaluation,
                              EducationLevel, SchoolYearLevel, TrackLevel, SchoolYearTrack)
from pedagogie.utils import moyenne_generale


def annual_average(enrollment):
    """Moyenne annuelle fondée sur les compositions de période.

    Les évaluations ponctuelles restent dans l'historique pédagogique mais ne
    participent pas à la proposition annuelle. Pour préserver les anciennes
    données du MVP, une période sans composition de période utilise encore son
    résultat officiel de bulletin.
    """
    values = []
    terms = Term.objects.filter(school_year=enrollment.school_year).order_by("order", "id")
    for term in terms:
        periodic_grades = Grade.objects.filter(
            enrollment=enrollment,
            term=term,
            evaluation__nature=Evaluation.Nature.PERIODIC_COMPOSITION,
            composition__isnull=False,
        ).select_related("subject", "evaluation")
        if periodic_grades.exists():
            mode = "F1" if enrollment.classe.education_level.school_type == "fundamental_1" else "SECONDARY"
            if mode == "F1":
                notes = [float(g.moyenne()) for g in periodic_grades]
                if notes:
                    values.append(sum(notes) / len(notes))
            else:
                total_points = 0.0
                total_coeff = 0.0
                for grade in periodic_grades:
                    if grade.class_average is None or grade.composition is None:
                        continue
                    coeff = float(grade.subject.coefficient or 0)
                    total_points += float(grade.moyenne()) * coeff
                    total_coeff += coeff
                if total_coeff:
                    values.append(total_points / total_coeff)
            continue

        if Grade.objects.filter(enrollment=enrollment, term=term, evaluation__isnull=True, composition__isnull=False).exists():
            values.append(moyenne_generale(enrollment, term))
    if not values:
        return None
    return sum(values) / len(values)


def doubled_classes(enrollment):
    return list(
        Enrollment.objects.filter(
            student=enrollment.student,
            school_year__start_date__lt=enrollment.school_year.start_date,
            school_year__is_archive=False,
        ).select_related("classe__education_level", "classe__pedagogical_track", "school_year")
        .order_by("school_year__start_date")
    )


@transaction.atomic
def get_or_create_passage(classe):
    if not classe.school_year_id:
        raise ValidationError("La classe doit être rattachée à une année scolaire.")
    passage, _ = PassageDecision.objects.get_or_create(source_year=classe.school_year, classe=classe)
    enrollments = Enrollment.objects.filter(classe=classe).select_related("student")
    existing = set(passage.lines.values_list("enrollment_id", flat=True))
    for enrollment in enrollments:
        if enrollment.id not in existing:
            PassageDecisionLine.objects.create(passage=passage, enrollment=enrollment)
    return passage

@transaction.atomic
def prepare_next_year_from_passage(passage, user=None):
    """Crée automatiquement les classes et inscriptions de l'année suivante.

    La règle est volontairement stricte : KIS ne crée jamais l'année scolaire.
    Elle doit déjà exister et son programme doit être validé. Une fois la
    décision du Directeur du CAP validée, les élèves *Passants* vont au niveau
    suivant déterminable dans leur contexte, les *Redoublants* restent au même
    niveau et les *Exclus* ne reçoivent pas d'inscription cible.

    Pour une classe groupée, le groupe est conservé (A -> A, B -> B). Cela
    évite une ressaisie tout en laissant l'établissement réorganiser ensuite
    les divisions si nécessaire.
    """
    if passage.status != PassageDecision.Status.DIRECTOR_VALIDATED:
        raise ValidationError("La décision du Directeur doit être validée avant de préparer l'année suivante.")

    source_year = passage.source_year
    target_year = (
        source_year.school.school_years.filter(
            start_date__gt=source_year.start_date,
        )
        .order_by("start_date", "id")
        .first()
    )
    if target_year is None:
        raise ValidationError(
            f"L'année scolaire suivante n'existe pas encore après {source_year.name}. "
            "Créez-la avant de valider les propositions."
        )
    if target_year.is_closed:
        raise ValidationError(f"L'année scolaire {target_year.name} est clôturée.")
    if not target_year.catalog_is_validated:
        raise ValidationError(
            f"Le référentiel de l'année scolaire {target_year.name} doit être validé avant la préparation des classes."
        )

    lines = list(passage.lines.select_related(
        "enrollment__student",
        "enrollment__classe__education_level",
        "enrollment__classe__pedagogical_track",
    ))

    # Préparer toutes les cibles avant de créer quoi que ce soit : ainsi une
    # impossibilité sur un élève ne laisse jamais une année cible partiellement
    # préparée.
    targets = []
    for line in lines:
        decision = line.director_decision
        if decision == PassageDecision.Decision.EXCLU:
            continue

        source_class = line.enrollment.classe
        target_level = source_class.education_level
        target_track = source_class.pedagogical_track

        if decision == PassageDecision.Decision.PASSANT:
            if target_track_id := getattr(target_track, "id", None):
                current = TrackLevel.objects.filter(
                    track_id=target_track_id,
                    education_level=source_class.education_level,
                    is_active=True,
                ).first()
                if current is None:
                    raise ValidationError(
                        f"Le parcours {target_track} n'est pas correctement configuré pour {source_class.education_level}."
                    )
                next_link = TrackLevel.objects.filter(
                    track_id=target_track_id,
                    is_active=True,
                    education_level__order__gt=current.education_level.order,
                ).select_related("education_level").order_by("education_level__order", "id").first()
                if next_link is None:
                    raise ValidationError(
                        f"Aucun niveau suivant n'est défini pour le parcours {target_track}. "
                        f"Le passage de {source_class.education_level.name} ne peut pas être automatisé."
                    )
                target_level = next_link.education_level
            else:
                target_level = EducationLevel.objects.filter(
                    school_type=source_class.education_level.school_type,
                    is_active=True,
                    order__gt=source_class.education_level.order,
                ).order_by("order", "id").first()
                if target_level is None:
                    raise ValidationError(
                        f"Aucun niveau suivant n'est défini après {source_class.education_level.name}."
                    )

        if not SchoolYearLevel.objects.filter(
            school_year=target_year, education_level=target_level, is_active=True
        ).exists():
            raise ValidationError(
                f"Le niveau {target_level.name} n'est pas ouvert dans l'année {target_year.name}."
            )

        if target_track_id := getattr(target_track, "id", None):
            if not TrackLevel.objects.filter(
                track_id=target_track_id, education_level=target_level, is_active=True
            ).exists():
                raise ValidationError(
                    f"Le parcours {target_track} ne propose pas le niveau {target_level.name}."
                )
            if not SchoolYearTrack.objects.filter(
                school_year=target_year, track_id=target_track_id, is_active=True
            ).exists():
                raise ValidationError(
                    f"Le parcours {target_track} n'est pas ouvert pour l'année {target_year.name}."
                )

        targets.append((line, target_level, target_track, (source_class.group or "").strip().upper()))

    created_classes = []
    created_enrollments = []
    for line, target_level, target_track, group in targets:
        source_class = line.enrollment.classe
        target_class, class_created = Classe.objects.get_or_create(
            school=source_year.school,
            school_year=target_year,
            education_level=target_level,
            pedagogical_track=target_track,
            group=group,
            defaults={
                "name": target_level.name + (f" {group}" if group else ""),
            },
        )
        if class_created:
            created_classes.append(target_class)

        enrollment, enrollment_created = Enrollment.objects.get_or_create(
            student=line.enrollment.student,
            school_year=target_year,
            defaults={
                "classe": target_class,
                "student_type": line.enrollment.student_type,
            },
        )
        if not enrollment_created and enrollment.classe_id != target_class.id:
            raise ValidationError(
                f"Une inscription existe déjà pour {enrollment.student} en {target_year.name} dans une autre classe."
            )
        if enrollment_created:
            created_enrollments.append(enrollment)

    return target_year, created_classes, created_enrollments
