from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("pedagogie", "0035_remove_legacy_bt_contexts"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="educationlevelsubject",
            options={
                "ordering": ["order", "name", "subject__name"],
                "verbose_name": "Matière par niveau",
                "verbose_name_plural": "Matières par niveau",
            },
        ),
        migrations.AlterModelOptions(
            name="tracklevelsubject",
            options={
                "ordering": ["order", "name", "subject__name"],
                "verbose_name": "Matière du parcours",
                "verbose_name_plural": "Matières des parcours",
            },
        ),
    ]
