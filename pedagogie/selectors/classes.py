from django.db.models import Case, IntegerField, Value, When

from administration.models import School


def ordered_classes(queryset):
    """Return classes in pedagogical order, never alphabetical-by-label order.

    Order is: sector -> level order -> class mode (single class first) -> group.
    A level is expected to use either the single-class mode or grouped classes,
    so the mode rank mainly keeps the display deterministic and readable.
    """
    sector_order = Case(
        When(education_level__school_type=School.SchoolType.PRESCHOOL, then=Value(1)),
        When(education_level__school_type=School.SchoolType.FUNDAMENTAL_1, then=Value(2)),
        When(education_level__school_type=School.SchoolType.FUNDAMENTAL_2, then=Value(3)),
        When(education_level__school_type=School.SchoolType.HIGH_SCHOOL, then=Value(4)),
        When(education_level__school_type=School.SchoolType.VOCATIONAL, then=Value(5)),
        default=Value(99),
        output_field=IntegerField(),
    )
    group_mode_order = Case(
        When(group="", then=Value(0)),
        default=Value(1),
        output_field=IntegerField(),
    )
    # ``ordered_classes`` est normalement appelé avec un QuerySet.
    # Le filtrage de ``programme_valide`` est une propriété Python, donc
    # certains appelants lui transmettent une liste déjà filtrée.
    if isinstance(queryset, list):
        sector_rank = {
            School.SchoolType.PRESCHOOL: 1,
            School.SchoolType.FUNDAMENTAL_1: 2,
            School.SchoolType.FUNDAMENTAL_2: 3,
            School.SchoolType.HIGH_SCHOOL: 4,
            School.SchoolType.VOCATIONAL: 5,
        }
        ordered = sorted(
            queryset,
            key=lambda classe: (
                sector_rank.get(classe.education_level.school_type, 99),
                classe.education_level.order,
                getattr(classe.pedagogical_track, "order", 0) if classe.pedagogical_track_id else 0,
                getattr(classe.pedagogical_track, "name", "") if classe.pedagogical_track_id else "",
                0 if not classe.group else 1,
                classe.group or "",
                classe.education_level.name,
                classe.id,
            ),
        )
        # A Django ModelChoiceField exige un QuerySet, même lorsque le
        # filtrage préalable (programme_valide) a produit une liste Python.
        if not ordered:
            return queryset
        model = ordered[0].__class__
        position = Case(
            *[When(pk=classe.pk, then=Value(index)) for index, classe in enumerate(ordered)],
            output_field=IntegerField(),
        )
        return model.objects.filter(pk__in=[classe.pk for classe in ordered]).annotate(
            _display_order=position
        ).order_by("_display_order")

    return queryset.order_by(
        sector_order,
        "education_level__order",
        "pedagogical_track__order",
        "pedagogical_track__name",
        group_mode_order,
        "group",
        "education_level__name",
        "id",
    )
