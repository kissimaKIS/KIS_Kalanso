from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone

class Migration(migrations.Migration):
    dependencies=[("administration","0015_alter_teacher_hire_date_alter_teacher_phone")]
    operations=[migrations.CreateModel(name="TeacherPayment",fields=[
        ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
        ("period",models.CharField(max_length=30,verbose_name="Période")),
        ("amount",models.DecimalField(decimal_places=2,max_digits=12,verbose_name="Montant payé")),
        ("paid_at",models.DateField(default=django.utils.timezone.localdate,verbose_name="Date de paiement")),
        ("note",models.CharField(blank=True,max_length=255,verbose_name="Observation")),
        ("created_at",models.DateTimeField(auto_now_add=True)),
        ("school_year",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="teacher_payments",to="administration.schoolyear")),
        ("teacher",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="payments",to="administration.teacher")),
    ]),migrations.AddConstraint(model_name="teacherpayment",constraint=models.UniqueConstraint(fields=("teacher","school_year","period"),name="unique_teacher_payment_period"))]
