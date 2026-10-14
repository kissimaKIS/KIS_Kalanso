from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vie_scolaire", "0002_attendance_j3_fields"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="attendance",
            options={
                "ordering": ["-date", "enrollment__student__last_name"],
                "verbose_name": "Présence",
                "verbose_name_plural": "Présences",
            },
        ),
        migrations.AlterModelOptions(
            name="disciplineincident",
            options={
                "ordering": ["-date", "-id"],
                "verbose_name": "Événement de vie scolaire",
                "verbose_name_plural": "Événements de vie scolaire",
            },
        ),
        migrations.AddField(
            model_name="attendance",
            name="note",
            field=models.CharField(blank=True, max_length=255, verbose_name="Observation"),
        ),
    ]
