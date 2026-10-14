from django.db import migrations, models
from django.core.validators import MinValueValidator, MaxValueValidator
class Migration(migrations.Migration):
 dependencies=[("pedagogie","0001_initial")]
 operations=[
  migrations.AlterField(model_name="grade",name="devoir",field=models.FloatField(blank=True,null=True,validators=[MinValueValidator(0),MaxValueValidator(20)],verbose_name="Devoir")),
  migrations.AlterField(model_name="grade",name="composition",field=models.FloatField(blank=True,null=True,validators=[MinValueValidator(0),MaxValueValidator(20)],verbose_name="Composition")),
 ]
