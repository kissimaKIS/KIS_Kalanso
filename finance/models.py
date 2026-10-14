from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models
from pedagogie.models import EducationLevel
from administration.models import School
from django.db.models import Sum
from pedagogie.models import Enrollment, Classe
from administration.models import SchoolYear
from common.services.numbering_service import NumberingService


class FeeType(models.Model):
    class Category(models.TextChoices):
        REGISTRATION = "registration", "Frais d'inscription"
        REENROLLMENT = "reenrollment", "Frais de réinscription"
        TUITION = "tuition", "Frais de scolarité"
        OPTIONAL = "optional", "Frais optionnel"
        ARREARS = "arrears", "Reliquat antérieur"

    class RegistrationScope(models.TextChoices):
        ANNUAL = "annual", "Année scolaire"
        CYCLE = "cycle", "Cycle"

    name = models.CharField(max_length=100, verbose_name="Type de frais")
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.TUITION,
        verbose_name="Catégorie",
    )
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name="fee_types", null=True, blank=True, verbose_name="Classe (facultatif)")
    education_level = models.ForeignKey(
        EducationLevel, on_delete=models.PROTECT, related_name="fee_types",
        null=True, blank=True, verbose_name="Niveau pédagogique (facultatif)",
    )
    school_type = models.CharField(
        max_length=30, choices=School.SchoolType.choices, null=True, blank=True,
        verbose_name="Secteur pédagogique (facultatif)",
    )
    school_year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE, related_name="fee_types")
    amount = models.DecimalField(max_digits=10, decimal_places=0, verbose_name="Montant")
    is_required = models.BooleanField(default=False, verbose_name="Appliquer automatiquement à l'inscription")
    registration_scope = models.CharField(
        max_length=10,
        choices=RegistrationScope.choices,
        default=RegistrationScope.ANNUAL,
        verbose_name="Validité des frais d'inscription",
    )
    cycle_key = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Référence du cycle d'inscription",
        help_text="Référence libre pour reconnaître un même cycle d'inscription sur plusieurs années.",
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    allows_quantity = models.BooleanField(
        default=False, verbose_name="Quantité et prix variables",
        help_text="Pour une option comme l'uniforme : on saisit le nombre d'articles et le prix unitaire "
                  "(qui peut varier selon la taille) au moment du choix. Le montant indiqué ci-dessus sert de prix proposé.",
    )

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["name", "classe", "education_level", "school_year"], name="unique_fee_type_per_scope_year")]
        verbose_name = "Type de frais"
        verbose_name_plural = "Types de frais"

    def clean(self):
        if self.classe_id and self.education_level_id and self.classe.education_level_id != self.education_level_id:
            raise ValidationError({"education_level": "Le niveau doit correspondre à la classe sélectionnée."})
        if self.school_year_id and self.education_level_id and not self.education_level.school_year_configurations.filter(school_year_id=self.school_year_id, is_active=True).exists():
            raise ValidationError({"education_level": "Ce niveau n’est pas ouvert dans l’année scolaire sélectionnée."})
        if self.category == self.Category.REGISTRATION and self.registration_scope == self.RegistrationScope.CYCLE and not self.cycle_key.strip():
            raise ValidationError({"cycle_key": "Un identifiant de cycle est requis pour un frais d'inscription valable sur un cycle."})
        if self.category != self.Category.REGISTRATION and self.cycle_key:
            raise ValidationError({"cycle_key": "La référence du cycle ne s'applique qu'aux frais d'inscription."})
        if self.category == self.Category.OPTIONAL and self.is_required:
            raise ValidationError({"is_required": "Un frais optionnel ne peut pas être obligatoire à l'inscription."})

    def __str__(self):
        return f"{self.name} — {self.amount:,.0f} FCFA"


