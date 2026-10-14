from decimal import Decimal
from io import BytesIO
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.db.models import Case, Count, DecimalField, F, Min, Q, Sum, Value, When
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import escape
from administration.models import SchoolYear
from pedagogie.models import Classe, Enrollment
from .forms import FeeTypeForm, PaymentForm, FinancialAdjustmentForm
from .models import FeeType, Invoice, Payment, StudentOption, EnrollmentDiscount
from common.pagination import paginate
from common.years import viewed_year


def _selected_year(request):
    """Return the explicitly selected year, otherwise the current active year.

    Closed years remain accessible for historical finance follow-up, including
    recording payments against outstanding invoices.
    """
    year_id = request.GET.get("year")
    if year_id:
        return get_object_or_404(SchoolYear, pk=year_id)
    return viewed_year()


def _finance_year_context(request, year):
    return {"school_year": year, "school_years": SchoolYear.objects.filter(school=year.school).order_by("-start_date") if year else SchoolYear.objects.none()}


@login_required
def fee_type_list(request):
    year = viewed_year()
    fees = FeeType.objects.filter(school_year=year).select_related("classe") if year else FeeType.objects.none()
    return render(request, "finance/fee_types/list.html", {"fees":fees,"school_year":year})


@login_required
def fee_type_create(request, classe_id=None):
    year = viewed_year()
    classe = get_object_or_404(Classe, pk=classe_id, school_year=year) if classe_id else None
    force_optional = request.GET.get("category") == FeeType.Category.OPTIONAL
    form = FeeTypeForm(request.POST or None, force_optional=force_optional)
    if force_optional and request.method == "POST":
        form.data = form.data.copy()
        form.data["category"] = FeeType.Category.OPTIONAL
        form.data["is_required"] = ""
    if classe:
        form.fields["name"].label = f"Type de frais — {classe.name}"
    if request.method == "POST" and form.is_valid():
        fee = form.save(commit=False)
        if force_optional:
            fee.category = FeeType.Category.OPTIONAL
            fee.is_required = False
        fee.school_year = year
        # Un type de frais peut être général à l'année : la classe est facultative.
        # Si l'écran a été ouvert depuis une classe, on la rattache explicitement.
        fee.classe_id = classe.pk if classe else None
        fee.save()
        if request.headers.get("HX-Request") or request.GET.get("modal"):
            from django.http import HttpResponse
            label = "Option financière enregistrée." if force_optional else "Frais enregistré."
            response = HttpResponse(f"<div class='kis-modal-success'>{label}</div>")
            response["HX-Trigger"] = "kisFeeCreated"
            return response
        return redirect("fee_type_list")
    if request.headers.get("HX-Request") or request.GET.get("modal"):
        return render(request, "finance/fee_types/_modal_form.html", {"form":form,"classe":classe})
    return render(request, "finance/fee_types/form.html", {"form":form,"classe":classe})


