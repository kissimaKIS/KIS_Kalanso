from django import forms

from administration.models import School
from .models import (
    EducationLevel,
    EducationLevelSubject,
    Classe,
    PedagogicalTrack,
    SchoolYear,
    SchoolYearLevel,
    SchoolYearTrack,
    Subject,
    TrackLevelSubject,
)




class PedagogicalTrackForm(forms.ModelForm):
    """Modification d'une série/filière/spécialité réelle du référentiel."""
    class Meta:
        model = PedagogicalTrack
        fields = ["name", "domain", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "kis-input"}),
            "domain": forms.TextInput(attrs={"class": "kis-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "kis-checkbox"}),
        }
        labels = {"name": "Nom", "domain": "Domaine", "is_active": "Active"}

class SchoolYearCatalogForm(forms.Form):
    """Choisit uniquement les contextes réels que l'établissement ouvre.

    Pour le lycée et le centre professionnel, les niveaux génériques ne sont
    jamais présentés à l'utilisateur : seules les séries/filières/spécialités
    réellement référencées sont proposées. Les niveaux techniques historiques
    restent en base pour la compatibilité des données existantes.
    """

    levels = forms.ModelMultipleChoiceField(
        queryset=EducationLevel.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple, label="Niveaux ouverts",
    )
    tracks = forms.ModelMultipleChoiceField(
        queryset=PedagogicalTrack.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple, label="Séries / filières / spécialités ouvertes",
    )

    def __init__(self, *args, school_year, **kwargs):
        super().__init__(*args, **kwargs)
        self.school_year = school_year
        enabled_types = school_year.school.enabled_school_types()
        # Les niveaux génériques du secondaire/professionnel ne sont pas une
        # offre pédagogique : ils restent uniquement des ancres techniques.
        self.fields["levels"].queryset = EducationLevel.objects.filter(
            school_type__in=enabled_types, is_active=True
        ).exclude(
            school_type__in=[School.SchoolType.HIGH_SCHOOL, School.SchoolType.VOCATIONAL]
        ).distinct().order_by("school_type", "order", "id")
        self.fields["levels"].initial = SchoolYearLevel.objects.filter(
            school_year=school_year, is_active=True,
            education_level__school_type__in=[School.SchoolType.PRESCHOOL, School.SchoolType.FUNDAMENTAL_1, School.SchoolType.FUNDAMENTAL_2]
        ).values_list("education_level_id", flat=True)

        self.fields["tracks"].queryset = PedagogicalTrack.objects.filter(
            school_type__in=enabled_types, is_active=True
        ).prefetch_related("levels").distinct().order_by("school_type", "domain", "order", "name")
        self.fields["tracks"].initial = SchoolYearTrack.objects.filter(
            school_year=school_year, is_active=True
        ).values_list("track_id", flat=True)

    def clean(self):
        cleaned = super().clean()
        levels = cleaned.get("levels") or []
        tracks = cleaned.get("tracks") or []
        level_ids = {level.id for level in levels}
        for track in tracks:
            track_level_ids = set(track.levels.filter(is_active=True).values_list("education_level_id", flat=True))
            if not track_level_ids:
                self.add_error("tracks", f"La série/filière « {track.name} » n'a aucun niveau référencé.")

        # Ne pas permettre de fermer un niveau ou un parcours déjà utilisé
        # par une classe de cette année. La référence reste modifiable, mais
        # l'ouverture de l'année ne peut pas devenir incohérente avec ses classes.
        selected_level_ids = {level.id for level in levels}
        existing_level_ids = set(
            Classe.objects.filter(
                school=self.school_year.school, school_year=self.school_year,
                pedagogical_track__isnull=True,
            ).values_list("education_level_id", flat=True)
        )
        hidden_levels = existing_level_ids - selected_level_ids
        if hidden_levels:
            names = list(EducationLevel.objects.filter(id__in=hidden_levels).values_list("name", flat=True))
            self.add_error("levels", f"Impossible de fermer un niveau : des classes existent déjà ({', '.join(names)}).")

        selected_track_ids = {track.id for track in tracks}
        existing_track_ids = set(
            Classe.objects.filter(
                school=self.school_year.school, school_year=self.school_year,
                pedagogical_track__isnull=False,
            ).values_list("pedagogical_track_id", flat=True)
        )
        hidden_tracks = existing_track_ids - selected_track_ids
        if hidden_tracks:
            names = list(PedagogicalTrack.objects.filter(id__in=hidden_tracks).values_list("name", flat=True))
            self.add_error("tracks", f"Impossible de fermer une série/filière : des classes existent déjà ({', '.join(names)}).")
        return cleaned

    def save(self):
        levels = self.cleaned_data.get("levels") or []
        tracks = self.cleaned_data.get("tracks") or []
        level_ids = {level.id for level in levels}
        track_ids = {track.id for track in tracks}

        # Les niveaux du fondamental restent configurables ici. Pour le
        # secondaire/professionnel, l'ouverture se fait par contexte réel
        # (série/filière/spécialité), jamais par niveau générique.
        allowed_level_types = [School.SchoolType.PRESCHOOL, School.SchoolType.FUNDAMENTAL_1, School.SchoolType.FUNDAMENTAL_2]
        SchoolYearLevel.objects.filter(
            school_year=self.school_year, education_level__school_type__in=allowed_level_types
        ).update(is_active=False)
        SchoolYearLevel.objects.filter(
            school_year=self.school_year, education_level_id__in=level_ids
        ).update(is_active=True)

        SchoolYearTrack.objects.filter(school_year=self.school_year).update(is_active=False)
        SchoolYearTrack.objects.filter(
            school_year=self.school_year, track_id__in=track_ids
        ).update(is_active=True)
        self.school_year.invalidate_catalog()
        return self.school_year

class EducationLevelSubjectForm(forms.ModelForm):
    """Configure une matière uniquement pour ce niveau.

    La matière est une donnée du programme de ce niveau. L'utilisateur saisit
    directement son nom et ses paramètres ; aucune notion de matière globale
    ou de référence interne n'est exposée dans l'interface.
    """

    # Champ interne conservé pour compatibilité avec les anciennes soumissions.
    # Il n'est jamais affiché dans le formulaire.
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.filter(is_active=True),
        required=False, widget=forms.HiddenInput(), label="Matière",
    )
    name = forms.CharField(
        label="Matière", max_length=100, required=False,
        widget=forms.TextInput(attrs={"class": "kis-input"}),
    )
    weekly_hours_max = forms.DecimalField(
        required=False, max_digits=4, decimal_places=1,
        widget=forms.HiddenInput(), label="Volume horaire / semaine (max)",
    )

    class Meta:
        model = EducationLevelSubject
        fields = ["subject", "name", "weekly_hours", "coefficient", "role", "is_required", "order", "is_active"]
        widgets = {
            "weekly_hours": forms.NumberInput(attrs={"class": "kis-input", "step": "0.5", "min": "0"}),
            "coefficient": forms.NumberInput(attrs={"class": "kis-input", "step": "0.01", "min": "0"}),
            "role": forms.Select(attrs={"class": "kis-select"}),
            "is_required": forms.CheckboxInput(attrs={"class": "kis-checkbox"}),
            "order": forms.NumberInput(attrs={"class": "kis-input", "min": "1"}),
            "is_active": forms.CheckboxInput(attrs={"class": "kis-checkbox"}),
        }
        labels = {"weekly_hours": "Heures / semaine", "coefficient": "Coefficient", "role": "Statut", "is_required": "Obligatoire", "order": "Ordre", "is_active": "Active"}

    def __init__(self, *args, education_level=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.education_level = education_level or getattr(self.instance, "education_level", None)
        if self.instance.pk:
            self.fields["subject"].initial = self.instance.subject_id
            self.fields["name"].initial = self.instance.name or self.instance.subject.name
        if self.education_level and not self.instance.pk:
            last_order = EducationLevelSubject.objects.filter(education_level=self.education_level).order_by("-order").values_list("order", flat=True).first()
            self.fields["order"].initial = (last_order or 0) + 1

    def clean(self):
        cleaned = super().clean()
        name = (cleaned.get("name") or "").strip()
        if not name and cleaned.get("subject"):
            name = cleaned["subject"].name
            cleaned["name"] = name
        if not name:
            self.add_error("name", "Indiquez le nom de la matière.")
        elif self.education_level:
            duplicates = EducationLevelSubject.objects.filter(
                education_level=self.education_level, name__iexact=name
            )
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                self.add_error("name", "Cette matière est déjà associée à ce niveau.")
        weekly_hours = cleaned.get("weekly_hours")
        weekly_hours_max = cleaned.get("weekly_hours_max")
        if weekly_hours is not None and weekly_hours_max is not None and weekly_hours_max < weekly_hours:
            self.add_error("weekly_hours_max", "Le volume horaire maximum doit être supérieur ou égal au volume horaire minimum.")
        return cleaned

    def save(self, commit=True):
        link = super().save(commit=False)
        name = self.cleaned_data["name"].strip()
        subject = self.cleaned_data.get("subject")
        if not subject:
            # Référence technique interne : elle n'est pas un programme global.
            base_code = f"CTX-{getattr(self.education_level, 'id', None) or 'X'}-{link.order}"
            code = base_code
            n = 1
            while Subject.objects.filter(code=code).exists():
                n += 1
                code = f"{base_code}-{n}"
            subject = Subject.objects.filter(name__iexact=name, is_active=True).first()
            if subject is None:
                subject = Subject.objects.create(code=code, name=name, coefficient=link.coefficient or 1, is_active=True)
        link.subject = subject
        link.name = name
        if commit:
            link.save()
        return link


class PreschoolSubjectCopyForm(forms.Form):
    """Choisit un autre niveau préscolaire dont le programme sera recopié."""
    source_level = forms.ModelChoiceField(
        queryset=EducationLevel.objects.none(),
        label="Niveau source",
        empty_label="— Choisir un niveau source —",
        widget=forms.Select(attrs={"class": "kis-select"}),
    )

    def __init__(self, *args, target_level=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_level = target_level
        qs = EducationLevel.objects.filter(
            school_type=School.SchoolType.PRESCHOOL, is_active=True
        ).order_by("order", "name")
        if target_level is not None:
            qs = qs.exclude(pk=target_level.pk)
        self.fields["source_level"].queryset = qs


class TrackLevelSubjectForm(forms.ModelForm):
    """Configure une matière uniquement pour ce niveau de série/filière/spécialité."""

    subject = forms.ModelChoiceField(
        queryset=Subject.objects.filter(is_active=True),
        required=False, widget=forms.HiddenInput(), label="Matière",
    )
    name = forms.CharField(
        label="Matière", max_length=100, required=False,
        widget=forms.TextInput(attrs={"class": "kis-input"}),
    )
    weekly_hours_max = forms.DecimalField(
        required=False, max_digits=4, decimal_places=1,
        widget=forms.HiddenInput(), label="Volume horaire / semaine (max)",
    )

    class Meta:
        model = TrackLevelSubject
        fields = ["subject", "name", "weekly_hours", "coefficient", "role", "is_required", "order", "is_active"]
        widgets = {
            "weekly_hours": forms.NumberInput(attrs={"class": "kis-input", "step": "0.5", "min": "0"}),
            "coefficient": forms.NumberInput(attrs={"class": "kis-input", "step": "0.01", "min": "0"}),
            "role": forms.Select(attrs={"class": "kis-select"}),
            "is_required": forms.CheckboxInput(attrs={"class": "kis-checkbox"}),
            "order": forms.NumberInput(attrs={"class": "kis-input", "min": "1"}),
            "is_active": forms.CheckboxInput(attrs={"class": "kis-checkbox"}),
        }
        labels = {"weekly_hours": "Heures / semaine", "coefficient": "Coefficient", "role": "Statut", "is_required": "Obligatoire", "order": "Ordre", "is_active": "Active"}

    def __init__(self, *args, track_level=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.track_level = track_level or getattr(self.instance, "track_level", None)
        if self.instance.pk:
            self.fields["subject"].initial = self.instance.subject_id
            self.fields["name"].initial = self.instance.name or self.instance.subject.name
        if self.track_level and not self.instance.pk:
            last_order = TrackLevelSubject.objects.filter(track_level=self.track_level).order_by("-order").values_list("order", flat=True).first()
            self.fields["order"].initial = (last_order or 0) + 1

    def clean(self):
        cleaned = super().clean()
        name = (cleaned.get("name") or "").strip()
        if not name and cleaned.get("subject"):
            name = cleaned["subject"].name
            cleaned["name"] = name
        if not name:
            self.add_error("name", "Indiquez le nom de la matière.")
        weekly_hours = cleaned.get("weekly_hours")
        weekly_hours_max = cleaned.get("weekly_hours_max")
        if weekly_hours is not None and weekly_hours_max is not None and weekly_hours_max < weekly_hours:
            self.add_error("weekly_hours_max", "Le volume horaire maximum doit être supérieur ou égal au volume horaire minimum.")
        return cleaned

    def save(self, commit=True):
        link = super().save(commit=False)
        name = self.cleaned_data["name"].strip()
        subject = self.cleaned_data.get("subject")
        if not subject:
            base_code = f"CTX-{getattr(self.track_level, 'id', None) or 'X'}-{link.order}"
            code = base_code
            n = 1
            while Subject.objects.filter(code=code).exists():
                n += 1
                code = f"{base_code}-{n}"
            subject = Subject.objects.filter(name__iexact=name, is_active=True).first()
            if subject is None:
                subject = Subject.objects.create(code=code, name=name, coefficient=link.coefficient or 1, is_active=True)
        link.subject = subject
        link.name = name
        if commit:
            link.save()
        return link
