from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        ("administration", "0019_otherpersonnel_payments"),
    ]

    operations = [
        migrations.AlterField(
            model_name="otherpersonnelpayment",
            name="paid_at",
            field=models.DateField(default=timezone.localdate, verbose_name="Date de paiement"),
        ),
    ]
