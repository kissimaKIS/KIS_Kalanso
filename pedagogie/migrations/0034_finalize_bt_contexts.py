from django.db import migrations


REAL_BT_CODES = [
    "BT-ELECTROMECANIQUE",
    "BT-GENIE-CIVIL",
    "BT-COMPTA-GESTION",
    "BT-SECRETARIAT",
]


def finalize_bt_contexts(apps, schema_editor):
    PedagogicalTrack = apps.get_model("pedagogie", "PedagogicalTrack")

    # The BT catalogue contains only the four real specialities supplied by
    # the terrain reference. Any legacy BT-* context is a compatibility
    # record only and must never remain active.
    PedagogicalTrack.objects.filter(
        school_type="vocational", code__startswith="BT-"
    ).exclude(code__in=REAL_BT_CODES).update(is_active=False)

    # Ensure the four real specialities remain active.
    PedagogicalTrack.objects.filter(
        school_type="vocational", code__in=REAL_BT_CODES
    ).update(is_active=True)


def reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("pedagogie", "0033_reconcile_secondary_contexts")]
    operations = [migrations.RunPython(finalize_bt_contexts, reverse)]
