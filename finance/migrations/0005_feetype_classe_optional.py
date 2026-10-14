from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("finance", "0004_fee_categories")]
    operations = [migrations.AlterField(
        model_name="feetype", name="classe",
        field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="fee_types", to="pedagogie.classe", verbose_name="Classe (facultatif)"),
    )]
