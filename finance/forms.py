from django import forms
from django.db.models import Q
from .models import FeeType, Invoice, Payment, StudentOption

class FeeTypeForm(forms.ModelForm):
    class Meta:
        model = FeeType
        fields = ["name", "category", "amount", "is_required", "allows_quantity", "registration_scope", "cycle_key", "education_level"]
        labels = {"category": "Nature du frais", "is_required": "Appliquer automatiquement à l'inscription", "registration_scope": "Validité du frais d'inscription", "cycle_key": "Référence du cycle d'inscription"}
        help_texts = {"is_required": "Les frais cochés sont ajoutés automatiquement à la facture lors de l'inscription. Les options restent au choix de la famille.", "registration_scope": "Concerne uniquement les frais d'inscription : cette année ou une seule fois sur un même cycle.", "cycle_key": "À utiliser seulement pour un frais d'inscription valable une seule fois sur plusieurs années du même parcours."}
    def __init__(self, *args, force_optional=False, **kwargs):
        super().__init__(*args, **kwargs)
        optional = force_optional or self.instance.category == FeeType.Category.OPTIONAL or self.data.get("category") == FeeType.Category.OPTIONAL
        if optional:
            self.fields["category"].initial = FeeType.Category.OPTIONAL; self.fields["category"].widget = forms.HiddenInput(); self.fields["is_required"].widget = forms.HiddenInput(); self.fields["is_required"].initial = False
    def clean(self):
        cleaned = super().clean()
        if cleaned.get("allows_quantity") and cleaned.get("category") != FeeType.Category.OPTIONAL:
            self.add_error("allows_quantity", "Réservé aux options (ex. uniformes).")
        return cleaned

class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["amount", "comment"]

class FinancialAdjustmentForm(forms.Form):
    optional_fees = forms.ModelMultipleChoiceField(queryset=FeeType.objects.none(), required=False, label="Options à ajouter")
    discount_type = forms.ChoiceField(choices=[("", "Aucune remise"), ("fixed", "Montant fixe"), ("percentage", "Pourcentage")], required=False, label="Remise")
    discount_value = forms.DecimalField(required=False, min_value=0, label="Valeur de la remise")
    discount_reason = forms.CharField(required=False, label="Motif de la remise")
    discount_note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Observation")
    def __init__(self, *args, enrollment=None, **kwargs):
        super().__init__(*args, **kwargs); self.enrollment = enrollment
        if enrollment:
            self.fields["optional_fees"].queryset = FeeType.objects.filter(school_year=enrollment.school_year, category=FeeType.Category.OPTIONAL, is_active=True).filter(Q(classe=enrollment.classe) | Q(classe__isnull=True)).exclude(invoices__enrollment=enrollment).order_by("name")
    def clean(self):
        cleaned = super().clean()
        if cleaned.get("discount_type") and not cleaned.get("discount_value"):
            self.add_error("discount_value", "Indiquez la valeur de la remise.")
        if cleaned.get("discount_type") and not cleaned.get("discount_reason", "").strip():
            self.add_error("discount_reason", "Le motif de la remise est obligatoire.")
        return cleaned
