from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings
class Migration(migrations.Migration):
 initial=True; dependencies=[("administration","0002_schoolyear"),("pedagogie","0001_initial")]
 operations=[migrations.CreateModel(name="Document",fields=[
  ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
  ("title",models.CharField(max_length=200)),
  ("category",models.CharField(choices=[("ADMIN","Administration"),("STUDENT","Élève"),("PEDAGOGY","Pédagogie"),("FINANCE","Finance"),("OTHER","Autre")],default="OTHER",max_length=20)),
  ("file",models.FileField(upload_to="documents/%Y/%m/")),
  ("student",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.CASCADE,related_name="documents",to="pedagogie.student")),
  ("classe",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name="documents",to="pedagogie.classe")),
  ("uploaded_by",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name="uploaded_documents",to=settings.AUTH_USER_MODEL)),
  ("uploaded_at",models.DateTimeField(auto_now_add=True))],options={"ordering":["-uploaded_at","-id"]})]
