from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("administration", "0006_schooltypeactivation_legacy"),
    ]

    operations = [
        migrations.AddField(
            model_name="schoolyear",
            name="catalog_validated_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Référentiel validé le"),
        ),
        migrations.AddField(
            model_name="schoolyear",
            name="catalog_validated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="validated_school_year_catalogs",
                to="administration.user",
                verbose_name="Référentiel validé par",
            ),
        ),
    ]
