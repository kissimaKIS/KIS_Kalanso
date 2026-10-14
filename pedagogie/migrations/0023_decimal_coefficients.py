from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("pedagogie", "0022_evaluation_par_classe")]
    operations = [
        migrations.AlterField(
            model_name="subject",
            name="coefficient",
            field=models.DecimalField(decimal_places=2, default=1, max_digits=5, verbose_name="Coefficient par défaut"),
        ),
        migrations.AlterField(
            model_name="educationlevelsubject",
            name="coefficient",
            field=models.DecimalField(decimal_places=2, default=1, max_digits=5, verbose_name="Coefficient"),
        ),
        migrations.AlterField(
            model_name="tracklevelsubject",
            name="coefficient",
            field=models.DecimalField(decimal_places=2, default=1, max_digits=5, verbose_name="Coefficient"),
        ),
    ]
