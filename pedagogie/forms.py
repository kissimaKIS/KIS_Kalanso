from django import forms
from django.db import models

from administration.models import School, Teacher

from .models import Classe, Evaluation, EvaluationSubject, Subject, TeacherSubject, Teaching, Term
from .selectors.classes import ordered_classes



class SubjectForm(forms.ModelForm):
    """Formulaire du référentiel permettant de modifier le nom de la matière."""
    class Meta:
        model = Subject
        fields = ["code", "name", "coefficient", "is_active"]
        labels = {"name": "Nom"}
        widgets = {"code": forms.TextInput(attrs={"class": "kis-input", "placeholder": "Ex. MATH"})}

class TeachingForm(forms.ModelForm):
    class AssignmentType(models.TextChoices):
        CLASS_RESPONSIBILITY = "class_responsibility", "Responsabilité de classe"
        SUBJECT_TEACHING = "subject_teaching", "Enseignement d'une matière"

    assignment_type = forms.ChoiceField(
        label="Type d'affectation",
        choices=AssignmentType.choices,
        widget=forms.Select(attrs={"class": "kis-select", "id": "id_assignment_type"}),
    )

    field_order = ["teacher", "classe", "assignment_type", "subject"]

    class Meta:
        model = Teaching
        fields = ["teacher", "subject", "classe"]
        labels = {"teacher": "Enseignant", "subject": "Matière", "classe": "Classe"}
        widgets = {
            "teacher": forms.Select(attrs={"class": "kis-select", "id": "id_teacher"}),
            "subject": forms.Select(attrs={"class": "kis-select", "id": "id_subject"}),
            "classe": forms.Select(attrs={"class": "kis-select", "id": "id_classe"}),
        }

    def __init__(self, *args, school=None, school_year=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school
        self.school_year = school_year
        self.fields["teacher"].queryset = Teacher.objects.filter(is_active=True).select_related("user")
        self.fields["subject"].required = False

        classes = Classe.objects.select_related("school_year", "education_level", "pedagogical_track")
        if school:
            classes = classes.filter(school=school)
        if school_year:
            classes = classes.filter(school_year=school_year)
        # ``catalog_is_validated`` est une propriété Python de SchoolYear,
        # pas un champ SQL : le filtrage doit donc être effectué après la requête.
        classes = [classe for classe in classes if classe.programme_valide]
        # ``programme_valide`` est une propriété Python. Après ce filtrage,
        # reconstruire un QuerySet à partir des identifiants afin que le
        # ModelChoiceField reçoive toujours un QuerySet, y compris si aucun
        # programme valide n'est disponible.
        class_ids = [classe.pk for classe in classes]
        classes_queryset = Classe.objects.filter(pk__in=class_ids)
        self.fields["classe"].queryset = ordered_classes(classes_queryset)

        teacher_id = self.data.get("teacher") or getattr(self.instance, "teacher_id", None)
        classe_id = self.data.get("classe") or getattr(self.instance, "classe_id", None)
        teacher = self.fields["teacher"].queryset.filter(pk=teacher_id).first() if teacher_id else None
        classe = self.fields["classe"].queryset.filter(pk=classe_id).select_related("education_level", "pedagogical_track").first() if classe_id else None

        self.class_subjects = {}
        for candidate in self.fields["classe"].queryset:
            self.class_subjects[str(candidate.pk)] = [
                {"id": str(link.subject_id), "name": link.name}
                for link in candidate.applicable_subject_links()
            ]

        if classe:
            self.fields["subject"].queryset = Subject.objects.filter(
                pk__in=[item["id"] for item in self.class_subjects.get(str(classe.pk), [])]
            ).order_by("name")
        else:
            self.fields["subject"].queryset = Subject.objects.none()

        if self.is_bound:
            self.fields["assignment_type"].initial = self.data.get("assignment_type")
        elif self.instance.pk:
            self.fields["assignment_type"].initial = (
                self.AssignmentType.SUBJECT_TEACHING if self.instance.subject_id else self.AssignmentType.CLASS_RESPONSIBILITY
            )
        elif teacher and teacher.pedagogical_profile == Teacher.PedagogicalProfile.GENERALISTE:
            self.fields["assignment_type"].initial = self.AssignmentType.CLASS_RESPONSIBILITY
        else:
            # Cas le plus courant (spécialiste, formateur) : enseigner une matière.
            self.fields["assignment_type"].initial = self.AssignmentType.SUBJECT_TEACHING

    def clean(self):
        cleaned = super().clean()
        teacher = cleaned.get("teacher")
        classe = cleaned.get("classe")
        subject = cleaned.get("subject")
        assignment_type = cleaned.get("assignment_type")
        if not teacher or not classe:
            return cleaned

        if self.school and classe.school_id != self.school.id:
            self.add_error("classe", "Cette classe n'appartient pas à l'établissement actif.")
        if self.school_year and classe.school_year_id != self.school_year.id:
            self.add_error("classe", "Cette classe n'appartient pas à l'année scolaire active.")

        # Le profil (généraliste, spécialiste…) ne fait que proposer le type
        # d'affectation : KIS propose, l'école décide (retours du 08/10).
        if assignment_type == self.AssignmentType.CLASS_RESPONSIBILITY:
            cleaned["subject"] = None
            return cleaned

        if assignment_type != self.AssignmentType.SUBJECT_TEACHING:
            self.add_error("assignment_type", "Sélectionnez le type d'affectation.")
        if not subject:
            self.add_error("subject", "Sélectionnez la matière à enseigner.")
        elif not classe.applicable_subject_links().filter(subject=subject, is_active=True).exists():
            self.add_error("subject", "Cette matière n'est pas prévue dans le programme actif de cette classe.")
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.cleaned_data.get("assignment_type") == self.AssignmentType.CLASS_RESPONSIBILITY:
            obj.subject = None
        if commit:
            obj.save()
        return obj

class TeacherSubjectForm(forms.ModelForm):
    class Meta:
        model = TeacherSubject
        fields = ["subject", "is_active"]
        widgets = {"subject": forms.Select(attrs={"class": "kis-input"})}


class EvaluationForm(forms.Form):
    """Création d'une évaluation pour une classe et une période.

    Les matières ne sont pas choisies ici : elles appartiennent au programme
    de la classe et la saisie est pilotée ensuite par la configuration du
    bulletin / les matières applicables.
    """
    classe = forms.ModelChoiceField(
        queryset=Classe.objects.none(),
        label="Classe",
        widget=forms.Select(attrs={"class": "kis-select", "id": "id_evaluation_classe"}),
    )
    term = forms.ModelChoiceField(
        queryset=Term.objects.none(),
        label="Période",
        widget=forms.Select(attrs={"class": "kis-select"}),
    )
    name = forms.CharField(
        max_length=100,
        label="Évaluation",
        widget=forms.TextInput(attrs={"class": "kis-input", "placeholder": "Ex. Contrôle de chant ou Composition de la première période"}),
    )
    nature = forms.ChoiceField(
        choices=Evaluation.Nature.choices,
        label="Nature",
        initial=Evaluation.Nature.PUNCTUAL,
        required=False,
        widget=forms.Select(attrs={"class": "kis-select"}),
    )
    date = forms.DateField(
        label="Date",
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"class": "kis-input", "type": "date"}),
    )

    def __init__(self, *args, school_year=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.school_year = school_year
        classes = Classe.objects.select_related("education_level", "pedagogical_track", "school_year")
        terms = Term.objects.all()
        if school_year:
            classes = classes.filter(school_year=school_year)
            terms = terms.filter(school_year=school_year)
        self.fields["classe"].queryset = classes
        self.fields["term"].queryset = terms.order_by("order", "id")

    def clean(self):
        cleaned = super().clean()
        classe = cleaned.get("classe")
        term = cleaned.get("term")
        if classe and self.school_year and classe.school_year_id != self.school_year.id:
            self.add_error("classe", "Cette classe n'appartient pas à l'année scolaire active.")
        if term and self.school_year and term.school_year_id != self.school_year.id:
            self.add_error("term", "Cette période n'appartient pas à l'année scolaire active.")
        if classe and term and classe.school_year_id != term.school_year_id:
            self.add_error("term", "La classe et la période doivent appartenir à la même année scolaire.")
        return cleaned

    def save(self):
        evaluation = Evaluation.objects.create(
            classe=self.cleaned_data["classe"],
            term=self.cleaned_data["term"],
            name=self.cleaned_data["name"],
            nature=self.cleaned_data.get("nature") or Evaluation.Nature.PUNCTUAL,
            date=self.cleaned_data["date"],
        )
        # Une évaluation concerne la classe : toutes les matières prévues au
        # programme sont rattachées automatiquement. Il n'y a donc aucun choix
        # de matières à faire lors de sa création.
        links = evaluation.classe.applicable_subject_links().filter(
            subject__is_active=True
        ).order_by("order", "subject__name")
        for order, link in enumerate(links, 1):
            EvaluationSubject.objects.create(
                evaluation=evaluation, subject=link.subject, order=order
            )
        return evaluation