@login_required
def invoice_list(request):
    year = _selected_year(request)

    # Sans filtre d'année, la situation financière principale est cumulative :
    # toutes les factures de l'établissement sont prises en compte, y compris
    # les dettes des années antérieures. Un ?year=... reste disponible pour
    # consulter explicitement une année historique.
    if year and request.GET.get("year"):
        invoices = Invoice.objects.filter(
            enrollment__school_year=year
        ).select_related("enrollment__student", "enrollment__classe", "enrollment__discount", "enrollment__school_year")
        cumulative = False
    elif year:
        invoices = Invoice.objects.filter(
            enrollment__school_year__school=year.school
        ).select_related("enrollment__student", "enrollment__classe", "enrollment__discount", "enrollment__school_year")
        cumulative = True
    else:
        invoices = Invoice.objects.none()
        cumulative = True

    # L'écran principal de Finance est piloté par l'élève. En mode cumulatif,
    # plusieurs inscriptions/années d'un même élève sont regroupées dans une
    # seule situation. L'inscription la plus récente sert de référence pour
    # l'affichage de la classe.
    search = (request.GET.get("q") or "").strip()
    if search:
        invoices = invoices.filter(
            Q(enrollment__student__first_name__icontains=search)
            | Q(enrollment__student__last_name__icontains=search)
            | Q(enrollment__student__matricule__icontains=search)
            | Q(fee_type__name__icontains=search)
        )

    # Agrégation par élève directement en SQL : une seule requête quel que
    # soit le nombre de factures, puis pagination sur les élèves.
    remaining_expr = Case(
        When(total_amount__gt=F("paid_amount"), then=F("total_amount") - F("paid_amount")),
        default=Value(0), output_field=DecimalField(max_digits=12, decimal_places=0),
    )
    rows = (
        invoices.order_by()
        .values("enrollment__student_id")
        .annotate(
            total_due=Sum("total_amount"), paid=Sum("paid_amount"),
            remaining=Sum(remaining_expr), invoice_count=Count("id"),
            first_name=Min("enrollment__student__first_name"), last_name=Min("enrollment__student__last_name"),
        )
    )
    status = request.GET.get("status")
    if status == "unpaid":
        rows = rows.filter(remaining__gt=0)
    elif status == "partial":
        rows = rows.filter(paid__gt=0, remaining__gt=0)
    elif status == "paid":
        rows = rows.filter(remaining=0)
    rows = rows.order_by(Lower("first_name"), Lower("last_name"), "enrollment__student_id")

    page_obj = paginate(request, rows)
    students = _attach_student_rows(list(page_obj.object_list), invoices)
    return render(request, "finance/invoices/list.html", {
        "students": students,
        "page_obj": page_obj,
        "status": status,
        "search": search,
        "cumulative": cumulative,
        **_finance_year_context(request, year),
    })


def _attach_student_rows(rows, invoices):
    """Complète les lignes agrégées d'une page : élève, inscription de référence, remises."""
    student_ids = [row["enrollment__student_id"] for row in rows]
    enrollment_ids = invoices.filter(enrollment__student_id__in=student_ids).values("enrollment_id")
    enrollments = (
        Enrollment.objects.filter(pk__in=enrollment_ids)
        .select_related("student", "school_year", "classe__education_level", "classe__pedagogical_track")
        .order_by("-school_year__start_date")
    )
    latest = {}
    for enrollment in enrollments:
        latest.setdefault(enrollment.student_id, enrollment)
    discounts = dict(
        EnrollmentDiscount.objects.filter(enrollment_id__in=enrollment_ids)
        .values("enrollment__student_id").annotate(total=Sum("amount"))
        .values_list("enrollment__student_id", "total")
    )
    for row in rows:
        student_id = row["enrollment__student_id"]
        row["enrollment"] = latest.get(student_id)
        row["student"] = row["enrollment"].student if row["enrollment"] else None
        row["discount"] = discounts.get(student_id) or Decimal("0")
        if row["remaining"] == 0:
            row["status_label"] = "Soldé"
        elif row["paid"] > 0:
            row["status_label"] = "Partiel"
        else:
            row["status_label"] = "Impayé"
    return rows


@login_required
def invoice_create(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment, pk=enrollment_id)
    fees = FeeType.objects.filter(Q(classe=enrollment.classe) | Q(classe__isnull=True), school_year=enrollment.school_year, is_active=True)
    if request.method == "POST":
        fee_id = request.POST.get("fee_type")
        fee = get_object_or_404(fees, pk=fee_id)
        invoice, created = Invoice.objects.get_or_create(
            enrollment=enrollment, fee_type=fee, defaults={"total_amount":fee.amount}
        )
        if not created:
            messages.info(request, "Cette facture existe déjà.")
        else:
            messages.success(request, "Facture créée.")
        return redirect("student_detail", student_id=enrollment.student_id)
    return render(request, "finance/invoices/form.html", {"enrollment":enrollment,"fees":fees})


