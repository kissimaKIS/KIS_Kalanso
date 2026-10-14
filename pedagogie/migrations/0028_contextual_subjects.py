from django.db import migrations, models


def populate_contextual_names(apps, schema_editor):
    EducationLevelSubject = apps.get_model("pedagogie", "EducationLevelSubject")
    TrackLevelSubject = apps.get_model("pedagogie", "TrackLevelSubject")

    for link in EducationLevelSubject.objects.select_related("subject").all().iterator():
        if not link.name:
            link.name = link.subject.name
            link.save(update_fields=["name"])

    for link in TrackLevelSubject.objects.select_related("subject").all().iterator():
        if not link.name:
            link.name = link.subject.name
            link.save(update_fields=["name"])


class Migration(migrations.Migration):
    dependencies = [("pedagogie", "0027_decisions_passage_par_classe")]

    operations = [
        migrations.AddField(
            model_name="educationlevelsubject",
            name="name",
            field=models.CharField(max_length=100, verbose_name="Nom", default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="tracklevelsubject",
            name="name",
            field=models.CharField(max_length=100, verbose_name="Nom", default=""),
            preserve_default=False,
        ),
        migrations.RunPython(populate_contextual_names, migrations.RunPython.noop),
    ]
