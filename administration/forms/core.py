from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone

from administration.models import School, SchoolYear, Teacher, User
from pedagogie.models import (
    Classe,
    EducationLevel,
    EducationLevelSubject,
    Enrollment,
    PedagogicalTrack,
    TrackLevel,
    SchoolYearTrack,
    SchoolYearLevel,
    Student,
    Subject,
)


class ClasseForm(forms.ModelForm):
    """Crée une classe à partir du contexte pédagogique réel.

    Fondamentale : niveau réel.
    Lycée / professionnel : série, filière ou spécialité réelle + son niveau.
    Aucun niveau générique n'est proposé à l'utilisateur.
    """

    GROUP_CHOICES = [("", "— Aucun groupe —")] + [(chr(i), f"Groupe {chr(i)}") for i in range(ord("A"), ord("Z") + 1)]

    group = forms.ChoiceField(
        label="Groupe", required=False, choices=GROUP_CHOICES,
        widget=forms.Select(attrs={"class": "kis-select"}),
        help_text="Laissez vide pour une classe unique. Si plusieurs classes existent, utilisez A, B, C…",
    )
    pedagogical_context = forms.ChoiceField(
        label="Série / filière / spécialité", required=False,
        choices=(), widget=forms.Select(attrs={"class": "kis-select"}),
        help_text="Pour une classe de Lycée ou de Centre professionnel. Laissez ce champ vide s'il s'agit d'une classe de Fondamentale ou de préscolaire.",
    )
    fundamental_level = forms.ModelChoiceField(
        label="Niveau", required=False, queryset=EducationLevel.objects.none(),
        widget=forms.Select(attrs={"class": "kis-select"}),
        help_text="Pour une classe de Fondamentale ou de préscolaire. Ne remplissez pas ce champ pour une classe de Lycée/Centre professionnel : utilisez « Série / filière / spécialité » ci-dessus.",
    )

    class Meta:
        model = Classe
        fields = ["education_level", "pedagogical_track", "group"]
        widgets = {
            "education_level": forms.Select(attrs={"class": "kis-select"}),
            "pedagogical_track": forms.Select(attrs={"class": "kis-select"}),
            "group": forms.Select(attrs={"class": "kis-select"}),
        }
        labels = {"education_level": "Niveau", "pedagogical_track": "Parcours / série / filière"}

    def __init__(self, *args, school=None, school_year=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.school, self.school_year = school, school_year
        if school is not None: self.instance.school = school
        if school_year is not None: self.instance.school_year = school_year

        secondary_types = {School.SchoolType.HIGH_SCHOOL, School.SchoolType.VOCATIONAL}
        levels = EducationLevel.objects.filter(is_active=True)
        if school: levels = levels.filter(school_type__in=school.enabled_school_types())
        if school_year: levels = levels.filter(school_year_configurations__school_year=school_year, school_year_configurations__is_active=True)
        fundamental_levels = levels.exclude(school_type__in=secondary_types).distinct().order_by("school_type", "order", "id")
        self.fields["fundamental_level"].queryset = fundamental_levels

        has_secondary = bool(school and any(t in secondary_types for t in school.enabled_school_types()))
        if has_secondary:
            contexts = TrackLevel.objects.filter(
                is_active=True, track__is_active=True,
                track__school_type__in=school.enabled_school_types(),
                track__school_year_configurations__school_year=school_year,
                track__school_year_configurations__is_active=True,
            ).select_related("track", "education_level").distinct().order_by(
                "track__school_type", "track__domain", "track__order", "education_level__order", "track__name"
            ) if school_year else TrackLevel.objects.none()
            choices=[]
            for tl in contexts:
                if tl.track.school_type == School.SchoolType.VOCATIONAL:
                    level_name = tl.education_level.name.replace("BT ", "BT") if tl.education_level.code.startswith("BT-") else tl.education_level.name.replace("CAP ", "CAP")
                    label = f"{level_name} — {tl.track.name.replace('BT ', '', 1) if tl.track.name.startswith('BT ') else tl.track.name}"
                else:
                    label = tl.track.name
                choices.append((str(tl.pk), label))
            self.fields["pedagogical_context"].choices = [("", "— Sélectionner une série / filière / spécialité —")] + choices
            self.fields["education_level"].required = False
            self.fields["education_level"].widget = forms.HiddenInput()
            self.fields["pedagogical_track"].required = False
            self.fields["pedagogical_track"].widget = forms.HiddenInput()
            self.fields["fundamental_level"].label = "Niveau (fondamentale / préscolaire)"
            if self.instance.pk:
                if self.instance.pedagogical_track_id:
                    tl = TrackLevel.objects.filter(track_id=self.instance.pedagogical_track_id, education_level_id=self.instance.education_level_id, is_active=True).first()
                    if tl: self.fields["pedagogical_context"].initial = str(tl.pk)
                elif self.instance.education_level_id:
                    self.fields["fundamental_level"].initial = self.instance.education_level_id
        else:
            self.fields.pop("pedagogical_context", None)
            self.fields.pop("fundamental_level", None)
            self.fields["pedagogical_track"].queryset = PedagogicalTrack.objects.none()
            self.fields["education_level"].queryset = levels.distinct().order_by("school_type", "order", "id")

    def clean_group(self):
        return (self.cleaned_data.get("group") or "").strip().upper()

    def clean(self):
        cleaned = super().clean()
        fundamental_level = cleaned.get("fundamental_level")
        if fundamental_level:
            cleaned["education_level"] = fundamental_level
            cleaned["pedagogical_track"] = None
        context_id = cleaned.get("pedagogical_context")
        if context_id:
            try: tl = TrackLevel.objects.select_related("track", "education_level").get(pk=context_id, is_active=True, track__is_active=True)
            except (TrackLevel.DoesNotExist, ValueError):
                self.add_error("pedagogical_context", "Le contexte pédagogique sélectionné est invalide.")
            else:
                if self.school_year and not SchoolYearTrack.objects.filter(school_year=self.school_year, track=tl.track, is_active=True).exists():
                    self.add_error("pedagogical_context", "Cette série/filière/spécialité n'est pas ouverte pour l'année scolaire.")
                else:
                    cleaned["education_level"] = tl.education_level
                    cleaned["pedagogical_track"] = tl.track

        level = cleaned.get("education_level")
        track = cleaned.get("pedagogical_track")
        group = cleaned.get("group", "")
        if not level:
            if "pedagogical_context" in self.fields:
                target_field = "pedagogical_context"
            elif "fundamental_level" in self.fields:
                target_field = "fundamental_level"
            else:
                target_field = "education_level"
            self.add_error(target_field, "Sélectionnez le contexte pédagogique réel de la classe.")
            return cleaned
        if track and not track.levels.filter(education_level=level, is_active=True).exists():
            self.add_error("pedagogical_context" if "pedagogical_context" in self.fields else "pedagogical_track", "Ce parcours ne propose pas ce niveau.")
        if self.school and self.school_year and not SchoolYearLevel.objects.filter(school_year=self.school_year, education_level=level, is_active=True).exists():
            self.add_error("education_level", "Ce niveau n'est pas ouvert pour cette année scolaire.")
        existing = Classe.objects.filter(school=self.school, school_year=self.school_year, education_level=level).exclude(pk=self.instance.pk)
        existing = existing.filter(pedagogical_track=track) if track else existing.filter(pedagogical_track__isnull=True)
        if group and existing.filter(group="").exists(): self.add_error("group", "Une classe sans groupe existe déjà dans ce contexte.")
        if not group and existing.filter(group__gt="").exists(): self.add_error("group", "Des classes groupées existent déjà dans ce contexte.")
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.school, obj.school_year = self.school, self.school_year
        obj.name = obj.display_name
        if commit:
            obj.save(); self.save_m2m()
        return obj


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ["code", "name", "coefficient", "is_active"]
        labels = {"name": "Nom"}
        widgets = {
            "code": forms.TextInput(
                attrs={"class": "kis-input", "placeholder": "Ex. MATH"}
            )
        }


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            "first_name", "last_name", "sex", "date_of_birth", "place_of_birth",
            "recruitment_year", "matricule", "father_name", "mother_name", "father_phone",
            "mother_phone", "whatsapp_phone", "contact_name", "contact_phone", "contact_relation", "photo",
        ]
        widgets = {
            "recruitment_year": forms.NumberInput(attrs={"min": 1980, "max": 2100, "placeholder": "Ex. 2022"}),
            "contact_relation": forms.TextInput(attrs={"list": "kis-relations", "placeholder": "Oncle, Tante, Tuteur…"}),
            "date_of_birth": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "max": timezone.localdate().isoformat()}),
            "photo": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }
        labels = {"sex": "Sexe", "recruitment_year": "Année de recrutement"}
        help_texts = {
            "sex": "Sélectionnez Garçon ou Fille.",
            "matricule": "Proposé automatiquement (ex. 22IQRA1M) à partir de l'année de recrutement et du sexe ; modifiable.",
            "contact_name": "Si elle est renseignée, c'est elle qui figure sur les documents internes (reçus, facture famille) ; sinon le père.",
        }

    def clean_recruitment_year(self):
        value = self.cleaned_data.get("recruitment_year")
        if value and not 1980 <= value <= timezone.localdate().year + 1:
            raise forms.ValidationError("Année de recrutement invalide (ex. 2022 pour 2022-2023).")
        return value

    def clean_date_of_birth(self):
        value = self.cleaned_data.get("date_of_birth")
        if value and value > timezone.localdate():
            raise forms.ValidationError("La date de naissance ne peut pas être dans le futur.")
        return value

class PaymentForm(forms.ModelForm):
    class Meta:
        from finance.models import Payment
        model = Payment
        fields = ["amount", "comment"]


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Nom d'utilisateur")
    password = forms.CharField(label="Mot de passe", widget=forms.PasswordInput)