@login_required
def payment_start(request):
    year = _selected_year(request)
    invoices = Invoice.objects.filter(
        enrollment__school_year=year, paid_amount__lt=F("total_amount"),
    ).select_related("enrollment__student", "fee_type") if year else Invoice.objects.none()
    search = (request.GET.get("q") or "").strip()
    if search:
        invoices = invoices.filter(_student_or_fee_search(search))
    invoices = invoices.order_by("enrollment__student__first_name", "enrollment__student__last_name", "fee_type__name")
    # La liste déroulante reste courte : au-delà, il faut affiner la recherche.
    limit = 100
    invoices = list(invoices[:limit + 1])
    truncated = len(invoices) > limit
    invoices = invoices[:limit]
    if request.method == "POST":
        invoice_id = request.POST.get("invoice")
        invoice = get_object_or_404(Invoice, pk=invoice_id, enrollment__school_year=year)
        return redirect("payment_create", invoice_id=invoice.id)
    return render(request, "finance/payments/select_invoice.html", {"invoices": invoices, "truncated": truncated, "search": search, **_finance_year_context(request, year)})


@login_required
def payment_create(request, invoice_id):
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    if invoice.lines.exists():
        # Frais détaillé en postes : on choisit les postes réglés sur l'écran d'encaissement.
        return redirect("grouped_payment", enrollment_id=invoice.enrollment_id)
    form = PaymentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        payment = form.save(commit=False)
        payment.invoice = invoice
        try:
            payment.save()
            # Le reçu PDF est la confirmation officielle du paiement.
            # Ne pas laisser un message Django en attente : la génération du PDF
            # ne consomme pas les messages et celui-ci pourrait apparaître sur
            # un écran HTML ultérieur (notamment la configuration initiale).
            # Confirmation dans l'application ; le reçu s'ouvre dans une fenêtre
            # séparée, que l'on ferme sans quitter KIS Kalanso.
            from django.urls import reverse
            return redirect(f"{reverse('payment_done')}?payment={payment.id}")
        except Exception as exc:
            form.add_error("amount", str(exc))
    return render(request, "finance/payments/form.html", {"form":form,"invoice":invoice})


@login_required
def payment_list(request):
    year = _selected_year(request)
    payments = Payment.objects.filter(invoice__enrollment__school_year=year).select_related("invoice__enrollment__student","invoice__fee_type") if year else Payment.objects.none()
    search = (request.GET.get("q") or "").strip()
    if search:
        payments = payments.filter(
            Q(receipt_number__icontains=search)
            | Q(invoice__enrollment__student__first_name__icontains=search)
            | Q(invoice__enrollment__student__last_name__icontains=search)
            | Q(invoice__enrollment__student__matricule__icontains=search)
        )
    day = (request.GET.get("date") or "").strip()
    if day:
        payments = payments.filter(date=day)
    page_obj = paginate(request, payments)
    import datetime as _dt
    return render(request, "finance/payments/list.html", {"payments": page_obj, "page_obj": page_obj, "search": search, "day": day,
                                                          "today": _dt.date.today().isoformat(), **_finance_year_context(request, year)})

@login_required
def debt_report(request):
    year = _selected_year(request)
    if year and request.GET.get("year"):
        invoices = Invoice.objects.filter(enrollment__school_year=year).select_related("enrollment__student", "enrollment__classe", "fee_type")
    elif year:
        invoices = Invoice.objects.filter(enrollment__school_year__school=year.school).select_related("enrollment__student", "enrollment__classe", "fee_type")
    else:
        invoices = Invoice.objects.none()
    search = (request.GET.get("q") or "").strip()
    rows, total = _debt_rows(invoices, search)
    page_obj = paginate(request, rows)
    students = _attach_student_rows(list(page_obj.object_list), invoices)
    return render(request, "finance/debt_report.html", {"students": students, "page_obj": page_obj, "total_debt": total, "search": search, "cumulative": not bool(request.GET.get("year")), **_finance_year_context(request, year)})


