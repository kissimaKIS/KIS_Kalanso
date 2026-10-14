from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("administration", "0008_school_official_bulletin_fields"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="schoolyear",
            constraint=models.UniqueConstraint(
                fields=("school",),
                condition=Q(is_active=True, is_closed=False),
                name="unique_active_open_school_year",
            ),
        ),
    ]
