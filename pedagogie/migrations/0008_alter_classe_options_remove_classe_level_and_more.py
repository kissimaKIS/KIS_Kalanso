from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pedagogie", "0007_generic_pedagogical_structures"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="classe",
            name="level",
        ),
        migrations.AlterField(
            model_name="classe",
            name="name",
            field=models.CharField(
                max_length=100,
                verbose_name="Libellé interne",
            ),
        ),
        migrations.AlterModelOptions(
            name="classe",
            options={
                "ordering": ["education_level__order", "group", "name"],
                "verbose_name": "Classe",
                "verbose_name_plural": "Classes",
            },
        ),
    ]
