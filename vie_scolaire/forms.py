from django import forms
from .models import Attendance, DisciplineIncident
from pedagogie.models import Classe, Enrollment


class AttendanceForm(forms.ModelForm):
    class Meta:
        model = Attendance
        fields = ["date", "status", "is_justified", "justification_note", "late_minutes", "note"]
        widgets = {
            "date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "justification_note": forms.TextInput(attrs={"placeholder": "Motif / justificatif"}),
            "late_minutes": forms.NumberInput(attrs={"min": 1, "placeholder": "Minutes"}),
        }


class DisciplineIncidentForm(forms.ModelForm):
    class Meta:
        model = DisciplineIncident
        fields = ["date", "incident_type", "severity", "description", "action", "resolved"]
        widgets = {"date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})}

class DisciplineEntryForm(DisciplineIncidentForm):
    classe = forms.ModelChoiceField(queryset=Classe.objects.none(), label="Classe")
    enrollment = forms.ModelChoiceField(queryset=Enrollment.objects.none(), label="Élève")

    def __init__(self, *args, school_year=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.school_year = school_year
        if school_year:
            classes = Classe.objects.filter(school_year=school_year).order_by("education_level__order", "name")
            self.fields["classe"].queryset = classes
            selected = self.data.get("classe") or self.initial.get("classe")
            if selected:
                self.fields["enrollment"].queryset = Enrollment.objects.filter(school_year=school_year, classe_id=selected).select_related("student").order_by("student__last_name", "student__first_name")
