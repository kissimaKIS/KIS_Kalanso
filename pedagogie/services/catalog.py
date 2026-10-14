from django.db import transaction

from administration.models import SchoolYear
from pedagogie.models import EducationLevel, PedagogicalTrack, SchoolYearLevel, SchoolYearTrack


def available_levels_for_school(school):
    enabled_types = school.enabled_school_types()
    return EducationLevel.objects.filter(
        school_type__in=enabled_types,
        is_active=True,
    ).order_by("school_type", "order", "id")


@transaction.atomic
def initialize_school_year_catalog(school_year):
    """Charge dans l'année les niveaux du référentiel correspondant à son établissement."""
    levels = available_levels_for_school(school_year.school)
    SchoolYearLevel.objects.bulk_create(
        [SchoolYearLevel(school_year=school_year, education_level=level) for level in levels],
        ignore_conflicts=True,
    )
    tracks = PedagogicalTrack.objects.filter(
        school_type__in=school_year.school.enabled_school_types(),
        is_active=True,
    )
    SchoolYearTrack.objects.bulk_create(
        [SchoolYearTrack(school_year=school_year, track=track) for track in tracks],
        ignore_conflicts=True,
    )
    return levels


@transaction.atomic
def sync_school_catalogs(school):
    """Synchronise le référentiel d'une école avec ses secteurs activés.

    Une modification des secteurs ne doit pas seulement changer une option
    d'établissement : les niveaux et parcours disponibles pour les années
    scolaires actives doivent être recalculés immédiatement. Les classes
    réelles ne sont jamais créées automatiquement ici.
    """
    enabled_types = set(school.enabled_school_types())

    for school_year in school.school_years.all():
        levels = EducationLevel.objects.filter(
            school_type__in=enabled_types, is_active=True
        )
        existing_levels = {
            row.education_level_id: row
            for row in SchoolYearLevel.objects.filter(school_year=school_year)
        }
        for level in levels:
            row = existing_levels.get(level.id)
            if row is None:
                SchoolYearLevel.objects.create(
                    school_year=school_year, education_level=level, is_active=True
                )
            elif not row.is_active:
                row.is_active = True
                row.save(update_fields=["is_active"])

        SchoolYearLevel.objects.filter(school_year=school_year).exclude(
            education_level__school_type__in=enabled_types
        ).update(is_active=False)

        tracks = PedagogicalTrack.objects.filter(
            school_type__in=enabled_types, is_active=True
        )
        existing_tracks = {
            row.track_id: row
            for row in SchoolYearTrack.objects.filter(school_year=school_year)
        }
        for track in tracks:
            row = existing_tracks.get(track.id)
            if row is None:
                SchoolYearTrack.objects.create(
                    school_year=school_year, track=track, is_active=True
                )
            elif not row.is_active:
                row.is_active = True
                row.save(update_fields=["is_active"])

        SchoolYearTrack.objects.filter(school_year=school_year).exclude(
            track__school_type__in=enabled_types
        ).update(is_active=False)

    return school