def _fit(text, width):
    """Tronque un libellé de cellule PDF (texte brut, sans retour à la ligne)."""
    return text if len(text) <= width else text[: width - 1] + "…"


def _student_or_fee_search(search):
    return (
        Q(enrollment__student__first_name__icontains=search)
        | Q(enrollment__student__last_name__icontains=search)
        | Q(enrollment__student__matricule__icontains=search)
        | Q(fee_type__name__icontains=search)
    )


def _debt_rows(invoices, search=""):
    """Impayés agrégés par élève (requête SQL unique) et total général."""
    if search:
        invoices = invoices.filter(_student_or_fee_search(search))
    unpaid = invoices.filter(paid_amount__lt=F("total_amount")).order_by()
    remaining = Sum(F("total_amount") - F("paid_amount"), output_field=DecimalField(max_digits=14, decimal_places=0))
    rows = (
        unpaid.values("enrollment__student_id")
        .annotate(
            remaining=remaining, paid=Sum("paid_amount"), invoice_count=Count("id"),
            first_name=Min("enrollment__student__first_name"), last_name=Min("enrollment__student__last_name"),
        )
        .order_by(Lower("first_name"), Lower("last_name"), "enrollment__student_id")
    )
    total = unpaid.aggregate(total=remaining)["total"] or Decimal("0")
    return rows, total


@login_required
def debt_report_pdf(request):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    year = _selected_year(request)
    if not year:
        return HttpResponse("Aucune année scolaire disponible.", status=404)
    if request.GET.get("year"):
        invoices = Invoice.objects.filter(enrollment__school_year=year).select_related("enrollment__student", "enrollment__classe", "fee_type")
    else:
        invoices = Invoice.objects.filter(enrollment__school_year__school=year.school).select_related("enrollment__student", "enrollment__classe", "fee_type")
    search = (request.GET.get("q") or "").strip()
    rows, total = _debt_rows(invoices, search)
    students = _attach_student_rows(list(rows), invoices)
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="impayes.pdf"'
    doc = SimpleDocTemplate(response, pagesize=A4, rightMargin=14*mm, leftMargin=14*mm, topMargin=14*mm, bottomMargin=14*mm, title="Impayés")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Small", parent=styles["Normal"], fontSize=8.5, leading=10))
    styles.add(ParagraphStyle("TitleK", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=17, textColor=colors.HexColor("#17365D")))
    story=[_school_identity_story(year.school, styles, A4[0]-28*mm), Spacer(1,5*mm), Paragraph("ÉTAT DES IMPAYÉS", styles["TitleK"]), Paragraph(f"Année : {escape(year.name)}" + (" — Situation cumulative" if not request.GET.get("year") else ""), styles["Small"])]
    if search: story.append(Paragraph(f"Recherche : {escape(search)}", styles["Small"]))
    story.append(Spacer(1,4*mm))
    data=[["Élève","Classe","Factures","Reste à payer"]]
    for r in students:
        # Texte brut plutôt qu'un Paragraph par cellule : ReportLab met en page
        # un Paragraph ~20 fois plus lentement (11 s → <2 s pour 10 000 élèves).
        data.append([_fit(str(r["student"]), 44), _fit(str(r["enrollment"].classe), 30), str(r["invoice_count"]), f"{r['remaining']:,.0f} {year.school.currency}"])
    header = data[0]
    rows = data[1:]
    base_style = [("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17365D")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#CBD5E1")),("FONTSIZE",(0,0),(-1,-1),8.5),("ALIGN",(2,1),(-1,-1),"RIGHT")]
    # Un tableau par bloc de lignes : ReportLab découpe un très grand tableau
    # en pages avec un coût qui explose avec sa taille.
    chunk = 200
    for start in range(0, max(len(rows), 1), chunk):
        block = [header] + rows[start:start + chunk]
        last = start + chunk >= len(rows)
        if last:
            block.append(["TOTAL","","",f"{total:,.0f} {year.school.currency}"])
        style = list(base_style)
        if last:
            style += [("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#F1F5F9")),("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold")]
        table=Table(block,colWidths=[72*mm,50*mm,25*mm,45*mm],repeatRows=1)
        table.setStyle(TableStyle(style))
        story.append(table)
    doc.build(story, onFirstPage=lambda c, d: _draw_internal_footer(c, d, year.school), onLaterPages=lambda c, d: _draw_internal_footer(c, d, year.school))
    return response