class EnrollmentDiscount(models.Model):
    class DiscountType(models.TextChoices):
        FIXED = "fixed", "Montant fixe"
        PERCENTAGE = "percentage", "Pourcentage"

    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name="discount")
    discount_type = models.CharField(max_length=12, choices=DiscountType.choices)
    value = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=10, decimal_places=0, verbose_name="Montant de la remise")
    reason = models.CharField(max_length=150, verbose_name="Motif")
    note = models.TextField(blank=True, verbose_name="Observation")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Remise"
        verbose_name_plural = "Remises"

    def clean(self):
        if self.value <= 0:
            raise ValidationError("La valeur de la remise doit être supérieure à zéro.")
        if self.discount_type == self.DiscountType.PERCENTAGE and self.value > 100:
            raise ValidationError("Une remise en pourcentage ne peut pas dépasser 100 %.")
        if not self.reason.strip():
            raise ValidationError("Le motif de la remise est obligatoire.")
        if self.amount < 0:
            raise ValidationError("Le montant de la remise ne peut pas être négatif.")

    def __str__(self):
        return f"{self.enrollment} — remise {self.amount:,.0f}"


class DiscountAllocation(models.Model):
    discount = models.ForeignKey(EnrollmentDiscount, on_delete=models.CASCADE, related_name="allocations")
    invoice = models.OneToOneField(Invoice if False else "Invoice", on_delete=models.CASCADE, related_name="discount_allocation")
    original_amount = models.DecimalField(max_digits=10, decimal_places=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=0)

    class Meta:
        verbose_name = "Affectation de remise"
        verbose_name_plural = "Affectations de remise"


class Invoice(models.Model):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="invoices")
    fee_type = models.ForeignKey(FeeType, on_delete=models.CASCADE, related_name="invoices")
    total_amount = models.DecimalField(max_digits=10, decimal_places=0, verbose_name="Montant total")
    paid_amount = models.DecimalField(max_digits=10, decimal_places=0, default=0, verbose_name="Montant payé")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["enrollment", "fee_type"], name="unique_invoice_per_fee")]
        verbose_name = "Facture"
        verbose_name_plural = "Factures"

    @property
    def reste(self):
        return max(Decimal("0"), self.total_amount - self.paid_amount)

    @property
    def is_paid(self):
        return self.paid_amount >= self.total_amount

    @property
    def label(self):
        """Nom du frais, avec « (3 × 7 500) » pour une option à quantité (uniformes…)."""
        name = self.fee_type.name
        if self.fee_type.allows_quantity:
            option = StudentOption.objects.filter(enrollment_id=self.enrollment_id, fee_type_id=self.fee_type_id).first()
            if option and option.detail:
                return f"{name} ({option.detail})"
        return name

    @property
    def status_label(self):
        if self.is_paid:
            return "Soldé"
        if self.paid_amount:
            return "Partiel"
        return "Impayé"

    def __str__(self):
        return f"{self.enrollment} — {self.fee_type}"


