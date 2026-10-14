from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pedagogie", "0013_secondary_ses_track"),
    ]

    operations = [
        migrations.AddField(
            model_name="educationlevelsubject",
            name="weekly_hours_max",
            field=models.DecimalField(
                blank=True,
                decimal_places=1,
                max_digits=4,
                null=True,
                verbose_name="Volume horaire / semaine (max)",
            ),
        ),
    ]
