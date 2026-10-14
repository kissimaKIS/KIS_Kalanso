from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("pedagogie", "0020_student_status")]

    operations = [
        migrations.AlterField(
            model_name="teaching",
            name="subject",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.CASCADE,
                related_name="teachings",
                to="pedagogie.subject",
            ),
        ),
        migrations.AddConstraint(
            model_name="teaching",
            constraint=models.UniqueConstraint(
                condition=Q(subject__isnull=True),
                fields=("teacher", "classe"),
                name="unique_generalist_class_teaching",
            ),
        ),
    ]
