from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0007_enrollment_discount"),
        ("pedagogie", "0013_secondary_ses_track"),
    ]

    operations = [
        migrations.AddField(
            model_name="feetype",
            name="education_level",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="fee_types",
                to="pedagogie.educationlevel",
                verbose_name="Niveau pédagogique (facultatif)",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="feetype",
            name="unique_fee_type_per_class_year",
        ),
        migrations.AddConstraint(
            model_name="feetype",
            constraint=models.UniqueConstraint(
                fields=("name", "classe", "education_level", "school_year"),
                name="unique_fee_type_per_scope_year",
            ),
        ),
    ]
