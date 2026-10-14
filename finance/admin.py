from django.contrib import admin
from .models import FeeType, Invoice, Payment, StudentOption


@admin.register(FeeType)
class FeeTypeAdmin(admin.ModelAdmin):
    list_display = ("name","category","classe","school_year","amount","is_required","registration_scope","is_active")
    list_filter = ("school_year","category","is_required","registration_scope","is_active")
    search_fields = ("name",)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("enrollment","fee_type","total_amount","paid_amount","reste","status_label")
    list_filter = ("fee_type",)
    search_fields = ("enrollment__student__last_name","enrollment__student__first_name")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("receipt_number","invoice","amount","date")
    search_fields = ("receipt_number","invoice__enrollment__student__last_name")


admin.site.register(StudentOption)
