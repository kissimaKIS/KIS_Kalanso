from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("vie_scolaire", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="attendance",
            name="is_justified",
            field=models.BooleanField(default=False, verbose_name="Absence justifiée"),
        ),
        migrations.AddField(
            model_name="attendance",
            name="justification_note",
            field=models.CharField(blank=True, max_length=255, verbose_name="Motif / justificatif"),
        ),
        migrations.AddField(
            model_name="attendance",
            name="late_minutes",
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Durée du retard (minutes)"),
        ),
        migrations.AlterField(
            model_name="attendance",
            name="status",
            field=models.CharField(
                choices=[("PRESENT", "Présent"), ("ABSENT", "Absent"), ("LATE", "Retard")],
                default="PRESENT",
                max_length=7,
            ),
        ),
    ]
