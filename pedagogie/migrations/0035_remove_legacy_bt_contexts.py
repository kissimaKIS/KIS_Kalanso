from django.db import migrations


LEGACY_BT_CODES = ["BT-TERTIAIRE", "BT-INDUSTRIEL"]


def remove_legacy_bt_contexts(apps, schema_editor):
    PedagogicalTrack = apps.get_model("pedagogie", "PedagogicalTrack")
    SchoolYearTrack = apps.get_model("pedagogie", "SchoolYearTrack")
    Classe = apps.get_model("pedagogie", "Classe")

    legacy_tracks = PedagogicalTrack.objects.filter(code__in=LEGACY_BT_CODES)

    # These old generic contexts are not valid catalogue entries anymore.
    # Close their year configurations first (PROTECT FK), and detach any
    # historical classes from the obsolete track while preserving the class.
    SchoolYearTrack.objects.filter(track__in=legacy_tracks).delete()
    Classe.objects.filter(pedagogical_track__in=legacy_tracks).update(pedagogical_track=None)

    # TrackLevel and TrackLevelSubject use CASCADE, so their obsolete
    # programme rows disappear with the legacy tracks as well.
    legacy_tracks.delete()


def reverse(apps, schema_editor):
    # Deliberately irreversible: the generic BT contexts are not part of the
    # terrain referential and must not be recreated automatically.
    pass


class Migration(migrations.Migration):
    dependencies = [("pedagogie", "0034_finalize_bt_contexts")]

    operations = [migrations.RunPython(remove_legacy_bt_contexts, reverse)]
