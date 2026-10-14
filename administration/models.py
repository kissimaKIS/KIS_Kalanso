from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, When, Value, IntegerField
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    ADMIN = "ADMIN", _("Administrateur")
    PROMOTER = "PROMOTER", _("Promoteur")
    DIRECTOR = "DIRECTOR", _("Directeur")
    MANAGER = "MANAGER", _("Gérant")
    ACCOUNTANT = "ACCOUNTANT", _("Comptable")
    STUDIES_DIRECTOR = "STUDIES_DIRECTOR", _("Directeur des études")
    SECRETARY = "SECRETARY", _("Secrétaire")
    TEACHER = "TEACHER", _("Professeur / Enseignant")
    STUDENT = "STUDENT", _("Élève")
    PARENT = "PARENT", _("Parent")
    # Compatibilité avec les données historiques.
    PROF = "PROF", _("Professeur")


class UserRoleAssignment(models.Model):
    """Rôle métier attribué à un utilisateur. Un utilisateur peut en cumuler plusieurs."""

    user = models.ForeignKey("User", on_delete=models.CASCADE, related_name="role_assignments")
    role = models.CharField(max_length=30, choices=Role.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="unique_user_role_assignment"),
        ]
        verbose_name = _("Rôle utilisateur")
        verbose_name_plural = _("Rôles utilisateurs")

    def __str__(self):
        return f"{self.user} — {self.get_role_display()}"


class User(AbstractUser):
    is_admin = models.BooleanField(default=False)
    is_prof = models.BooleanField(default=False)
    is_student = models.BooleanField(default=False)
    is_secretary = models.BooleanField(default=False)

    def assigned_roles(self):
        return set(self.role_assignments.values_list("role", flat=True))

    def has_role(self, role):
        if self.is_superuser:
            return True
        role = str(role).upper()
        if role in self.assigned_roles():
            return True
        legacy = {
            "ADMIN": self.is_admin,
            "PROF": self.is_prof,
            "TEACHER": self.is_prof,
            "SECRETARY": self.is_secretary,
            "STUDENT": self.is_student,
        }
        return legacy.get(role, False)

    def has_admin_role(self):
        return self.is_superuser or self.is_admin

    def has_prof_role(self):
        return self.is_prof

    def has_student_role(self):
        return self.is_student

    def has_secretary_role(self):
        return self.is_secretary

    def __str__(self):
        return self.get_full_name() or self.username


