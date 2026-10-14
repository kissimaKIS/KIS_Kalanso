from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from administration.models import School, Teacher


class TeacherForm(forms.ModelForm):
    first_name = forms.CharField(label="Prénom(s)", required=True)
    last_name = forms.CharField(label="Nom", required=True)
    email = forms.EmailField(label="Email", required=False)

    class Meta:
        model = Teacher
        fields = [
            "employee_number", "first_name", "last_name", "phone", "email",
            "address", "date_of_birth", "photo", "hire_date", "is_active",
            "contract_type", "pedagogical_profile",
            "monthly_salary", "weekly_obligation", "complementary_hours_allowed",
            "hourly_rate", "hours_cap", "contract_start_date", "contract_end_date",
            "specialty", "qualification",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "hire_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "contract_start_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "contract_end_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "photo": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, school=None, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        self.fields["employee_number"].required = True
        self.fields["phone"].required = True
        # Actif/Inactif est un choix binaire : il ne doit pas être soumis à
        # la validation HTML5 "required", sinon l'option Inactif devient
        # impossible à enregistrer (une case décochée est considérée vide).
        self.fields["is_active"].required = False
        self.fields["contract_type"].required = True
        self.fields["pedagogical_profile"].required = True

        allowed = set(school.enabled_school_types()) if school else set()
        profiles = []
        if School.SchoolType.FUNDAMENTAL_1 in allowed:
            profiles.append(Teacher.PedagogicalProfile.GENERALISTE)
        if School.SchoolType.FUNDAMENTAL_2 in allowed or School.SchoolType.HIGH_SCHOOL in allowed:
            profiles.append(Teacher.PedagogicalProfile.SPECIALISTE)
        if School.SchoolType.VOCATIONAL in allowed:
            profiles.append(Teacher.PedagogicalProfile.FORMATEUR_METIER)
        self.fields["pedagogical_profile"].choices = [
            (value, Teacher.PedagogicalProfile(value).label) for value in profiles
        ]

        if self.instance and self.instance.pk:
            self.fields["first_name"].initial = self.instance.first_name
            self.fields["last_name"].initial = self.instance.last_name
            self.fields["email"].initial = self.instance.email

    def clean_date_of_birth(self):
        value = self.cleaned_data.get("date_of_birth")
        if value and value > timezone.localdate():
            raise forms.ValidationError("La date de naissance ne peut pas être dans le futur.")
        return value

    def clean(self):
        cleaned = super().clean()
        contract = cleaned.get("contract_type")
        profile = cleaned.get("pedagogical_profile")
        allowed = set(self.school.enabled_school_types()) if self.school else set()

        if contract == Teacher.ContractType.PERMANENT and cleaned.get("hourly_rate") is not None:
            self.add_error("hourly_rate", "Le taux horaire concerne uniquement les vacataires.")
        if contract == Teacher.ContractType.VACATAIRE and cleaned.get("monthly_salary") is not None:
            self.add_error("monthly_salary", "Le salaire mensuel fixe concerne uniquement les permanents.")
        start, end = cleaned.get("contract_start_date"), cleaned.get("contract_end_date")
        if start and end and end < start:
            self.add_error("contract_end_date", "La fin du contrat ne peut pas précéder son début.")

        allowed_by_profile = {
            Teacher.PedagogicalProfile.GENERALISTE: School.SchoolType.FUNDAMENTAL_1,
            Teacher.PedagogicalProfile.SPECIALISTE: (School.SchoolType.FUNDAMENTAL_2, School.SchoolType.HIGH_SCHOOL),
            Teacher.PedagogicalProfile.FORMATEUR_METIER: School.SchoolType.VOCATIONAL,
        }
        required_scope = allowed_by_profile.get(profile)
        if required_scope:
            if isinstance(required_scope, tuple):
                valid = any(item in allowed for item in required_scope)
            else:
                valid = required_scope in allowed
            if not valid:
                self.add_error("pedagogical_profile", "Ce profil n'est pas disponible dans le périmètre de licence de l'établissement.")
        return cleaned

    def save(self, commit=True):
        # La fiche enseignant porte l'identité de la personne. Aucun compte
        # utilisateur n'est créé ici : un compte de connexion (rôle
        # Professeur) se crée explicitement dans Administration → Utilisateurs.
        teacher = super().save(commit=False)
        teacher.first_name = self.cleaned_data["first_name"].strip()
        teacher.last_name = self.cleaned_data["last_name"].strip()
        teacher.email = (self.cleaned_data.get("email") or "").strip()
        if commit:
            teacher.save()
        return teacher
