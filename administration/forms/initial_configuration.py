from django import forms
from administration.models import School


class InitialConfigurationForm(forms.Form):
    license_level = forms.ChoiceField(label="Niveau de licence", choices=School.LicenseLevel.choices, widget=forms.RadioSelect)
    secondary_choice = forms.ChoiceField(
        label="Secteur secondaire / professionnel",
        choices=[("", "— Sélectionner —"), (School.SchoolType.HIGH_SCHOOL, "Lycée"), (School.SchoolType.VOCATIONAL, "Centre professionnel")],
        required=False,
    )
    name = forms.CharField(label="Nom de l'établissement", max_length=200)
    code = forms.CharField(label="Code / Sigle", max_length=20)
    ministry_name = forms.CharField(label="Ministère", max_length=150, required=False)
    academy_name = forms.CharField(label="Académie", max_length=150, required=False)
    cap_name = forms.CharField(label="Centre d'Animation Pédagogique", max_length=150, required=False)
    address = forms.CharField(label="Adresse", max_length=255, required=False)
    city = forms.CharField(label="Ville", max_length=100, required=False)
    phone = forms.CharField(label="Téléphone", max_length=30, required=False)
    email = forms.EmailField(label="E-mail", required=False)
    logo = forms.ImageField(label="Logo", required=False)
    motto = forms.CharField(label="Devise", max_length=255, required=False)
    currency = forms.ChoiceField(label="Monnaie", choices=[("FCFA", "Franc CFA (FCFA)"), ("EUR", "Euro (€)"), ("USD", "Dollar américain ($)")])
    school_year_start = forms.DateField(label="Début de l'année scolaire", widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    school_year_end = forms.DateField(label="Fin de l'année scolaire", widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    threshold_preschool_10 = forms.DecimalField(label="Préscolaire /10", min_value=0, max_value=10, required=False, initial=8)
    threshold_f1_10 = forms.DecimalField(label="Fondamentale 1 /10", min_value=0, max_value=10, required=False, initial=8)
    threshold_f2_20 = forms.DecimalField(label="Fondamentale 2 /20", min_value=0, max_value=20, required=False, initial=14)
    threshold_high_20 = forms.DecimalField(label="Lycée /20", min_value=0, max_value=20, required=False, initial=14)
    threshold_voc_20 = forms.DecimalField(label="Centre professionnel /20", min_value=0, max_value=20, required=False, initial=14)

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("school_year_start"), cleaned.get("school_year_end")
        if start and end and end <= start:
            self.add_error("school_year_end", "La date de fin doit être postérieure à la date de début.")
        elif start and end and end.year != start.year + 1:
            self.add_error("school_year_end", "Une année scolaire doit couvrir deux années civiles consécutives (ex. 2026-2027).")
        level = cleaned.get("license_level")
        secondary = cleaned.get("secondary_choice")
        if level == School.LicenseLevel.SECONDARY_OR_VOCATIONAL and not secondary:
            self.add_error("secondary_choice", "Choisissez Lycée ou Centre professionnel.")
        if level != School.LicenseLevel.SECONDARY_OR_VOCATIONAL:
            cleaned["secondary_choice"] = ""
        if level in (School.LicenseLevel.SECONDARY_OR_VOCATIONAL, School.LicenseLevel.SECONDARY_AND_VOCATIONAL):
            cleaned["cap_name"] = ""
        return cleaned

    def selected_types(self):
        level = self.cleaned_data.get("license_level")
        secondary = self.cleaned_data.get("secondary_choice")
        if level == School.LicenseLevel.FUNDAMENTAL:
            return [School.SchoolType.PRESCHOOL, School.SchoolType.FUNDAMENTAL_1, School.SchoolType.FUNDAMENTAL_2]
        if level == School.LicenseLevel.SECONDARY_OR_VOCATIONAL:
            return [secondary]
        if level == School.LicenseLevel.SECONDARY_AND_VOCATIONAL:
            return [School.SchoolType.HIGH_SCHOOL, School.SchoolType.VOCATIONAL]
        return [School.SchoolType.PRESCHOOL, School.SchoolType.FUNDAMENTAL_1, School.SchoolType.FUNDAMENTAL_2, School.SchoolType.HIGH_SCHOOL, School.SchoolType.VOCATIONAL]


class InitialOptionForm(forms.Form):
    name = forms.CharField(max_length=100, label="Option")
    amount = forms.DecimalField(min_value=0, max_digits=10, decimal_places=0, label="Montant")


# Les options sont ajoutées une par une dans une modale. Le formset reste un
# conteneur technique invisible pour transporter les options vers le POST final.
InitialOptionFormSet = forms.formset_factory(InitialOptionForm, extra=0, can_delete=True)


class InitialBaseFeesForm(forms.Form):
    """Deux tarifs de base par secteur activé : inscription et scolarité."""

    def __init__(self, *args, school_types=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.school_types = list(school_types or [])
        all_types = [choice[0] for choice in School.SchoolType.choices]
        for school_type in all_types:
            required = school_type in self.school_types
            self.fields[f"{school_type}_registration"] = forms.DecimalField(
                label="Inscription", min_value=0, max_digits=10, decimal_places=0, required=required
            )
            self.fields[f"{school_type}_tuition"] = forms.DecimalField(
                label="Scolarité", min_value=0, max_digits=10, decimal_places=0, required=required
            )
            # Détail facultatif de l'inscription en postes (inscription, manuel, uniformes…).
            for index in range(self.PARTS):
                self.fields[f"{school_type}_part_name_{index}"] = forms.CharField(
                    label="Poste", max_length=100, required=False,
                    widget=forms.TextInput(attrs={"placeholder": "Ex. Frais d'inscription" if index == 0 else "Ex. Manuel, 2 uniformes…"}),
                )
                self.fields[f"{school_type}_part_amount_{index}"] = forms.DecimalField(
                    label="Montant", min_value=1, max_digits=10, decimal_places=0, required=False,
                )

    PARTS = 4

    def registration_parts(self, school_type):
        """[(nom, montant)] saisis pour le détail de l'inscription d'un secteur."""
        data = getattr(self, "cleaned_data", {})
        rows = []
        for index in range(self.PARTS):
            name = (data.get(f"{school_type}_part_name_{index}") or "").strip()
            amount = data.get(f"{school_type}_part_amount_{index}")
            if name or amount:
                rows.append((name, amount))
        return rows

    def part_fields(self, school_type):
        return [(self[f"{school_type}_part_name_{i}"], self[f"{school_type}_part_amount_{i}"]) for i in range(self.PARTS)]

    def clean(self):
        cleaned = super().clean()
        for school_type in self.school_types:
            rows = self.registration_parts(school_type)
            if not rows:
                continue
            for index, (name, amount) in enumerate(rows):
                if not name or not amount:
                    self.add_error(f"{school_type}_registration", "Chaque poste du détail doit avoir un nom et un montant.")
                    break
            else:
                total = sum(amount for _, amount in rows)
                registration = cleaned.get(f"{school_type}_registration")
                if registration is not None and total != registration:
                    self.add_error(
                        f"{school_type}_registration",
                        f"Le total des postes ({total:,.0f}) doit être égal au montant de l'inscription ({registration:,.0f}).".replace(",", " "),
                    )
        return cleaned

    def sector_label(self, school_type):
        return dict(School.SchoolType.choices).get(school_type, school_type)
