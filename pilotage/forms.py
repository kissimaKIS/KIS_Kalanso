from django import forms
from .models import BudgetCategory, BudgetEntry, TeacherEvaluation


class BudgetCategoryForm(forms.ModelForm):
    class Meta:
        model = BudgetCategory
        fields = ["name"]
        labels = {"name": "Catégorie"}


class BudgetEntryForm(forms.ModelForm):
    new_category = forms.CharField(
        required=False,
        label="Nouvelle catégorie",
        help_text="Laissez vide pour utiliser une catégorie existante.",
    )

    class Meta:
        model = BudgetEntry
        fields = ["category", "kind", "label", "amount", "date", "notes"]
        labels = {
            "category": "Catégorie",
            "kind": "Type d'opération",
            "label": "Libellé",
            "amount": "Montant",
            "date": "Date",
            "notes": "Observation",
        }
        widgets = {"date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = BudgetCategory.objects.filter(is_active=True).order_by("name")
        self.fields["category"].required = False

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get("category")
        new_category = (cleaned.get("new_category") or "").strip()
        if not category and not new_category:
            self.add_error("category", "Sélectionnez une catégorie ou créez-en une.")
        if category and new_category:
            self.add_error("new_category", "Choisissez une seule catégorie : existante ou nouvelle.")
        cleaned["new_category"] = new_category
        return cleaned


class TeacherEvaluationForm(forms.ModelForm):
    class Meta:
        model = TeacherEvaluation
        fields = ["period", "score", "comment", "date"]
        widgets = {"date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})}
