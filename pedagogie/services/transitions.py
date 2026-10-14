from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from pedagogie.models import Classe, Enrollment, PromotionProposal, SchoolYearTransition


@transaction.atomic
def create_transition(source_year, target_year):
    if source_year.school_id != target_year.school_id:
        raise ValidationError("Les deux années doivent appartenir au même établissement.")
    return SchoolYearTransition.objects.get_or_create(
        source_year=source_year,
        target_year=target_year,
    )[0]


@transaction.atomic
def prepare_class_proposals(transition, class_map):
    """Prépare les propositions d'élèves sans créer les classes cibles.

    class_map: {source_classe_id: {education_level, pedagogical_track, group}}
    Rien n'est déduit automatiquement : la cible est fournie explicitement.
    Les classes et inscriptions cibles sont créées uniquement lors de
    l'application des décisions validées.
    """
    if transition.status != SchoolYearTransition.Status.DRAFT:
        raise ValidationError("La préparation n'est possible que sur un passage en préparation.")

    created_classes = []
    created_proposals = []
    for source_class_id, spec in class_map.items():
        source_class = transition.source_year.classes.get(pk=source_class_id)
        level = spec["education_level"]
        track = spec.get("pedagogical_track")
        group = (spec.get("group") or "").strip().upper()
        for enrollment in source_class.enrollments.select_related("student"):
            proposal, created = PromotionProposal.objects.get_or_create(
                transition=transition,
                source_enrollment=enrollment,
                defaults={
                    "target_education_level": level,
                    "target_track": track,
                    "target_group": group,
                },
            )
            if created:
                created_proposals.append(proposal)
    return created_classes, created_proposals


@transaction.atomic
def apply_transition(transition, user=None):
    if transition.status != SchoolYearTransition.Status.VALIDATED:
        raise ValidationError("Les décisions doivent être validées avant de préparer les inscriptions.")
    proposals = transition.proposals.filter(decision=PromotionProposal.Decision.ACCEPTED).select_related("source_enrollment", "target_education_level", "target_track")
    created = []
    for proposal in proposals:
        target_class, _ = Classe.objects.get_or_create(
            school=transition.target_year.school,
            school_year=transition.target_year,
            education_level=proposal.target_education_level,
            pedagogical_track=proposal.target_track,
            group=proposal.target_group,
            defaults={"name": proposal.target_education_level.name + (f" {proposal.target_group}" if proposal.target_group else "")},
        )
        enrollment, _ = Enrollment.objects.get_or_create(
            student=proposal.source_enrollment.student,
            school_year=transition.target_year,
            defaults={
                "classe": target_class,
                "student_type": proposal.student_type,
            },
        )
        if enrollment.classe_id != target_class.id or enrollment.student_type != proposal.student_type:
            raise ValidationError(
                f"Une inscription existe déjà pour {enrollment.student} dans l'année cible avec une autre configuration."
            )
        created.append(enrollment)
    transition.status = SchoolYearTransition.Status.APPLIED
    transition.applied_at = timezone.now()
    transition.applied_by = user if getattr(user, "pk", None) else None
    transition.save(update_fields=["status", "applied_at", "applied_by", "updated_at"])
    return created
