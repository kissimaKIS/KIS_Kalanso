from django import forms
from .models import Document
from pedagogie.models import Classe, Enrollment, Student


class DocumentForm(forms.ModelForm):
    classe = forms.ModelChoiceField(queryset=Classe.objects.none(), label="Classe", required=False)
    student = forms.ModelChoiceField(queryset=Student.objects.none(), label="Élève", required=False)

    class Meta:
        model = Document
        fields = ["title", "category", "classe", "student", "file"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        classes = Classe.objects.all().select_related("education_level").order_by("school_year__start_date", "education_level__order", "name")
        self.fields["classe"].queryset = classes
        self.fields["title"].widget.attrs.update({"list": "document-pieces", "placeholder": "Ex. Acte de naissance"})
        selected = self.data.get("classe") or self.initial.get("classe") or getattr(self.instance, "classe_id", None)
        if selected:
            self.fields["student"].queryset = Student.objects.filter(enrollments__classe_id=selected).distinct().order_by("last_name", "first_name")
