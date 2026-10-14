from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies=[("communication","0001_initial")]
    operations=[migrations.AlterField(model_name="announcement",name="audience",field=models.CharField(choices=[("ALL","Toute l'école"),("STUDENTS","Élèves"),("TEACHERS","Enseignants"),("SECRETARY","Secrétariat"),("PARENTS","Parents"),("EXTERNAL","Communication externe")],default="ALL",max_length=20))]
