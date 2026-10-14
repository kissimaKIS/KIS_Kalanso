from decimal import Decimal
from django.db import migrations


def reconcile(apps, schema_editor):
    PedagogicalTrack = apps.get_model("pedagogie", "PedagogicalTrack")
    TrackLevelSubject = apps.get_model("pedagogie", "TrackLevelSubject")
    # Legacy generic BT contexts must never be active.
    PedagogicalTrack.objects.filter(
        code__in=["BT-TERTIAIRE", "BT-INDUSTRIEL"]
    ).update(is_active=False)
    # The terrain reference for 11e Sciences uses 5h of Mathematics.
    TrackLevelSubject.objects.filter(
        track_level__track__code="LY-11-SCI",
        track_level__education_level__code="LYC-11",
        subject__code="MATH",
    ).update(weekly_hours=Decimal("5.0"))


def reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("pedagogie", "0032_reconcile_terrain_contexts")]
    operations = [migrations.RunPython(reconcile, reverse)]
