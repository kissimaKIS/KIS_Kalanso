from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("administration", "0002_schoolyear"),
    ]
    operations = [
        migrations.CreateModel(
            name="Classe",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("level", models.PositiveIntegerField(verbose_name="Niveau")),
                ("name", models.CharField(max_length=50, verbose_name="Classe")),
                ("filiere", models.CharField(blank=True, max_length=100, null=True, verbose_name="Filière")),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="classes", to="administration.school", verbose_name="Établissement")),
                ("school_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="classes", to="administration.schoolyear", verbose_name="Année scolaire")),
            ],
            options={"ordering":["level","name"],"verbose_name":"Classe","verbose_name_plural":"Classes"},
        ),
        migrations.CreateModel(
            name="Subject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True, verbose_name="Matière")),
                ("coefficient", models.PositiveIntegerField(default=1, verbose_name="Coefficient")),
            ],
            options={"ordering":["name"],"verbose_name":"Matière","verbose_name_plural":"Matières"},
        ),
        migrations.CreateModel(
            name="Student",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("first_name", models.CharField(max_length=100, verbose_name="Prénom")),
                ("last_name", models.CharField(max_length=100, verbose_name="Nom")),
                ("date_of_birth", models.DateField(blank=True, null=True, verbose_name="Date de naissance")),
                ("place_of_birth", models.CharField(blank=True, max_length=100, null=True, verbose_name="Lieu de naissance")),
                ("matricule", models.CharField(blank=True, max_length=50, null=True, unique=True, verbose_name="Matricule")),
                ("father_name", models.CharField(blank=True, max_length=100, null=True, verbose_name="Nom du père")),
                ("mother_name", models.CharField(blank=True, max_length=100, null=True, verbose_name="Nom de la mère")),
                ("father_phone", models.CharField(blank=True, max_length=30, null=True, verbose_name="Téléphone père")),
                ("mother_phone", models.CharField(blank=True, max_length=30, null=True, verbose_name="WhatsApp")),
                ("whatsapp_phone", models.CharField(blank=True, max_length=30, null=True, verbose_name="WhatsApp")),
                ("photo", models.ImageField(blank=True, null=True, upload_to="students/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering":["last_name","first_name"],"verbose_name":"Élève","verbose_name_plural":"Élèves"},
        ),
        migrations.CreateModel(
            name="Enrollment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("student_type", models.CharField(choices=[("regulier","Régulier"),("cl","Candidat libre")], default="regulier", max_length=10, verbose_name="Type d'élève")),
                ("enrollment_date", models.DateField(auto_now_add=False, default=django.utils.timezone.localdate, verbose_name="Date d'inscription")),
                ("classe", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="enrollments", to="pedagogie.classe")),
                ("school_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="enrollments", to="administration.schoolyear", verbose_name="Année scolaire")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="enrollments", to="pedagogie.student")),
            ],
            options={"ordering":["student__last_name","student__first_name"],"verbose_name":"Inscription","verbose_name_plural":"Inscriptions"},
        ),
        migrations.CreateModel(
            name="Teaching",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("classe", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="teachings", to="pedagogie.classe")),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="teachings", to="pedagogie.subject")),
                ("teacher", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="teachings", to="administration.teacher")),
            ],
            options={"verbose_name":"Enseignement","verbose_name_plural":"Enseignements"},
        ),
        migrations.CreateModel(
            name="Term",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=50, verbose_name="Trimestre")),
                ("order", models.PositiveSmallIntegerField(default=1, verbose_name="Ordre")),
                ("school_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="terms", to="administration.schoolyear")),
            ],
            options={"ordering":["order","id"],"verbose_name":"Trimestre","verbose_name_plural":"Trimestres"},
        ),
        migrations.CreateModel(
            name="Grade",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("devoir", models.FloatField(blank=True, null=True, verbose_name="Devoir")),
                ("composition", models.FloatField(blank=True, null=True, verbose_name="Composition")),
                ("enrollment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="grades", to="pedagogie.enrollment")),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="grades", to="pedagogie.subject")),
                ("term", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="grades", to="pedagogie.term")),
            ],
            options={"verbose_name":"Note","verbose_name_plural":"Notes"},
        ),
        migrations.AddConstraint(model_name="classe", constraint=models.UniqueConstraint(fields=("school","school_year","name"), name="unique_classe_per_year")),
        migrations.AddConstraint(model_name="enrollment", constraint=models.UniqueConstraint(fields=("student","school_year"), name="unique_student_year_enrollment")),
        migrations.AddConstraint(model_name="teaching", constraint=models.UniqueConstraint(fields=("teacher","subject","classe"), name="unique_teaching")),
        migrations.AddConstraint(model_name="term", constraint=models.UniqueConstraint(fields=("school_year","name"), name="unique_term_per_year")),
        migrations.AddConstraint(model_name="grade", constraint=models.UniqueConstraint(fields=("enrollment","subject","term"), name="unique_grade")),
    ]
