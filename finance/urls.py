from django.urls import path
from .views import (
    financial_adjustment,
    fee_type_list, fee_type_create, invoice_list, invoice_create,
    payment_create, payment_list, debt_report,
    receipt_pdf, invoice_statement_pdf, debt_report_pdf,
)

from .views_arrears import arrears_import, arrears_quick, arrears_template, prior_balance_add
from .views_family import family_list, family_list_pdf
from .views_options import option_lists, option_list_pdf
from .views_components import fee_components, invoice_ventilation
from .views_grouped import payment_start, grouped_payment, payment_done, batch_receipt_pdf, family_statement_pdf, receipts_print_pdf

urlpatterns = [
    path("finance/enrollments/<int:enrollment_id>/adjust/", financial_adjustment, name="financial_adjustment"),
    path("finance/fees/", fee_type_list, name="fee_type_list"),
    path("finance/fees/add/", fee_type_create, name="fee_type_create"),
    path("finance/classes/<int:classe_id>/fees/add/", fee_type_create, name="fee_type_create_for_class"),
    path("finance/fees/<int:fee_id>/postes/", fee_components, name="fee_components"),
    path("finance/factures/<int:invoice_id>/ventilation/", invoice_ventilation, name="invoice_ventilation"),
    path("finance/invoices/", invoice_list, name="invoice_list"),
    path("finance/enrollments/<int:enrollment_id>/invoice/", invoice_create, name="invoice_create"),
    path("finance/invoices/<int:invoice_id>/payment/", payment_create, name="payment_create"),
    path("finance/payments/", payment_list, name="payment_list"),
    path("finance/reprise-soldes/", arrears_import, name="arrears_import"),
    path("finance/reprise-soldes/saisie-rapide/", arrears_quick, name="arrears_quick"),
    path("finance/reprise-soldes/modele.xlsx", arrears_template, name="arrears_template"),
    path("finance/eleves/<int:student_id>/reliquat/", prior_balance_add, name="prior_balance_add"),
    path("finance/familles/", family_list, name="family_list"),
    path("finance/familles/pdf/", family_list_pdf, name="family_list_pdf"),
    path("finance/options/", option_lists, name="option_lists"),
    path("finance/options/pdf/", option_list_pdf, name="option_list_pdf"),
    path("finance/payments/new/", payment_start, name="payment_start"),
    path("finance/encaissement/<int:enrollment_id>/", grouped_payment, name="grouped_payment"),
    path("finance/encaissement/termine/", payment_done, name="payment_done"),
    path("finance/recus/imprimer/", receipts_print_pdf, name="receipts_print_pdf"),
    path("finance/recus/<int:batch_id>/", batch_receipt_pdf, name="batch_receipt_pdf"),
    path("finance/famille/<int:enrollment_id>/situation/", family_statement_pdf, name="family_statement_pdf"),
    path("finance/debts/", debt_report, name="debt_report"),
    path("finance/debts/pdf/", debt_report_pdf, name="debt_report_pdf"),
    path("finance/payments/<int:payment_id>/receipt/", receipt_pdf, name="receipt_pdf"),
    path("finance/enrollments/<int:enrollment_id>/statement/", invoice_statement_pdf, name="invoice_statement_pdf"),
]
