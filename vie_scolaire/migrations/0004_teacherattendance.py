from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("administration", "0002_schoolyear"),
        ("vie_scolaire", "0003_alter_attendance_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="TeacherAttendance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(default=django.utils.timezone.localdate)),
                ("status", models.CharField(choices=[("PRESENT", "Présent"), ("ABSENT", "Absent"), ("LATE", "Retard")], default="PRESENT", max_length=7)),
                ("entry_time", models.TimeField(blank=True, null=True, verbose_name="Heure d'entrée")),
                ("exit_time", models.TimeField(blank=True, null=True, verbose_name="Heure de sortie")),
                ("late_minutes", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Durée du retard (minutes)")),
                ("note", models.CharField(blank=True, max_length=255, verbose_name="Observation")),
                ("recorded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="teacher_attendance_records", to=settings.AUTH_USER_MODEL)),
                ("school_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="teacher_attendance_records", to="administration.schoolyear", verbose_name="Année scolaire")),
                ("teacher", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attendance_records", to="administration.teacher", verbose_name="Enseignant")),
            ],
            options={"ordering": ["-date", "teacher__user__last_name", "teacher__user__first_name"], "verbose_name": "Présence enseignant", "verbose_name_plural": "Présences enseignants"},
        ),
        migrations.AddConstraint(
            model_name="teacherattendance",
            constraint=models.UniqueConstraint(fields=("teacher", "school_year", "date"), name="unique_teacher_attendance_day"),
        ),
    ]
