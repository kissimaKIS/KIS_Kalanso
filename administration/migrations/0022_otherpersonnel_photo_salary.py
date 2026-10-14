from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("administration", "0021_alter_school_honor_roll_threshold_help_text")]

    operations = [
        migrations.AddField(
            model_name="otherpersonnel",
            name="photo",
            field=models.ImageField(blank=True, null=True, upload_to="other_personnel/photos/", verbose_name="Photo"),
        ),
        migrations.AddField(
            model_name="otherpersonnel",
            name="monthly_salary",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name="Salaire mensuel"),
        ),
        migrations.AddField(
            model_name="otherpersonnel",
            name="hourly_rate",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name="Taux horaire"),
        ),
    ]
