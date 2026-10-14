from django.db import migrations


def reconcile(apps, schema_editor):
    import importlib
    module = importlib.import_module("pedagogie.migrations.0029_referentiel_secondaire_terrain")
    module.seed(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [("pedagogie", "0031_reapply_terrain_referential")]
    operations = [migrations.RunPython(reconcile, migrations.RunPython.noop)]