@login_required
def financial_adjustment(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment.objects.select_related("student", "classe", "school_year"), pk=enrollment_id)
    form = FinancialAdjustmentForm(request.POST or None, enrollment=enrollment)
    quantity_options = list(StudentOption.objects.filter(
        enrollment=enrollment, fee_type__allows_quantity=True).select_related("fee_type"))
    if request.method == "POST" and form.is_valid():
        try:
            from django.db import transaction
            from finance.services.discount_service import apply_enrollment_discount
            from finance.services.options import add_option, read_quantity_price, update_option
            with transaction.atomic():
                for fee in form.cleaned_data["optional_fees"]:
                    quantity, unit_price = read_quantity_price(request.POST, fee)
                    add_option(enrollment, fee, quantity, unit_price)
                for option in quantity_options:
                    quantity, unit_price = read_quantity_price(request.POST, option.fee_type, prefix="current")
                    if quantity != option.quantity or unit_price != option.price:
                        update_option(option, quantity, unit_price)
                if form.cleaned_data.get("discount_type"):
                    if hasattr(enrollment, "discount"):
                        raise ValidationError("Une remise existe déjà pour cette inscription.")
                    apply_enrollment_discount(enrollment, form.cleaned_data["discount_type"], form.cleaned_data["discount_value"], form.cleaned_data["discount_reason"], form.cleaned_data.get("discount_note", ""))
            messages.success(request, "Situation financière mise à jour.")
            return redirect("student_detail", student_id=enrollment.student_id)
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
    return render(request, "finance/financial_adjustment.html", {
        "form": form, "enrollment": enrollment, "quantity_options": quantity_options,
        "available_options": form.fields["optional_fees"].queryset,
    })

def _school_identity_story(school, styles, width):
    """Return a compact establishment identity header for internal documents.

    Internal financial documents show only the establishment identity.
    Institutional authorities belong to official documents such as bulletins.

    The helper is intentionally self-contained because callers may provide a
    plain ReportLab stylesheet without the finance-specific school styles.
    """
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Image, Spacer, Table, TableStyle, Paragraph

    # Some PDF views (notably the debt report) start from getSampleStyleSheet()
    # directly. Ensure the identity styles exist before indexing them.
    if "SchoolName" not in styles.byName:
        styles.add(ParagraphStyle("SchoolName", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=13, leading=15))
    if "SchoolSmall" not in styles.byName:
        styles.add(ParagraphStyle("SchoolSmall", parent=styles["Normal"], fontSize=8.5, leading=10, textColor=colors.HexColor("#475569")))

    logo = Spacer(1, 18 * mm)
    try:
        if school.logo:
            # Lire via le storage Django puis normaliser en PNG rend le logo
            # fiable avec tous les formats acceptés par ImageField (notamment
            # JPEG/PNG/WebP) et évite de dépendre de .path.
            from PIL import Image as PILImage

            school.logo.open("rb")
            try:
                source = PILImage.open(school.logo)
                source.load()
                if source.mode not in ("RGB", "RGBA"):
                    source = source.convert("RGBA")
                logo_buffer = BytesIO()
                source.save(logo_buffer, format="PNG")
                logo_buffer.seek(0)
                logo = Image(
                    logo_buffer,
                    width=18 * mm,
                    height=18 * mm,
                    kind="proportional",
                )
            finally:
                school.logo.close()
    except (AttributeError, OSError, ValueError):
        pass

    contact = [part for part in [school.address, school.city] if part]
    if school.phone:
        contact.append(f"Tél. : {school.phone}")
    if school.email:
        contact.append(school.email)
    # Document interne : aucune autorité officielle dans l'en-tête.
    # L'identité administrative (Ministère / Académie / CAP) est réservée
    # aux documents officiels. Ici, on affiche uniquement l'établissement
    # et ses coordonnées ; la devise est traitée séparément en pied de page.
    identity = []
    school_display_name = school.name
    if school.code:
        school_display_name = f"{school.name} ({school.code})"
    identity.append(Paragraph(f"<b>{escape(school_display_name)}</b>", styles["SchoolName"]))
    identity.append(Paragraph(escape(" — ".join(contact)), styles["SchoolSmall"]))

    table = Table([[logo, identity]], colWidths=[22 * mm, max(width - 22 * mm, 40 * mm)], rowHeights=[30 * mm])
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#B8C2CC")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _draw_internal_footer(canvas, doc, school):
    """Pied de page des documents internes de gestion.

    À gauche : « Document généré par KIS Kalanso » ; au centre : la devise de
    l'établissement si elle est renseignée.
    """
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    canvas.saveState()
    page_width = getattr(canvas, "_pagesize", (595.275590551, 841.88976378))[0]
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.setFont("Helvetica", 7)
    canvas.drawString(getattr(doc, "leftMargin", 15 * mm), 7 * mm, "Document généré par KIS Kalanso")
    motto = (getattr(school, "motto", "") or "").strip()
    if motto:
        canvas.setFont("Helvetica-Oblique", 7.5)
        canvas.drawCentredString(page_width / 2, 7 * mm, motto)
    canvas.restoreState()



