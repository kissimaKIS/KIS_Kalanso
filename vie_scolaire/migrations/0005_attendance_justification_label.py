from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("vie_scolaire", "0004_teacherattendance")]

    operations = [
        migrations.AlterField(
            model_name="attendance",
            name="is_justified",
            field=models.BooleanField(default=False, verbose_name="Justification"),
        ),
    ]
