from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings
from django.utils import timezone
class Migration(migrations.Migration):
 initial=True; dependencies=[("administration","0002_schoolyear")]
 operations=[migrations.CreateModel(name="Announcement",fields=[
  ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
  ("title",models.CharField(max_length=200)),("message",models.TextField()),
  ("audience",models.CharField(choices=[("ALL","Toute l'école"),("STUDENTS","Élèves"),("TEACHERS","Enseignants"),("SECRETARY","Secrétariat")],default="ALL",max_length=20)),
  ("published_at",models.DateTimeField(default=timezone.now)),("is_active",models.BooleanField(default=True)),
  ("author",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name="announcements",to=settings.AUTH_USER_MODEL))],options={"ordering":["-published_at","-id"]})]
