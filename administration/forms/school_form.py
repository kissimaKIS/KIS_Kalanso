from django import forms

from administration.models import HonorRollRule, School, SchoolTypeActivation


class SchoolForm(forms.ModelForm):
    CURRENCY_CHOICES = [
        ("FCFA", "Franc CFA (FCFA)"),
        ("EUR", "Euro (€)"),
        ("USD", "Dollar américain ($)"),
    ]

    LANGUAGE_CHOICES = [
        ("Français", "Français"),
        ("Bambara", "Bambara"),
        ("English", "English"),
    ]

    currency = forms.ChoiceField(
        label="Monnaie",
        choices=CURRENCY_CHOICES,
        required=True,
        widget=forms.Select(attrs={"class": "kis-select"}),
    )
    language = forms.ChoiceField(
        label="Langue",
        choices=LANGUAGE_CHOICES,
        required=True,
        widget=forms.Select(attrs={"class": "kis-select"}),
    )

    school_types = forms.MultipleChoiceField(
        label="Types d'enseignement activés",
        choices=School.SchoolType.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Sélectionnez un ou plusieurs secteurs pour gérer un établissement ou un complexe scolaire.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Le tableau d’honneur est réglé secteur par secteur, avec le barème
        # propre à chaque secteur. Les champs visibles sont strictement
        # limités au périmètre de la licence de l’établissement.
        is_locked = bool(self.instance and self.instance.pk and self.instance.license_level)
        if is_locked:
            # Le périmètre est verrouillé par la licence : les cases à cocher
            # sont désactivées et n'apparaissent donc pas dans les données
            # soumises. Seul l'état réel de l'établissement fait foi.
            honor_types = list(self.instance.enabled_school_types())
        elif self.is_bound and hasattr(self.data, "getlist"):
            # Le formulaire vient d'être soumis : si une autre erreur de
            # validation force un réaffichage, les secteurs à afficher sont
            # ceux que l'utilisateur vient de cocher/décocher à l'instant,
            # pas l'ancien état enregistré en base — sinon un secteur tout
            # juste décoché continue d'afficher son barème dans la liste.
            selected = self.data.getlist("school_types")
            honor_types = selected or [School.SchoolType.FUNDAMENTAL_1]
        elif self.instance and self.instance.pk:
            honor_types = list(self.instance.enabled_school_types())
        else:
            honor_types = [School.SchoolType.FUNDAMENTAL_1]

        scales = {
            School.SchoolType.PRESCHOOL: 10,
            School.SchoolType.FUNDAMENTAL_1: 10,
            School.SchoolType.FUNDAMENTAL_2: 20,
            School.SchoolType.HIGH_SCHOOL: 20,
            School.SchoolType.VOCATIONAL: 20,
        }
        labels = dict(School.SchoolType.choices)
        defaults = {
            School.SchoolType.PRESCHOOL: 8,
            School.SchoolType.FUNDAMENTAL_1: 8,
            School.SchoolType.FUNDAMENTAL_2: 14,
            School.SchoolType.HIGH_SCHOOL: 14,
            School.SchoolType.VOCATIONAL: 14,
        }
        for school_type in honor_types:
            if school_type not in scales:
                continue
            scale = scales[school_type]
            existing = None
            if self.instance and self.instance.pk:
                existing = self.instance.honor_roll_rules.filter(
                    school_type=school_type, scale=scale, is_active=True
                ).first()
            self.fields[f"honor_threshold_{school_type}"] = forms.DecimalField(
                label=f"{labels.get(school_type, school_type)} /{scale}",
                min_value=0, max_value=scale, required=True,
                initial=existing.threshold if existing else defaults[school_type],
                widget=forms.NumberInput(attrs={
                    "class": "kis-input", "step": "0.01", "min": "0", "max": str(scale),
                }),
                help_text=f"Seuil propre à ce secteur. Barème conservé sur /{scale}, sans conversion.",
            )

        if self.instance and self.instance.pk:
            active = list(self.instance.type_activations.filter(is_active=True).values_list("school_type", flat=True))
            self.fields["school_types"].initial = active or [self.instance.school_type]
            if self.instance.license_level:
                self.fields["school_types"].disabled = True
                self.fields["school_types"].help_text = "Le périmètre est déterminé par la licence et ne peut pas être modifié après l'installation."

    def clean_school_types(self):
        selected = set(self.cleaned_data["school_types"])
        if self.instance and self.instance.pk:
            used_types = set(self.instance.classes.values_list("education_level__school_type", flat=True).distinct())
            removed = used_types - selected
            if removed:
                labels = dict(School.SchoolType.choices)
                names = ", ".join(labels.get(value, value) for value in sorted(removed))
                raise forms.ValidationError(f"Impossible de désactiver {names} : des classes utilisent déjà ce secteur.")
        if not selected:
            raise forms.ValidationError("Au moins un type d'enseignement doit être activé.")
        return list(selected)

    def save(self, commit=True):
        previous_enabled = set(self.instance.enabled_school_types()) if self.instance and self.instance.pk else set()
        # ``school_type`` is NOT NULL in the database. We therefore must set the
        # compatibility field before the first INSERT. Calling ModelForm.save
        # with commit=True here would insert NULL before our multi-type logic
        # gets a chance to update it.
        selected = set(self.cleaned_data["school_types"])
        if self.instance and self.instance.pk and self.instance.license_level:
            selected = set(self.instance.enabled_school_types())
        school = super().save(commit=False)
        school.school_type = (
            self.instance.school_type if self.instance and self.instance.pk and self.instance.school_type in selected
            else sorted(selected)[0]
        )

        if commit:
            school.save()
            SchoolTypeActivation.objects.filter(school=school).exclude(school_type__in=selected).update(is_active=False)

            scales = {
                School.SchoolType.PRESCHOOL: 10,
                School.SchoolType.FUNDAMENTAL_1: 10,
                School.SchoolType.FUNDAMENTAL_2: 20,
                School.SchoolType.HIGH_SCHOOL: 20,
                School.SchoolType.VOCATIONAL: 20,
            }
            # Les seuils sont enregistrés indépendamment. Aucun seuil n'est
            # converti d'un barème vers un autre.
            for school_type in selected:
                scale = scales.get(school_type)
                field_name = f"honor_threshold_{school_type}"
                if scale is None or field_name not in self.cleaned_data:
                    continue
                threshold = self.cleaned_data[field_name]
                HonorRollRule.objects.update_or_create(
                    school=school,
                    school_type=school_type,
                    scale=scale,
                    defaults={"threshold": threshold, "is_active": True},
                )
            # Les règles des secteurs qui ne sont plus activés restent en base
            # pour l'historique mais ne participent plus au paramétrage actif.
            HonorRollRule.objects.filter(school=school).exclude(
                school_type__in=selected
            ).update(is_active=False)
            for school_type in selected:
                SchoolTypeActivation.objects.update_or_create(
                    school=school, school_type=school_type, defaults={"is_active": True, "is_legacy": False}
                )

            # Les secteurs activés pilotent immédiatement le catalogue de chaque
            # année scolaire existante. Cela évite qu'une nouvelle activation
            # reste invisible dans la création des classes.
            from pedagogie.services.catalog import sync_school_catalogs
            sync_school_catalogs(school)
            # Une évolution des secteurs modifie le périmètre du référentiel
            # de l'année. Elle doit donc remettre les années concernées
            # en « À vérifier » afin que l'administrateur puisse contrôler
            # les nouveaux niveaux/parcours avant de créer des classes.
            if previous_enabled and previous_enabled != selected:
                for school_year in school.school_years.all():
                    school_year.invalidate_catalog()
        return school

    class Meta:
        model = School
        fields = [
            "name",
            "code",
            "school_types",
            "address",
            "city",
            "phone",
            "email",
            "logo",
            "motto",
            "ministry_name",
            "academy_name",
            "cap_name",
            "currency",
            "language",
        ]
        widgets = {
            "ministry_name": forms.TextInput(attrs={"class": "kis-input", "placeholder": "Ministère de tutelle"}),
            "name": forms.TextInput(attrs={
                "class": "kis-input",
                "placeholder": "Nom complet de l'établissement",
                "autocomplete": "organization",
            }),
            "code": forms.TextInput(attrs={
                "class": "kis-input",
                "placeholder": "Ex. ILE",
                "autocomplete": "organization-title",
            }),
            "address": forms.TextInput(attrs={
                "class": "kis-input",
                "placeholder": "Adresse de l'établissement",
                "autocomplete": "street-address",
            }),
            "city": forms.TextInput(attrs={
                "class": "kis-input",
                "placeholder": "Ville",
                "autocomplete": "address-level2",
            }),
            "phone": forms.TextInput(attrs={
                "class": "kis-input",
                "placeholder": "+223 XX XX XX XX",
                "autocomplete": "tel",
                "inputmode": "tel",
            }),
            "email": forms.EmailInput(attrs={
                "class": "kis-input",
                "placeholder": "contact@ecole.ml",
                "autocomplete": "email",
            }),
            "logo": forms.ClearableFileInput(attrs={
                "class": "kis-file-input",
                "accept": "image/png,image/jpeg,image/webp",
            }),
            "motto": forms.TextInput(attrs={
                "class": "kis-input",
                "placeholder": "Devise ou slogan de l'établissement",
            }),
            "academy_name": forms.TextInput(attrs={
                "class": "kis-input",
                "placeholder": "Ex. Académie d'enseignement de Koutiala",
            }),
            "cap_name": forms.TextInput(attrs={
                "class": "kis-input",
                "placeholder": "Ex. CAP de Koutiala",
            }),
            "currency": forms.Select(attrs={
                "class": "kis-select",
            }),
            "language": forms.Select(attrs={
                "class": "kis-select",
            }),
        }
