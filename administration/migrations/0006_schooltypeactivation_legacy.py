from django.db import migrations, models


def mark_previous_activations_as_legacy(apps, schema_editor):
    SchoolTypeActivation = apps.get_model("administration", "SchoolTypeActivation")
    SchoolTypeActivation.objects.all().update(is_legacy=True)


class Migration(migrations.Migration):
    dependencies = [
        ("administration", "0005_school_type_activation"),
    ]

    operations = [
        migrations.AddField(
            model_name="schooltypeactivation",
            name="is_legacy",
            field=models.BooleanField(
                default=False,
                verbose_name="Compatibilité ancienne configuration",
            ),
        ),
        migrations.RunPython(mark_previous_activations_as_legacy, migrations.RunPython.noop),
    ]
