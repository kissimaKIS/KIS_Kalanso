from django.db import migrations, models
from django.db.models import Q


def prepare_existing_classes(apps, schema_editor):
    # Les anciennes classes peuvent avoir "A", "6A", etc. dans name.
    # On ne déduit pas arbitrairement un groupe : on laisse group vide et
    # conserve le libellé historique pour ne perdre aucune information.
    pass


class Migration(migrations.Migration):
    dependencies = [("pedagogie", "0007_generic_pedagogical_structures")]

    operations = [
        migrations.AddField(
            model_name="classe",
            name="group",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optionnel : A, B, C… Laisser vide pour une classe unique au niveau.",
                max_length=10,
                verbose_name="Groupe",
            ),
        ),
        migrations.RunPython(prepare_existing_classes, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="classe",
            name="unique_classe_per_year",
        ),
        migrations.AddConstraint(
            model_name="classe",
            constraint=models.UniqueConstraint(
                condition=Q(pedagogical_track__isnull=True),
                fields=("school", "school_year", "education_level", "group"),
                name="unique_classe_level_group_no_track",
            ),
        ),
        migrations.AddConstraint(
            model_name="classe",
            constraint=models.UniqueConstraint(
                condition=Q(pedagogical_track__isnull=False),
                fields=("school", "school_year", "education_level", "pedagogical_track", "group"),
                name="unique_classe_level_track_group",
            ),
        ),
    ]
