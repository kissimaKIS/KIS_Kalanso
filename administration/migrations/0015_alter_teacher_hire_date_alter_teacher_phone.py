from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("administration", "0014_teacher_management"),
    ]

    operations = [
        migrations.AlterField(
            model_name="teacher",
            name="hire_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Date de recrutement / prise de fonction",
            ),
        ),
        migrations.AlterField(
            model_name="teacher",
            name="phone",
            field=models.CharField(
                blank=True,
                max_length=30,
                verbose_name="Téléphone",
            ),
        ),
    ]