class School(models.Model):
    class SchoolType(models.TextChoices):
        PRESCHOOL = "preschool", _("Préscolaire")
        FUNDAMENTAL_1 = "fundamental_1", _("Fondamentale 1")
        FUNDAMENTAL_2 = "fundamental_2", _("Fondamentale 2")
        HIGH_SCHOOL = "high_school", _("Lycée")
        VOCATIONAL = "vocational", _("Centre professionnel")

    class LicenseLevel(models.TextChoices):
        FUNDAMENTAL = "1", _("1 — École fondamentale")
        SECONDARY_OR_VOCATIONAL = "2", _("2 — Lycée ou Centre professionnel")
        SECONDARY_AND_VOCATIONAL = "3", _("3 — Lycée et Centre professionnel")
        COMPLEX = "4", _("4 — Complexe")

    name = models.CharField(max_length=200, verbose_name=_("Nom de l'établissement"))
    code = models.CharField(max_length=20, unique=True, verbose_name=_("Code / Sigle"))
    license_level = models.CharField(max_length=1, choices=LicenseLevel.choices, blank=True, default="", verbose_name=_("Niveau de licence"))
    # Conservé pour compatibilité avec les anciennes données et comme type principal.
    # La configuration réelle peut désormais activer plusieurs types via SchoolTypeActivation.
    school_type = models.CharField(max_length=30, choices=SchoolType.choices, verbose_name=_("Type principal"))
    address = models.CharField(max_length=255, blank=True, verbose_name=_("Adresse"))
    city = models.CharField(max_length=100, blank=True, verbose_name=_("Ville"))
    phone = models.CharField(max_length=30, blank=True, verbose_name=_("Téléphone"))
    email = models.EmailField(blank=True, verbose_name=_("Email"))
    logo = models.ImageField(upload_to="school/logo/", blank=True, null=True, verbose_name=_("Logo"))
    motto = models.CharField(max_length=255, blank=True, verbose_name=_("Devise"))
    ministry_name = models.CharField(max_length=150, blank=True, verbose_name=_("Ministère"))
    academy_name = models.CharField(
        max_length=150, blank=True,
        verbose_name=_("Académie d'enseignement"),
    )
    cap_name = models.CharField(
        max_length=150, blank=True,
        verbose_name=_("CAP"),
        help_text=_("Centre d'Animation Pédagogique — applicable à la Fondamentale 1 et 2."),
    )
    currency = models.CharField(max_length=10, default="FCFA", verbose_name=_("Monnaie"))
    language = models.CharField(max_length=30, default="Français", verbose_name=_("Langue"))
    honor_roll_threshold = models.DecimalField(
        max_digits=5, decimal_places=2, default=14,
        verbose_name=_("Seuil du tableau d’honneur"),
        help_text=_("Champ historique de compatibilité. Les seuils actuels sont réglés séparément par secteur et par barème, sans conversion."),
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Actif"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("Établissement")
        verbose_name_plural = _("Établissements")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def has_school_type(self, school_type):
        return school_type in self.enabled_school_types()

    def enabled_school_types(self):
        # Les activations explicites pilotent la configuration dès qu'il en
        # existe une. Les lignes legacy ne servent qu'à conserver le
        # comportement des anciennes écoles qui n'ont pas encore été
        # reconfigurées.
        explicit = list(
            self.type_activations.filter(is_active=True, is_legacy=False)
            .values_list("school_type", flat=True)
            .order_by(
                Case(
                    When(school_type=self.SchoolType.PRESCHOOL, then=Value(1)),
                    When(school_type=self.SchoolType.FUNDAMENTAL_1, then=Value(2)),
                    When(school_type=self.SchoolType.FUNDAMENTAL_2, then=Value(3)),
                    When(school_type=self.SchoolType.HIGH_SCHOOL, then=Value(4)),
                    When(school_type=self.SchoolType.VOCATIONAL, then=Value(5)),
                    default=Value(99), output_field=IntegerField(),
                )
            )
        )
        if explicit:
            return explicit

        legacy = list(
            self.type_activations.filter(is_active=True, is_legacy=True)
            .values_list("school_type", flat=True)
            .order_by(
                Case(
                    When(school_type=self.SchoolType.PRESCHOOL, then=Value(1)),
                    When(school_type=self.SchoolType.FUNDAMENTAL_1, then=Value(2)),
                    When(school_type=self.SchoolType.FUNDAMENTAL_2, then=Value(3)),
                    When(school_type=self.SchoolType.HIGH_SCHOOL, then=Value(4)),
                    When(school_type=self.SchoolType.VOCATIONAL, then=Value(5)),
                    default=Value(99), output_field=IntegerField(),
                )
            )
        )
        if legacy:
            return legacy

        # Compatibilité avec les écoles créées directement par code/admin
        # avant l'existence des activations.
        return [self.school_type] if self.school_type else []

    def __str__(self):
        return f"{self.code} - {self.name}"


class SchoolTypeActivation(models.Model):
    """Types d'enseignement effectivement activés dans un établissement.

    Un établissement peut activer plusieurs types simultanément afin de gérer
    un complexe scolaire dans une seule installation KIS Kalanso.
    """

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="type_activations", verbose_name=_("Établissement"))
    school_type = models.CharField(max_length=30, choices=School.SchoolType.choices, verbose_name=_("Type d'enseignement"))
    is_active = models.BooleanField(default=True, verbose_name=_("Actif"))
    # True uniquement pour les activations créées automatiquement lors de la
    # migration de l'ancien champ School.school_type. Elles servent de
    # compatibilité pour les anciennes écoles, mais ne doivent pas être
    # interprétées comme une sélection explicite dans la nouvelle configuration.
    is_legacy = models.BooleanField(default=False, verbose_name=_("Compatibilité ancienne configuration"))
    activated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["school_type"]
        verbose_name = _("Type d'enseignement activé")
        verbose_name_plural = _("Types d'enseignement activés")
        constraints = [
            models.UniqueConstraint(fields=["school", "school_type"], name="unique_school_school_type_activation"),
        ]

    def __str__(self):
        return f"{self.school} — {self.get_school_type_display()}"


