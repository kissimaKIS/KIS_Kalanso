from django.db import migrations, models
import django.db.models.deletion


def seed_track_level_links(apps, schema_editor):
    # No lycée/professional series or formations are invented here.
    # The structures are intentionally empty until they are validated and entered
    # by the KIS administrator from official curricula.
    pass


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("pedagogie", "0006_pedagogical_organization_and_official_subjects"),
    ]

    operations = [
        migrations.CreateModel(
            name="PedagogicalTrack",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=40, unique=True, verbose_name="Code")),
                ("name", models.CharField(max_length=150, verbose_name="Nom")),
                ("school_type", models.CharField(choices=[
                    ("preschool", "Préscolaire"),
                    ("fundamental_1", "Fondamentale 1"),
                    ("fundamental_2", "Fondamentale 2"),
                    ("high_school", "Lycée"),
                    ("vocational", "Centre professionnel"),
                ], max_length=30, verbose_name="Type d'établissement")),
                ("kind", models.CharField(choices=[
                    ("section", "Section"),
                    ("series", "Série"),
                    ("stream", "Filière"),
                    ("training", "Formation"),
                    ("option", "Option"),
                ], default="stream", max_length=20, verbose_name="Nature")),
                ("order", models.PositiveSmallIntegerField(default=1, verbose_name="Ordre")),
                ("is_active", models.BooleanField(default=True, verbose_name="Actif")),
            ],
            options={
                "ordering": ["school_type", "kind", "order", "name"],
                "verbose_name": "Parcours pédagogique",
                "verbose_name_plural": "Parcours pédagogiques",
            },
        ),
        migrations.CreateModel(
            name="TrackLevel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order", models.PositiveSmallIntegerField(default=1, verbose_name="Ordre")),
                ("is_active", models.BooleanField(default=True, verbose_name="Actif")),
                ("education_level", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="track_links", to="pedagogie.educationlevel", verbose_name="Niveau")),
                ("track", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="levels", to="pedagogie.pedagogicaltrack", verbose_name="Parcours")),
            ],
            options={
                "ordering": ["order", "education_level__order", "id"],
                "verbose_name": "Niveau du parcours",
                "verbose_name_plural": "Niveaux des parcours",
            },
        ),
        migrations.CreateModel(
            name="TrackLevelSubject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("coefficient", models.PositiveIntegerField(default=1, verbose_name="Coefficient")),
                ("order", models.PositiveSmallIntegerField(default=1, verbose_name="Ordre")),
                ("is_active", models.BooleanField(default=True, verbose_name="Active")),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="track_level_links", to="pedagogie.subject", verbose_name="Matière")),
                ("track_level", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="subject_links", to="pedagogie.tracklevel", verbose_name="Niveau du parcours")),
            ],
            options={
                "ordering": ["order", "subject__name"],
                "verbose_name": "Matière du parcours",
                "verbose_name_plural": "Matières des parcours",
            },
        ),
        migrations.CreateModel(
            name="SchoolYearTrack",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_active", models.BooleanField(default=True, verbose_name="Ouvert dans l'établissement")),
                ("school_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="configured_tracks", to="administration.schoolyear", verbose_name="Année scolaire")),
                ("track", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="school_year_configurations", to="pedagogie.pedagogicaltrack", verbose_name="Parcours")),
            ],
            options={
                "ordering": ["track__kind", "track__order", "track__name"],
                "verbose_name": "Parcours de l'année scolaire",
                "verbose_name_plural": "Parcours de l'année scolaire",
            },
        ),
        migrations.AddField(
            model_name="classe",
            name="pedagogical_track",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="classes", to="pedagogie.pedagogicaltrack", verbose_name="Parcours / série / filière"),
        ),
        migrations.AddConstraint(
            model_name="tracklevel",
            constraint=models.UniqueConstraint(fields=("track", "education_level"), name="unique_track_level"),
        ),
        migrations.AddConstraint(
            model_name="tracklevelsubject",
            constraint=models.UniqueConstraint(fields=("track_level", "subject"), name="unique_track_level_subject"),
        ),
        migrations.AddConstraint(
            model_name="schoolyeartrack",
            constraint=models.UniqueConstraint(fields=("school_year", "track"), name="unique_school_year_track"),
        ),
        migrations.RunPython(seed_track_level_links, reverse_noop),
    ]
