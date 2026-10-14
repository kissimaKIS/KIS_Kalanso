from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("administration", "0008_school_official_bulletin_fields")]

    operations = [
        migrations.CreateModel(
            name="UserRoleAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[
                    ("ADMIN", "Administrateur"), ("PROMOTER", "Promoteur"), ("DIRECTOR", "Directeur"),
                    ("MANAGER", "Gérant"), ("ACCOUNTANT", "Comptable"), ("STUDIES_DIRECTOR", "Directeur des études"),
                    ("SECRETARY", "Secrétaire"), ("TEACHER", "Professeur / Enseignant"), ("STUDENT", "Élève"),
                    ("PARENT", "Parent"), ("PROF", "Professeur")], max_length=30)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="role_assignments", to="administration.user")),
            ],
            options={"verbose_name": "Rôle utilisateur", "verbose_name_plural": "Rôles utilisateurs"},
        ),
        migrations.AddConstraint(
            model_name="userroleassignment",
            constraint=models.UniqueConstraint(fields=("user", "role"), name="unique_user_role_assignment"),
        ),
    ]