class HonorRollRule(models.Model):
    """Seuil du tableau d'honneur, indépendant pour chaque contexte et barème."""

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="honor_roll_rules", verbose_name=_("Établissement"))
    school_type = models.CharField(max_length=30, choices=School.SchoolType.choices, verbose_name=_("Contexte pédagogique"))
    scale = models.PositiveSmallIntegerField(choices=((10, "/10"), (20, "/20")), verbose_name=_("Barème"))
    threshold = models.DecimalField(max_digits=5, decimal_places=2, verbose_name=_("Seuil"))
    is_active = models.BooleanField(default=True, verbose_name=_("Actif"))

    class Meta:
        ordering = ["school_type", "scale"]
        constraints = [
            models.UniqueConstraint(fields=["school", "school_type", "scale"], name="unique_school_honor_roll_rule"),
        ]
        verbose_name = _("Règle du tableau d'honneur")
        verbose_name_plural = _("Règles du tableau d'honneur")

    def clean(self):
        if self.scale == 10 and not (0 <= self.threshold <= 10):
            raise ValidationError({"threshold": _("Le seuil doit être compris entre 0 et 10.")})
        if self.scale == 20 and not (0 <= self.threshold <= 20):
            raise ValidationError({"threshold": _("Le seuil doit être compris entre 0 et 20.")})

    def __str__(self):
        return f"{self.school} — {self.get_school_type_display()} — {self.threshold}/{self.scale}"


