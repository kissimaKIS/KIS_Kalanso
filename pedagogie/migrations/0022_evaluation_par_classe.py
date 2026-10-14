from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("pedagogie", "0021_teaching_generalist_class_assignment"),
    ]

    operations = [
        migrations.CreateModel(
            name="Evaluation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, verbose_name="Évaluation")),
                ("date", models.DateField(verbose_name="Date")),
                ("classe", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="evaluations", to="pedagogie.classe", verbose_name="Classe")),
                ("term", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="evaluations", to="pedagogie.term", verbose_name="Période")),
            ],
            options={
                "verbose_name": "Évaluation",
                "verbose_name_plural": "Évaluations",
                "ordering": ["date", "classe__education_level__order", "classe__group", "name", "id"],
            },
        ),
        migrations.CreateModel(
            name="EvaluationSubject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order", models.PositiveSmallIntegerField(default=1, verbose_name="Ordre")),
                ("evaluation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="subject_links", to="pedagogie.evaluation", verbose_name="Évaluation")),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="evaluation_links", to="pedagogie.subject", verbose_name="Matière")),
            ],
            options={
                "verbose_name": "Matière de l'évaluation",
                "verbose_name_plural": "Matières de l'évaluation",
                "ordering": ["order", "subject__name", "id"],
            },
        ),
        migrations.AddField(
            model_name="evaluation",
            name="subjects",
            field=models.ManyToManyField(blank=True, related_name="evaluations", through="pedagogie.EvaluationSubject", to="pedagogie.subject", verbose_name="Matières"),
        ),
        migrations.AddField(
            model_name="grade",
            name="evaluation",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="grades", to="pedagogie.evaluation", verbose_name="Évaluation"),
        ),
        migrations.RemoveConstraint(
            model_name="grade",
            name="unique_grade",
        ),
        migrations.AddConstraint(
            model_name="evaluationsubject",
            constraint=models.UniqueConstraint(fields=("evaluation", "subject"), name="unique_evaluation_subject"),
        ),
        migrations.AddConstraint(
            model_name="grade",
            constraint=models.UniqueConstraint(condition=Q(evaluation__isnull=True), fields=("enrollment", "subject", "term"), name="unique_grade_legacy_term"),
        ),
        migrations.AddConstraint(
            model_name="grade",
            constraint=models.UniqueConstraint(condition=Q(evaluation__isnull=False), fields=("enrollment", "subject", "evaluation"), name="unique_grade_per_evaluation"),
        ),
    ]
