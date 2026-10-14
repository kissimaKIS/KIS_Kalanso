from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("pedagogie", "0036_alter_educationlevelsubject_options_and_more")]

    operations = [
        migrations.CreateModel(
            name="BulletinItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(blank=True, default="", max_length=150, verbose_name="Libellé")),
                ("coefficient", models.DecimalField(decimal_places=2, default=1, max_digits=5, verbose_name="Coefficient")),
                ("max_score", models.DecimalField(decimal_places=2, default=20, max_digits=6, verbose_name="Barème")),
                ("order", models.PositiveSmallIntegerField(default=1, verbose_name="Ordre")),
                ("is_active", models.BooleanField(default=True, verbose_name="Actif")),
                ("classe", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bulletin_items", to="pedagogie.classe", verbose_name="Classe")),
                ("subject", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="bulletin_items", to="pedagogie.subject", verbose_name="Matière")),
            ],
            options={
                "ordering": ["order", "id"],
                "verbose_name": "Élément du bulletin",
                "verbose_name_plural": "Éléments du bulletin",
            },
        ),
        migrations.CreateModel(
            name="BulletinItemResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("note", models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True, verbose_name="Note")),
                ("bulletin_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="results", to="pedagogie.bulletinitem")),
                ("enrollment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bulletin_item_results", to="pedagogie.enrollment")),
                ("term", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bulletin_item_results", to="pedagogie.term")),
            ],
            options={
                "verbose_name": "Résultat du bulletin",
                "verbose_name_plural": "Résultats du bulletin",
            },
        ),
        migrations.AddConstraint(
            model_name="bulletinitem",
            constraint=models.UniqueConstraint(condition=models.Q(("subject__isnull", False)), fields=("classe", "subject"), name="unique_bulletin_subject_per_class"),
        ),
        migrations.AddConstraint(
            model_name="bulletinitemresult",
            constraint=models.UniqueConstraint(fields=("enrollment", "bulletin_item", "term"), name="unique_bulletin_item_result"),
        ),
    ]
