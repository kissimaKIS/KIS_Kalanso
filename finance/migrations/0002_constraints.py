from django.db import migrations, models
class Migration(migrations.Migration):
 dependencies=[("finance","0001_initial")]
 operations=[
  migrations.AddConstraint(model_name="feetype",constraint=models.UniqueConstraint(fields=("name","classe","school_year"),name="unique_fee_type_per_class_year")),
  migrations.AddConstraint(model_name="invoice",constraint=models.UniqueConstraint(fields=("enrollment","fee_type"),name="unique_invoice_per_fee")),
 ]