def payment_receipt_builder(payment):
    """(établissement, build) pour le reçu d'un paiement isolé (hors encaissement groupé)."""
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    enrollment = payment.invoice.enrollment
    school = enrollment.school_year.school

    total_paid_after = payment.invoice.paid_amount
    paid_before = max(Decimal("0"), total_paid_after - payment.amount)
    remaining = payment.invoice.reste

    def build(width, st, copy_label=None):
        k = width / (173 * mm)
        label, value = st["label"], st["value"]
        amount = ParagraphStyle("ReceiptAmount", parent=value, fontName="Helvetica-Bold", fontSize=value.fontSize * 1.5,
                                leading=value.fontSize * 1.8, alignment=2)
        story = [Paragraph(copy_label, st["copy"])] if copy_label else []
        story += [
            _school_identity_story(school, st["styles"], width),
            Spacer(1, 8 * mm * k),
            Paragraph("REÇU DE PAIEMENT", st["title"]),
            Paragraph(f"N° {payment.receipt_number}", st["center"]),
            Spacer(1, 7 * mm * k),
        ]
        data = [
            [Paragraph("Élève", label), Paragraph(escape(str(enrollment.student)), value)],
            [Paragraph("Classe", label), Paragraph(escape(str(enrollment.classe)), value)],
            [Paragraph("Année scolaire", label), Paragraph(escape(enrollment.school_year.name), value)],
            [Paragraph("Responsable", label), Paragraph(escape(enrollment.student.responsible_label or "—")
                                                        + (f" · {escape(enrollment.student.responsible_phone)}" if enrollment.student.responsible_phone else ""), value)],
            [Paragraph("Frais", label), Paragraph(escape(payment.invoice.label), value)],
            [Paragraph("Date", label), Paragraph(payment.date.strftime("%d/%m/%Y"), value)],
        ]
        table = Table(data, colWidths=[48 * mm * k, width - 48 * mm * k], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7 * k),
            ("TOPPADDING", (0, 0), (-1, -1), 7 * k),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
        ]))
        story += [table, Spacer(1, 8 * mm * k)]
        amount_table = Table([
            [Paragraph("MONTANT DU FRAIS", label), Paragraph(f"{payment.invoice.total_amount:,.0f} {school.currency}".replace(",", " "), value)],
            [Paragraph("DÉJÀ PAYÉ AVANT CE RÈGLEMENT", label), Paragraph(f"{paid_before:,.0f} {school.currency}".replace(",", " "), value)],
            [Paragraph("MONTANT DE CE PAIEMENT", label), Paragraph(f"{payment.amount:,.0f} {school.currency}".replace(",", " "), amount)],
            [Paragraph("RESTE À PAYER", label), Paragraph(f"{remaining:,.0f} {school.currency}".replace(",", " "), value)],
        ], colWidths=[95 * mm * k, width - 95 * mm * k])
        amount_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#F3F6FA")),
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#C8D0DA")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E1E6EC")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10 * k),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10 * k),
            ("TOPPADDING", (0, 0), (-1, -1), 8 * k),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8 * k),
        ]))
        story += [amount_table, Spacer(1, 8 * mm * k)]
        status = "Paiement intégral" if remaining == 0 else "Paiement partiel"
        story += [
            Paragraph(f"<b>{status}</b>", value),
            Spacer(1, 14 * mm * k),
            Paragraph("Signature / Cachet de l'établissement", label),
        ]
        return story

    return school, build