class SchoolYear(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="school_years",
        verbose_name=_("Établissement"),
    )
    start_date = models.DateField(verbose_name=_("Date de début"))
    end_date = models.DateField(verbose_name=_("Date de fin"))
    name = models.CharField(max_length=20, editable=False, verbose_name=_("Année scolaire"))
    is_active = models.BooleanField(default=False, verbose_name=_("Année active"))
    is_closed = models.BooleanField(default=False, verbose_name=_("Année clôturée"))
    is_archive = models.BooleanField(
        default=False, verbose_name=_("Année antérieure reprise"),
        help_text=_("Année d'avant KIS Kalanso, créée seulement pour reprendre les soldes impayés (reliquats)."),
    )
    catalog_validated_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Référentiel validé le"))
    catalog_validated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="validated_school_year_catalogs", verbose_name=_("Référentiel validé par")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date"]
        verbose_name = _("Année scolaire")
        verbose_name_plural = _("Années scolaires")
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="unique_school_year_name"),
        ]

    def clean(self):
        errors = {}
        if self.start_date and self.end_date:
            if self.end_date <= self.start_date:
                errors["end_date"] = _("La date de fin doit être postérieure à la date de début.")
            elif self.end_date.year != self.start_date.year + 1:
                errors["end_date"] = _("Une année scolaire doit couvrir deux années civiles consécutives (ex. 2026-2027).")
        if self.is_closed and self.is_active:
            raise ValidationError(_("Une année clôturée ne peut pas être active."))
        if self.pk is None and self.school_id and not self.is_archive:
            blocker = SchoolYear.creation_blocker(self.school_id, self.start_date)
            if blocker:
                raise ValidationError(blocker)
        if self.is_active and not self.is_closed and self.school_id:
            existing = SchoolYear.objects.filter(
                school_id=self.school_id, is_active=True, is_closed=False
            ).exclude(pk=self.pk)
            if existing.exists():
                errors["is_active"] = _(
                    "Une année scolaire est déjà active. Elle doit être clôturée avant de créer la suivante."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.name = f"{self.start_date.year}-{self.end_date.year}"
        self.full_clean()
        if self.is_archive:
            # Une année reprise est toujours clôturée : elle ne sert qu'aux soldes antérieurs.
            self.is_active, self.is_closed = False, True
        if self.is_active:
            SchoolYear.objects.exclude(pk=self.pk).filter(school=self.school, is_active=True).update(is_active=False)
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.is_archive:
            # Le référentiel pédagogique est chargé automatiquement pour le type
            # d'établissement, sans créer de classes réelles.
            from pedagogie.services.catalog import initialize_school_year_catalog
            initialize_school_year_catalog(self)

    @classmethod
    def creation_blocker(cls, school_id, start_date=None):
        """Raison empêchant de créer une nouvelle année, ou ``None``.

        Une nouvelle année ne peut être créée qu'une fois toutes les années
        précédentes terminées : clôturées, et la nouvelle doit commencer après
        la date de fin de la dernière (pas de chevauchement).
        """
        years = cls.objects.filter(school_id=school_id, is_archive=False)
        open_year = years.filter(is_closed=False).order_by("-start_date").first()
        if open_year:
            return _(
                "L'année scolaire %(name)s n'est pas terminée. Clôturez-la avant de créer la suivante."
            ) % {"name": open_year.name}
        last = years.order_by("-end_date").first()
        if last and start_date and start_date <= last.end_date:
            return _(
                "La nouvelle année doit commencer après la fin de l'année %(name)s (le %(end)s)."
            ) % {"name": last.name, "end": last.end_date.strftime("%d/%m/%Y")}
        return None

    @property
    def is_current(self):
        return self.is_active and not self.is_closed

    @property
    def catalog_is_validated(self):
        return self.catalog_validated_at is not None

    def invalidate_catalog(self):
        self.catalog_validated_at = None
        self.catalog_validated_by = None
        self.save(update_fields=["catalog_validated_at", "catalog_validated_by", "updated_at"])

    def validate_catalog(self, user=None):
        self.catalog_validated_at = timezone.now()
        self.catalog_validated_by = user if getattr(user, "pk", None) else None
        self.save(update_fields=["catalog_validated_at", "catalog_validated_by", "updated_at"])

    def __str__(self):
        return f"{self.name} — {self.school.code}"


class Teacher(models.Model):
    class ContractType(models.TextChoices):
        PERMANENT = "permanent", _("Permanent")
        VACATAIRE = "vacataire", _("Vacataire")

    class PedagogicalProfile(models.TextChoices):
        GENERALISTE = "generaliste", _("Généraliste")
        SPECIALISTE = "specialiste", _("Spécialiste")
        FORMATEUR_METIER = "formateur_metier", _("Formateur métier")

    # La fiche enseignant porte sa propre identité. Le compte de connexion est
    # facultatif : il est créé explicitement dans Administration → Utilisateurs
    # puis rattaché à la fiche (rôle Professeur). Créer un enseignant ne crée
    # donc plus aucun compte utilisateur.
    user = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="teacher_profile", verbose_name=_("Compte utilisateur"),
    )
    first_name = models.CharField(max_length=150, blank=True, default="", verbose_name=_("Prénom(s)"))
    last_name = models.CharField(max_length=150, blank=True, default="", verbose_name=_("Nom"))
    email = models.EmailField(blank=True, default="", verbose_name=_("Email"))
    employee_number = models.CharField(max_length=30, unique=True, verbose_name=_("Matricule"))
    address = models.CharField(max_length=255, blank=True, verbose_name=_("Adresse"))
    date_of_birth = models.DateField(null=True, blank=True, verbose_name=_("Date de naissance"))
    photo = models.ImageField(upload_to="teachers/photos/", blank=True, null=True, verbose_name=_("Photo"))
    specialty = models.CharField(max_length=100, blank=True, verbose_name=_("Spécialité"))
    qualification = models.CharField(max_length=100, blank=True, verbose_name=_("Diplôme / Qualification"))
    hire_date = models.DateField(null=True, blank=True, verbose_name=_("Date de recrutement / prise de fonction"))
    phone = models.CharField(max_length=30, blank=True, verbose_name=_("Téléphone"))
    contract_type = models.CharField(max_length=20, choices=ContractType.choices, default=ContractType.PERMANENT, verbose_name=_("Statut"))
    pedagogical_profile = models.CharField(max_length=30, choices=PedagogicalProfile.choices, blank=True, default="", verbose_name=_("Profil pédagogique"))
    monthly_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name=_("Salaire mensuel fixe"))
    weekly_obligation = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name=_("Obligation hebdomadaire (h)"))
    complementary_hours_allowed = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name=_("Heures complémentaires autorisées (h)"))
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name=_("Taux horaire"))
    hours_cap = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name=_("Plafond d'heures (h)"))
    contract_start_date = models.DateField(null=True, blank=True, verbose_name=_("Début du contrat"))
    contract_end_date = models.DateField(null=True, blank=True, verbose_name=_("Fin du contrat"))
    is_active = models.BooleanField(default=True, verbose_name=_("Actif"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.contract_type == self.ContractType.PERMANENT:
            if self.hourly_rate is not None:
                raise ValidationError(_("Un enseignant permanent ne peut pas avoir de taux horaire."))
            if self.contract_end_date and self.contract_start_date and self.contract_end_date < self.contract_start_date:
                raise ValidationError(_("La fin du contrat ne peut pas précéder son début."))
        if self.contract_type == self.ContractType.VACATAIRE:
            if self.monthly_salary is not None:
                raise ValidationError(_("Un vacataire ne peut pas avoir de salaire mensuel fixe."))
            if self.contract_end_date and self.contract_start_date and self.contract_end_date < self.contract_start_date:
                raise ValidationError(_("La fin du contrat ne peut pas précéder son début."))

    class Meta:
        ordering = ["last_name", "first_name"]
        verbose_name = _("Enseignant")
        verbose_name_plural = _("Enseignants")

    @property
    def full_name(self):
        name = f"{self.first_name} {self.last_name}".strip()
        if name:
            return name
        if self.user_id:
            return self.user.get_full_name() or self.user.username
        return self.employee_number

    def get_full_name(self):
        return self.full_name

    def __str__(self):
        return self.full_name


class OtherPersonnel(models.Model):
    """Membre du personnel non enseignant.

    Ce modèle est volontairement séparé de Teacher : un agent administratif,
    de surveillance, d'entretien, etc. ne devient pas un enseignant sans
    affectation. Il ne crée pas de compte utilisateur automatiquement.
    """
    class ContractType(models.TextChoices):
        PERMANENT = "permanent", _("Permanent")
        CONTRACTUEL = "contractuel", _("Contractuel")
        VACATAIRE = "vacataire", _("Vacataire")
        TEMPORAIRE = "temporaire", _("Temporaire")

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="other_personnel", verbose_name=_("Établissement"))
    employee_number = models.CharField(max_length=30, unique=True, verbose_name=_("Matricule"))
    first_name = models.CharField(max_length=100, verbose_name=_("Prénom(s)"))
    last_name = models.CharField(max_length=100, verbose_name=_("Nom"))
    function = models.CharField(max_length=120, verbose_name=_("Fonction"))
    contract_type = models.CharField(max_length=20, choices=ContractType.choices, default=ContractType.PERMANENT, verbose_name=_("Statut"))
    phone = models.CharField(max_length=30, blank=True, verbose_name=_("Téléphone"))
    email = models.EmailField(blank=True, verbose_name=_("Email"))
    address = models.CharField(max_length=255, blank=True, verbose_name=_("Adresse"))
    photo = models.ImageField(upload_to="other_personnel/photos/", blank=True, null=True, verbose_name=_("Photo"))
    date_of_birth = models.DateField(null=True, blank=True, verbose_name=_("Date de naissance"))
    hire_date = models.DateField(null=True, blank=True, verbose_name=_("Date de recrutement / prise de fonction"))
    is_active = models.BooleanField(default=True, verbose_name=_("Actif"))
    monthly_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name=_("Salaire mensuel"))
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name=_("Taux horaire"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        verbose_name = _("Autre membre du personnel")
        verbose_name_plural = _("Autres membres du personnel")

    def clean(self):
        super().clean()
        if self.date_of_birth and self.date_of_birth > timezone.localdate():
            raise ValidationError(_("La date de naissance ne peut pas être dans le futur."))
        if self.monthly_salary is not None and self.monthly_salary < 0:
            raise ValidationError({"monthly_salary": _("Le salaire mensuel ne peut pas être négatif.")})
        if self.hourly_rate is not None and self.hourly_rate < 0:
            raise ValidationError({"hourly_rate": _("Le taux horaire ne peut pas être négatif.")})
        if self.contract_type == self.ContractType.VACATAIRE and self.monthly_salary is not None:
            raise ValidationError({"monthly_salary": _("Un vacataire ne peut pas avoir un salaire mensuel fixe.")})

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip()


class OtherPersonnelPayment(models.Model):
    """Paiement effectivement versé à un membre du personnel non enseignant."""
    personnel = models.ForeignKey(OtherPersonnel, on_delete=models.PROTECT, related_name="payments", verbose_name="Personnel")
    school_year = models.ForeignKey(SchoolYear, on_delete=models.PROTECT, related_name="other_personnel_payments", verbose_name="Année scolaire")
    period = models.CharField(max_length=30, verbose_name="Période")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Montant payé")
    paid_at = models.DateField(default=timezone.localdate, verbose_name="Date de paiement")
    note = models.CharField(max_length=255, blank=True, verbose_name="Observation")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_at", "personnel__last_name", "personnel__first_name"]
        constraints = [models.UniqueConstraint(fields=["personnel", "school_year", "period"], name="unique_other_personnel_payment_period")]
        verbose_name = "Paiement autre personnel"
        verbose_name_plural = "Paiements autre personnel"

    def clean(self):
        super().clean()
        if self.amount is None or self.amount <= 0:
            raise ValidationError("Le montant payé doit être supérieur à zéro.")
        if self.personnel_id and self.school_year_id and self.personnel.school_id != self.school_year.school_id:
            raise ValidationError("Le personnel et l'année scolaire doivent appartenir au même établissement.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class TeacherPayment(models.Model):
    """Paiement effectivement versé à un enseignant pour une période."""
    teacher = models.ForeignKey(Teacher, on_delete=models.PROTECT, related_name="payments")
    school_year = models.ForeignKey(SchoolYear, on_delete=models.PROTECT, related_name="teacher_payments")
    period = models.CharField(max_length=30, verbose_name="Période")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Montant payé")
    paid_at = models.DateField(default=timezone.localdate, verbose_name="Date de paiement")
    note = models.CharField(max_length=255, blank=True, verbose_name="Observation")
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["-paid_at","teacher__last_name","teacher__first_name"]
        constraints=[models.UniqueConstraint(fields=["teacher","school_year","period"],name="unique_teacher_payment_period")]
        verbose_name="Paiement enseignant"; verbose_name_plural="Paiements enseignants"
    def clean(self):
        if self.amount is None or self.amount <= 0: raise ValidationError("Le montant payé doit être supérieur à zéro.")
    def save(self,*args,**kwargs): self.full_clean(); return super().save(*args,**kwargs)


class CorrectionLog(models.Model):
    """Trace de chaque correction faite par la direction (V5-10).

    Une suppression ou une annulation ne laisse ainsi jamais de « trou »
    inexpliqué : on garde qui, quand, quoi, le montant et le motif. Le numéro
    d'un reçu annulé reste réservé (la numérotation n'est jamais réutilisée).
    """

    class Action(models.TextChoices):
        PAYMENT_CANCEL = "payment_cancel", "Annulation de paiement"
        INVOICE_DELETE = "invoice_delete", "Suppression de facture"
        CLASS_CHANGE = "class_change", "Changement de classe"
        ENROLLMENT_DELETE = "enrollment_delete", "Suppression d'inscription"
        STUDENT_DELETE = "student_delete", "Suppression d'élève"
        STUDENT_MERGE = "student_merge", "Fusion de fiches élève"
        MATRICULES = "matricules", "Génération des matricules"
        SALARY_CANCEL = "salary_cancel", "Annulation de paiements de salaire"

    action = models.CharField(max_length=30, choices=Action.choices, verbose_name="Action")
    description = models.TextField(verbose_name="Détail")
    reason = models.TextField(verbose_name="Motif")
    amount = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True, verbose_name="Montant")
    receipt_number = models.CharField(max_length=40, blank=True, verbose_name="N° de reçu concerné")
    student_label = models.CharField(max_length=200, blank=True, verbose_name="Élève")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="corrections")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Correction"
        verbose_name_plural = "Journal des corrections"

    def __str__(self):
        return f"{self.get_action_display()} — {self.student_label}"
