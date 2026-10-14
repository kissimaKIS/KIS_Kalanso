from django.contrib import admin
from .models import BudgetCategory, BudgetEntry, TeacherEvaluation
admin.site.register(BudgetCategory); admin.site.register(BudgetEntry); admin.site.register(TeacherEvaluation)
