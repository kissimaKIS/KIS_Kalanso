from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("administration", "0016_teacher_payments")]

    operations = [
        migrations.AlterModelOptions(
            name="teacherpayment",
            options={
                "ordering": ["-paid_at", "teacher__user__last_name", "teacher__user__first_name"],
                "verbose_name": "Paiement enseignant",
                "verbose_name_plural": "Paiements enseignants",
            },
        ),
    ]