@login_required
def receipt_pdf(request, payment_id):
    """Génère le reçu officiel d'un paiement, y compris s'il est partiel."""
    from django.http import HttpResponse
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    payment = get_object_or_404(
        Payment.objects.select_related(
            "invoice__enrollment__student",
            "invoice__enrollment__classe",
            "invoice__enrollment__school_year__school",
            "invoice__fee_type",
        ),
        pk=payment_id,
    )
    if payment.is_carryover:
        return HttpResponse("Ce versement a été reçu avant l'utilisation de KIS Kalanso (reprise) : aucun reçu KIS n'existe.", status=404)
    if payment.batch_id:
        # Ligne d'un encaissement groupé : le reçu officiel est le reçu groupé.
        from finance.views_grouped import batch_receipt_pdf
        return batch_receipt_pdf(request, payment.batch_id)
    school, build = payment_receipt_builder(payment)
    from finance.views_grouped import _pdf_styles, two_copies_pdf
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="recu_{payment.receipt_number}.pdf"'
    if request.GET.get("exemplaires") == "2":
        return two_copies_pdf(response, build, school, f"Reçu {payment.receipt_number}")
    doc = SimpleDocTemplate(
        response, pagesize=A4,
        rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"Reçu {payment.receipt_number}",
        author=school.name,
    )
    st = _pdf_styles()
    st["title"] = ParagraphStyle("ReceiptTitle", parent=st["title"], fontSize=18, leading=22, spaceAfter=6)
    st["label"] = ParagraphStyle("ReceiptLabel", parent=st["label"], fontSize=10, leading=12)
    st["value"] = ParagraphStyle("ReceiptValue", parent=st["value"], fontSize=10, leading=12)
    doc.build(build(A4[0] - 36 * mm, st) + [Spacer(1, 16 * mm)],
              onFirstPage=lambda c, d: _draw_internal_footer(c, d, school), onLaterPages=lambda c, d: _draw_internal_footer(c, d, school))
    return response


