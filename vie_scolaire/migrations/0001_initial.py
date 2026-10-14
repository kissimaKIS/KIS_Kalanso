from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
class Migration(migrations.Migration):
    initial=True
    dependencies=[("pedagogie","0001_initial"),("administration","0002_schoolyear")]
    operations=[
      migrations.CreateModel(name="Attendance",fields=[
        ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
        ("date",models.DateField(default=django.utils.timezone.localdate)),
        ("status",models.CharField(choices=[("PRESENT","Présent"),("ABSENT","Absent"),("LATE","Retard"),("JUSTIFIED","Absence justifiée")],default="PRESENT",max_length=12)),
        ("note",models.CharField(blank=True,max_length=255)),
        ("enrollment",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="attendance_records",to="pedagogie.enrollment")),
        ("recorded_by",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name="attendance_records",to=settings.AUTH_USER_MODEL)),],options={"ordering":["-date","enrollment__student__last_name"]}),
      migrations.CreateModel(name="DisciplineIncident",fields=[
        ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
        ("date",models.DateField(default=django.utils.timezone.localdate)),
        ("incident_type",models.CharField(choices=[("DISCIPLINE","Discipline"),("MERIT","Mérite"),("SANCTION","Sanction"),("OTHER","Autre")],default="DISCIPLINE",max_length=20)),
        ("severity",models.CharField(choices=[("LOW","Faible"),("MEDIUM","Moyenne"),("HIGH","Élevée")],default="LOW",max_length=10)),
        ("description",models.TextField()),("action",models.CharField(blank=True,max_length=255)),("resolved",models.BooleanField(default=False)),
        ("enrollment",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="discipline_incidents",to="pedagogie.enrollment")),
        ("recorded_by",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name="discipline_records",to=settings.AUTH_USER_MODEL)),],options={"ordering":["-date","-id"]}),
      migrations.AddConstraint(model_name="attendance",constraint=models.UniqueConstraint(fields=("enrollment","date"),name="unique_attendance_day")),
    ]