class PaymentBatch(models.Model):
    """Encaissement groupé : un seul reçu pour plusieurs factures.

    Exemple : inscription + option + une tranche de scolarité, ou les frais de
    plusieurs enfants d'une même famille réglés en une fois par un parent.
    Chaque facture réglée garde son propre Payment (le suivi par facture ne
    change pas) ; le versement porte le numéro du reçu unique.
    """

    receipt_number = models.CharField(max_length=30, unique=True, verbose_name="N° de reçu")
    date = models.DateField(auto_now_add=True)
    payer_name = models.CharField(max_length=150, blank=True, verbose_name="Versé par")
    comment = models.TextField(blank=True, verbose_name="Commentaire")
    created_by = models.ForeignKey(
        "administration.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="payment_batches"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name = "Encaissement groupé"
        verbose_name_plural = "Encaissements groupés"

    @property
    def total(self):
        return self.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")

    def __str__(self):
        return self.receipt_number


class Payment(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    batch = models.ForeignKey(
        PaymentBatch, on_delete=models.CASCADE, null=True, blank=True, related_name="payments",
        verbose_name="Encaissement groupé",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=0, verbose_name="Montant payé")
    date = models.DateField(auto_now_add=True)
    receipt_number = models.CharField(max_length=30, unique=True, blank=True)
    comment = models.TextField(blank=True, null=True)
    is_carryover = models.BooleanField(
        default=False, verbose_name="Reprise (versement reçu avant KIS)",
        help_text="Versement déjà encaissé sur papier avant l'utilisation de KIS Kalanso : aucun reçu KIS n'est édité.",
    )

    @property
    def has_receipt(self):
        return not self.is_carryover

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [models.Index(fields=["date"], name="payment_date_idx")]
        verbose_name = "Paiement"
        verbose_name_plural = "Paiements"

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Le montant du paiement doit être supérieur à zéro.")
        if self.invoice_id and self.amount > self.invoice.reste:
            raise ValidationError("Le paiement dépasse le reste à payer.")

    def save(self, *args, **kwargs):
        self.full_clean()
        if not self.receipt_number:
            self.receipt_number = NumberingService.next_receipt_number()
        super().save(*args, **kwargs)
        total_paid = self.invoice.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
        self.invoice.paid_amount = total_paid
        self.invoice.save(update_fields=["paid_amount"])

    def __str__(self):
        return f"{self.receipt_number} — {self.amount:,.0f} {self.invoice.enrollment.school_year.school.currency}"


class StudentOption(models.Model):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="options")
    fee_type = models.ForeignKey(FeeType, on_delete=models.CASCADE, related_name="student_options")
    start_date = models.DateField(auto_now_add=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    quantity = models.PositiveSmallIntegerField(default=1, verbose_name="Quantité")
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=0, null=True, blank=True, verbose_name="Prix unitaire",
        help_text="Vide : prix du catalogue.",
    )

    @property
    def price(self):
        return self.fee_type.amount if self.unit_price is None else self.unit_price

    @property
    def total(self):
        return self.price * (self.quantity or 1)

    @property
    def detail(self):
        """Ex. « 3 × 7 500 » pour une option à quantité, sinon vide."""
        if not self.fee_type.allows_quantity:
            return ""
        return f"{self.quantity} × {self.price:,.0f}".replace(",", " ")

    class Meta:
        verbose_name = "Option élève"
        verbose_name_plural = "Options élèves"
        constraints = [models.UniqueConstraint(fields=["enrollment", "fee_type"], name="unique_student_option")]

    def clean(self):
        if self.fee_type.category != FeeType.Category.OPTIONAL:
            raise ValidationError("Une option élève doit utiliser un frais de catégorie optionnelle.")

    def __str__(self):
        return f"{self.enrollment} — {self.fee_type}"



# --------------------------------------------------------------------------
# Composantes d'un frais (retours du 09/10)
# Un frais reste unique pour la famille (ex. « Inscription préscolaire »
# 20 000 F, un seul reçu global) mais il est détaillé en interne en postes
# (inscription, manuel, 2 uniformes…). Chaque facture de ce frais reçoit les
# mêmes postes ; chaque paiement est ventilé sur les postes réglés.
# --------------------------------------------------------------------------
class FeeComponent(models.Model):
    fee_type = models.ForeignKey(FeeType, on_delete=models.CASCADE, related_name="components", verbose_name="Frais")
    name = models.CharField(max_length=100, verbose_name="Poste")
    amount = models.DecimalField(max_digits=10, decimal_places=0, verbose_name="Montant")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="Ordre")

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Composante de frais"
        verbose_name_plural = "Composantes de frais"

    def clean(self):
        if self.amount is None or self.amount <= 0:
            raise ValidationError("Le montant d'un poste doit être supérieur à zéro.")

    def __str__(self):
        return f"{self.fee_type.name} — {self.name}"


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines", verbose_name="Facture")
    component = models.ForeignKey(FeeComponent, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoice_lines")
    name = models.CharField(max_length=100, verbose_name="Poste")
    amount = models.DecimalField(max_digits=10, decimal_places=0, verbose_name="Montant")
    paid_amount = models.DecimalField(max_digits=10, decimal_places=0, default=0, verbose_name="Payé")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Poste de facture"
        verbose_name_plural = "Postes de facture"

    @property
    def reste(self):
        return max(Decimal("0"), self.amount - self.paid_amount)

    def __str__(self):
        return f"{self.invoice} — {self.name}"


class PaymentAllocation(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="allocations")
    line = models.ForeignKey(InvoiceLine, on_delete=models.CASCADE, related_name="allocations")
    amount = models.DecimalField(max_digits=10, decimal_places=0)

    class Meta:
        verbose_name = "Ventilation de paiement"
        verbose_name_plural = "Ventilations de paiement"
