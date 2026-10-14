from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies=[("pedagogie","0015_school_year_transition_promotion_proposal")]
    operations=[
        migrations.RemoveField(model_name="promotionproposal", name="proposed_classe"),
        migrations.AddField(model_name="promotionproposal", name="target_education_level", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="promotion_targets", to="pedagogie.educationlevel", verbose_name="Niveau cible")),
        migrations.AddField(model_name="promotionproposal", name="target_track", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="promotion_targets", to="pedagogie.pedagogicaltrack", verbose_name="Parcours cible")),
        migrations.AddField(model_name="promotionproposal", name="target_group", field=models.CharField(blank=True, default="", max_length=10, verbose_name="Groupe cible")),
    ]