@login_required
def invoice_statement_pdf(request, enrollment_id):
    """Génère la situation financière d'un élève.

    Sans filtre d'année, le document est cumulatif et reprend toutes les
    inscriptions/factures de l'élève dans l'établissement. Avec ?year=..., il
    reste possible de produire une situation historique limitée à cette année.
    """
    from django.http import HttpResponse
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    enrollment = get_object_or_404(
        Enrollment.objects.select_related("student", "classe", "school_year__school"),
        pk=enrollment_id,
    )
    school = enrollment.school_year.school
    year_id = request.GET.get("year")

    enrollments = Enrollment.objects.filter(
        student=enrollment.student,
        school_year__school=school,
    ).select_related("classe", "school_year").order_by("school_year__start_date", "id")

    if year_id:
        selected_year = get_object_or_404(SchoolYear, pk=year_id, school=school)
        enrollments = enrollments.filter(school_year=selected_year)
        cumulative = False
    else:
        cumulative = True

    enrollment_ids = list(enrollments.values_list("id", flat=True))
    invoices = list(
        Invoice.objects.filter(enrollment_id__in=enrollment_ids)
        .select_related("fee_type", "enrollment__school_year", "enrollment__classe")
        .order_by("enrollment__school_year__start_date", "fee_type__category", "fee_type__name")
    )

    total = sum((i.total_amount for i in invoices), Decimal("0"))
    paid = sum((i.paid_amount for i in invoices), Decimal("0"))
    remaining = total - paid
    discount_amount = sum(
        (getattr(e, "discount", None).amount if getattr(e, "discount", None) else Decimal("0"))
        for e in enrollments
    )
    gross_total = total + discount_amount

    response = HttpResponse(content_type="application/pdf")
    suffix = "cumulative" if cumulative else f"{enrollment.school_year.name}"
    response["Content-Disposition"] = f'inline; filename="situation_{enrollment.student_id}_{suffix}.pdf"'
    doc = SimpleDocTemplate(
        response, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title="Situation financière cumulative" if cumulative else "Situation financière",
        author=school.name,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("SchoolName", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=13, leading=15))
    styles.add(ParagraphStyle("SchoolSmall", parent=styles["Normal"], fontSize=8.5, leading=10, textColor=colors.HexColor("#475569")))
    title = ParagraphStyle("StatementTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=18, spaceAfter=6)
    label = ParagraphStyle("StatementLabel", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9)
    value = ParagraphStyle("StatementValue", parent=styles["Normal"], fontSize=9)

    story = [
        _school_identity_story(school, styles, A4[0] - 36 * mm),
        Spacer(1, 8 * mm),
        Paragraph("SITUATION FINANCIÈRE", title),
        Paragraph(
            "Situation cumulative — toutes les années scolaires"
            if cumulative else f"Année scolaire : {escape(enrollment.school_year.name)}",
            value,
        ),
        Paragraph(f"Élève : <b>{escape(str(enrollment.student))}</b>", value),
        Spacer(1, 7 * mm),
    ]

    data = [[
        Paragraph("Année", label), Paragraph("Classe", label), Paragraph("Frais", label),
        Paragraph("Dû", label), Paragraph("Payé", label), Paragraph("Reste", label),
    ]]
    for invoice in invoices:
        data.append([
            Paragraph(escape(invoice.enrollment.school_year.name), value),
            Paragraph(escape(str(invoice.enrollment.classe)), value),
            Paragraph(escape(invoice.label), value),
            Paragraph(f"{invoice.total_amount:,.0f}", value),
            Paragraph(f"{invoice.paid_amount:,.0f}", value),
            Paragraph(f"{invoice.reste:,.0f}", value),
        ])
    data.append([
        Paragraph("TOTAL", label), Paragraph("", value), Paragraph("", value),
        Paragraph(f"{total:,.0f}", label), Paragraph(f"{paid:,.0f}", label),
        Paragraph(f"{remaining:,.0f}", label),
    ])
    table = Table(data, colWidths=[27 * mm, 31 * mm, 53 * mm, 24 * mm, 24 * mm, 24 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F2D5C")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F3F6FA")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    summary = [Paragraph(f"Total brut : <b>{gross_total:,.0f} {school.currency}</b>", value)]
    if discount_amount:
        summary.append(Paragraph(f"Remises : <b>-{discount_amount:,.0f} {school.currency}</b>", value))
    summary.append(Paragraph(
        f"Total net dû : <b>{total:,.0f} {school.currency}</b> · "
        f"Total payé : <b>{paid:,.0f} {school.currency}</b> · "
        f"Reste : <b>{remaining:,.0f} {school.currency}</b>", value
    ))
    story += [table, Spacer(1, 10 * mm), *summary, Spacer(1, 18 * mm), Paragraph("Signature / Cachet de l'établissement", label)]
    doc.build(story)
    return response

