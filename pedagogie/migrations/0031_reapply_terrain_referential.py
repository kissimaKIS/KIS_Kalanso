import importlib
from django.db import migrations


def reapply_terrain_referential(apps, schema_editor):
    # 0029 contains the authoritative terrain catalogue for the secondary.
    # It may already have been marked applied in an existing database, so
    # replay its idempotent seed here to restore the actual contexts and their
    # SchoolYearTrack links without resetting data.
    module = importlib.import_module("pedagogie.migrations.0029_referentiel_secondaire_terrain")
    module.seed(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [
        ("pedagogie", "0029_referentiel_secondaire_terrain"),
        ("pedagogie", "0030_contextual_subject_name_defaults"),
    ]

    operations = [
        migrations.RunPython(reapply_terrain_referential, migrations.RunPython.noop),
    ]
