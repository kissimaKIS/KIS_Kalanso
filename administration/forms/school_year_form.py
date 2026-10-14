from django import forms
from administration.models import SchoolYear


class SchoolYearForm(forms.ModelForm):
    class Meta:
        model = SchoolYear
        fields = ["start_date", "end_date"]
        widgets = {
            "start_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "end_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school

    def clean_start_date(self):
        return self.cleaned_data.get("start_date")

    def clean_end_date(self):
        end = self.cleaned_data.get("end_date")
        start = self.cleaned_data.get("start_date")
        if start and end and end <= start:
            raise forms.ValidationError("La date de fin doit être postérieure à la date de début.")
        if start and end and end.year != start.year + 1:
            raise forms.ValidationError("Une année scolaire doit couvrir deux années civiles consécutives (ex. 2026-2027).")
        return end

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")

        if start and end and end <= start:
            self.add_error("end_date", "La date de fin doit être postérieure à la date de début.")
        elif start and end and end.year != start.year + 1:
            self.add_error("end_date", "Une année scolaire doit couvrir deux années civiles consécutives (ex. 2026-2027).")

        if self.school and start and end:
            name = f"{start.year}-{end.year}"
            if SchoolYear.objects.filter(
                school=self.school, name=name
            ).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError(
                    "Cette année scolaire existe déjà pour cet établissement."
                )

        if self.school and not self.instance.pk:
            blocker = SchoolYear.creation_blocker(self.school.pk, start)
            if blocker:
                raise forms.ValidationError(blocker)
        return cleaned
