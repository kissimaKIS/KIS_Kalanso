from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("pedagogie", "0017_grade_class_average"),
    ]

    operations = [
        migrations.CreateModel(
            name="Bulletin",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("observation_generale", models.TextField(blank=True)),
                ("date_generation", models.DateTimeField(auto_now_add=True)),
                ("enrollment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bulletins", to="pedagogie.enrollment")),
                ("term", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bulletins", to="pedagogie.term")),
            ],
        ),
        migrations.AddConstraint(
            model_name="bulletin",
            constraint=models.UniqueConstraint(fields=("enrollment", "term"), name="unique_bulletin_enrollment_term"),
        ),
    ]
