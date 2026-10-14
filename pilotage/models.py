from django.conf import settings
from django.db import models
from django.utils import timezone
from administration.models import SchoolYear, Teacher

class BudgetCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    def __str__(self): return self.name

class BudgetEntry(models.Model):
    KIND_CHOICES = [("REVENUE", "Recette"), ("EXPENSE", "Dépense")]
    school_year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE, related_name="budget_entries")
    category = models.ForeignKey(BudgetCategory, on_delete=models.PROTECT, related_name="entries")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    label = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    date = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="budget_entries")
    class Meta:
        ordering = ["-date", "-id"]

class TeacherEvaluation(models.Model):
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="evaluations")
    school_year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE, related_name="teacher_evaluations")
    period = models.CharField(max_length=50)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    comment = models.TextField(blank=True)
    date = models.DateField(default=timezone.localdate)
    class Meta:
        ordering = ["-date", "-id"]
