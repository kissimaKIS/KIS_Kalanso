from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
class Migration(migrations.Migration):
 initial=True; dependencies=[("administration","0002_schoolyear")]
 operations=[
 migrations.CreateModel(name="BudgetCategory",fields=[("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("name",models.CharField(max_length=100,unique=True)),("is_active",models.BooleanField(default=True))]),
 migrations.CreateModel(name="BudgetEntry",fields=[
  ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("kind",models.CharField(choices=[("REVENUE","Recette"),("EXPENSE","Dépense")],max_length=10)),("label",models.CharField(max_length=200)),("amount",models.DecimalField(decimal_places=0,max_digits=12)),("date",models.DateField(default=django.utils.timezone.localdate)),("notes",models.TextField(blank=True)),
  ("category",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="entries",to="pilotage.budgetcategory")),("school_year",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="budget_entries",to="administration.schoolyear")),("created_by",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name="budget_entries",to=settings.AUTH_USER_MODEL))],options={"ordering":["-date","-id"]}),
 migrations.CreateModel(name="TeacherEvaluation",fields=[
  ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("period",models.CharField(max_length=50)),("score",models.DecimalField(blank=True,decimal_places=2,max_digits=5,null=True)),("comment",models.TextField(blank=True)),("date",models.DateField(default=django.utils.timezone.localdate)),
  ("school_year",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="teacher_evaluations",to="administration.schoolyear")),("teacher",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="evaluations",to="administration.teacher"))],options={"ordering":["-date","-id"]})]
