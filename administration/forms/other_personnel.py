from django import forms
from django.utils import timezone

from administration.models import OtherPersonnel


class OtherPersonnelForm(forms.ModelForm):
    class Meta:
        model = OtherPersonnel
        fields = [
            "employee_number", "first_name", "last_name", "function",
            "contract_type", "phone", "email", "address", "photo", "date_of_birth",
            "hire_date", "is_active", "monthly_salary", "hourly_rate",
        ]
        labels = {
            "employee_number": "Matricule",
            "first_name": "Prénom(s)",
            "last_name": "Nom",
            "function": "Fonction",
            "contract_type": "Statut",
            "phone": "Téléphone",
            "email": "Email",
            "address": "Adresse",
            "date_of_birth": "Date de naissance",
            "hire_date": "Date de recrutement / prise de fonction",
            "is_active": "Actif",
            "photo": "Photo",
            "monthly_salary": "Salaire mensuel",
            "hourly_rate": "Taux horaire",
        }
        widgets = {
            "photo": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "date_of_birth": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "hire_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }

    def __init__(self, *args, school=None, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        self.fields["employee_number"].required = True
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["function"].required = True
        self.fields["is_active"].required = False
        if school is not None:
            self.instance.school = school

    def clean_date_of_birth(self):
        value = self.cleaned_data.get("date_of_birth")
        if value and value > timezone.localdate():
            raise forms.ValidationError("La date de naissance ne peut pas être dans le futur.")
        return value


    def clean(self):
        cleaned = super().clean()
        contract = cleaned.get("contract_type")
        monthly = cleaned.get("monthly_salary")
        hourly = cleaned.get("hourly_rate")
        if monthly is not None and monthly < 0:
            self.add_error("monthly_salary", "Le salaire mensuel ne peut pas être négatif.")
        if hourly is not None and hourly < 0:
            self.add_error("hourly_rate", "Le taux horaire ne peut pas être négatif.")
        if contract == OtherPersonnel.ContractType.VACATAIRE and monthly is not None:
            self.add_error("monthly_salary", "Un vacataire ne peut pas avoir un salaire mensuel fixe.")
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.school is not None:
            obj.school = self.school
        if commit:
            obj.save()
        return obj
