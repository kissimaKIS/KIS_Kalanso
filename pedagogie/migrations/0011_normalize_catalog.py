from django.db import migrations


# 0005 contained an early generic subject mapping. 0006 introduced the
# granular official F1/F2 mapping (e.g. Histoire and Géographie separately).
# The lycée/professional mappings in 0005 were intentionally generic and are
# not treated as official curriculum data until validated.
LEGACY_F1_F2_CODES = {"SCI", "HG", "ART"}
LEGACY_LYC_CODES = {"FR", "MATH", "ANG", "HG", "PHCH", "SVT", "EPS", "INFO"}
LEGACY_PRO_CODES = {"FR", "MATH", "ANG", "INFO", "TECH", "PRO", "EPS"}


def normalize_catalog(apps, schema_editor):
    EducationLevelSubject = apps.get_model("pedagogie", "EducationLevelSubject")

    # Remove obsolete F1/F2 associations from the preliminary catalog.
    EducationLevelSubject.objects.filter(
        education_level__school_type__in=["fundamental_1", "fundamental_2"],
        subject__code__in=LEGACY_F1_F2_CODES,
    ).update(is_active=False)

    # Do not present the unvalidated lycée/professional subject mapping as
    # official curriculum data. Track-specific links remain untouched.
    EducationLevelSubject.objects.filter(
        education_level__school_type="high_school",
        subject__code__in=LEGACY_LYC_CODES,
    ).update(is_active=False)

    EducationLevelSubject.objects.filter(
        education_level__school_type="vocational",
        subject__code__in=LEGACY_PRO_CODES,
    ).update(is_active=False)


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("pedagogie", "0010_alter_classe_filiere_alter_subject_coefficient"),
    ]

    operations = [
        migrations.RunPython(normalize_catalog, reverse_noop),
    ]
