from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("administration", "0007_schoolyear_catalog_validation"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="academy_name",
            field=models.CharField(blank=True, max_length=150, verbose_name="Académie d'enseignement"),
        ),
        migrations.AddField(
            model_name="school",
            name="cap_name",
            field=models.CharField(blank=True, help_text="Centre d'Animation Pédagogique — applicable à la Fondamentale 1 et 2.", max_length=150, verbose_name="CAP"),
        ),
    ]
