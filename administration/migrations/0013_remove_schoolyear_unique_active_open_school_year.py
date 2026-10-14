from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("administration", "0012_initial_configuration_fields"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="schoolyear",
            name="unique_active_open_school_year",
        ),
    ]
