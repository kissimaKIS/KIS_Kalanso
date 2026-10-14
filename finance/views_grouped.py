"""Encaissement : choix de l'élève, règlement de plusieurs factures (et de la
famille) sous un seul reçu, page de confirmation et documents PDF."""
from decimal import Decimal
from xml.sax.saxutils import escape

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, F, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from pedagogie.models import Enrollment
from .models import Invoice, Payment, PaymentBatch
from administration.permissions import user_has_permission
from .services.grouped_payment import (family_enrollments, open_invoices, parse_amount, record_carryover,
                                      record_grouped_payment, sort_by_priority)
from .views import _draw_internal_footer, _finance_year_context, _school_identity_story, _selected_year


def _money(value, currency):
    return f"{value:,.0f} {currency}".replace(",", " ")


@login_required
def payment_start(request):
    """Étape 1 : choisir l'élève (les élèves ayant un reste à payer)."""
    year = _selected_year(request)
    search = (request.GET.get("q") or "").strip()
    rows = []
    truncated = False
    all_years = bool(search) and not request.GET.get("year")
    if year or all_years:
        # Une recherche porte sur toutes les années : on retrouve ainsi les anciens
        # élèves qui règlent encore un reliquat.
        enrollments = Enrollment.objects.filter(invoices__paid_amount__lt=F("invoices__total_amount"))
        if not all_years:
            enrollments = enrollments.filter(school_year=year)
        if search:
            enrollments = enrollments.filter(
                Q(student__first_name__icontains=search) | Q(student__last_name__icontains=search)
                | Q(student__matricule__icontains=search) | Q(student__father_name__icontains=search)
                | Q(student__mother_name__icontains=search) | Q(student__father_phone__icontains=search)
                | Q(student__contact_name__icontains=search) | Q(student__contact_phone__icontains=search)
                | Q(student__mother_phone__icontains=search)
            )
        enrollments = (
            enrollments.annotate(
                open_count=Count("invoices", distinct=True),
                due=Sum(F("invoices__total_amount") - F("invoices__paid_amount")),
            )
            .select_related("student", "classe__education_level", "classe__pedagogical_track", "school_year__school")
            .order_by("student__last_name", "student__first_name", "-school_year__start_date").distinct()
        )
        rows = list(enrollments[:101])
        truncated = len(rows) > 100
        rows = rows[:100]
    return render(request, "finance/payments/select_student.html", {
        "rows": rows, "search": search, "truncated": truncated, "all_years": all_years, **_finance_year_context(request, year),
    })


@login_required
def grouped_payment(request, enrollment_id):
    """Étape 2 : cocher une ou plusieurs factures (de l'élève, ou de toute la famille)."""
    enrollment = get_object_or_404(Enrollment.objects.select_related("student", "classe", "school_year__school"), pk=enrollment_id)
    family = family_enrollments(enrollment)
    with_family = request.GET.get("famille") == "1" or request.POST.get("famille") == "1"
    scope = family if with_family else [enrollment]
    # Toutes les factures ouvertes des élèves concernés, années antérieures (reliquats) comprises.
    invoices = open_invoices(Enrollment.objects.filter(student_id__in=[e.student_id for e in scope]))
    # Année en cours prioritaire, puis les dettes passées année par année.
    from administration.models import SchoolYear
    active = SchoolYear.objects.filter(is_active=True).first()
    current_year_id = active.pk if active else enrollment.school_year_id
    invoices = sort_by_priority(invoices, current_year_id)
    from finance.models import InvoiceLine
    by_invoice = {}
    for line in InvoiceLine.objects.filter(invoice__in=invoices).order_by("order", "id"):
        by_invoice.setdefault(line.invoice_id, []).append(line)
    for invoice in invoices:
        all_lines = by_invoice.get(invoice.id, [])
        allocated = sum((l.paid_amount for l in all_lines), Decimal("0"))
        # Argent reçu avant la mise en place des postes, pas encore réparti :
        # on demande d'abord la ventilation ; d'ici là le versement suit l'ordre des postes.
        invoice.to_ventilate = max(Decimal("0"), invoice.paid_amount - allocated) if all_lines else Decimal("0")
        invoice.open_lines = [l for l in all_lines if l.reste > 0] if not invoice.to_ventilate else []
    student = enrollment.student
    default_payer = student.responsible_name
    errors = []
    if request.method == "POST":
        chosen = set(request.POST.getlist("invoice"))
        chosen_lines = set(request.POST.getlist("line"))
        lines = []
        for invoice in invoices:
            if str(invoice.id) not in chosen:
                continue
            try:
                amount = parse_amount(request.POST.get(f"amount_{invoice.id}"))
                # Frais détaillé en postes : le montant est la somme des postes cochés.
                alloc = []
                for line in invoice.open_lines:
                    if str(line.id) in chosen_lines:
                        part = parse_amount(request.POST.get(f"line_amount_{line.id}"))
                        if part:
                            alloc.append((line, part))
                if alloc:
                    amount = sum((part for _, part in alloc), Decimal("0"))
            except ValidationError as exc:
                errors.extend(exc.messages)
                continue
            lines.append((invoice, amount, alloc) if alloc else (invoice, amount))
        if not errors and request.POST.get("carryover") and user_has_permission(request.user, "finance.manage"):
            import datetime as _dt
            try:
                raw_date = request.POST.get("carryover_date") or ""
                try:
                    date = _dt.date.fromisoformat(raw_date)
                except ValueError:
                    date = None
                created = record_carryover(lines, date, request.POST.get("comment", ""), request.user)
            except ValidationError as exc:
                errors.extend(exc.messages)
            else:
                total = sum((p.amount for p in created), Decimal("0"))
                messages.success(request, f"Reprise enregistrée : {len(created)} versement(s) antérieur(s) pour "
                                          f"{total:,.0f} {enrollment.school_year.school.currency}, sans reçu KIS.".replace(",", " "))
                return redirect("student_detail", student_id=enrollment.student_id)
        elif not errors:
            try:
                batch = record_grouped_payment(lines, request.POST.get("payer_name", ""), request.POST.get("comment", ""), request.user)
            except ValidationError as exc:
                errors.extend(exc.messages)
            else:
                return redirect(f"{reverse('payment_done')}?batch={batch.id}")
    currency = enrollment.school_year.school.currency
    return render(request, "finance/payments/grouped.html", {
        "enrollment": enrollment, "family": family, "with_family": with_family, "invoices": invoices,
        "currency": currency, "errors": errors, "chosen": set(request.POST.getlist("invoice")) if request.method == "POST" else set(),
        "chosen_lines": set(request.POST.getlist("line")) if request.method == "POST" else None,
        "payer_name": request.POST.get("payer_name", default_payer) if request.method == "POST" else default_payer,
        "comment": request.POST.get("comment", ""),
        "total_due": sum((i.reste for i in invoices), Decimal("0")),
        "current_year_id": current_year_id,
        "carryover": request.POST.get("carryover") == "1", "carryover_date": request.POST.get("carryover_date", ""),
    })


@login_required
def payment_done(request):
    """Confirmation après un encaissement : le reçu s'ouvre dans une fenêtre séparée,
    que l'on peut fermer sans quitter KIS Kalanso."""
    batch = payment = None
    if request.GET.get("batch"):
        batch = get_object_or_404(PaymentBatch, pk=request.GET["batch"])
        receipt_url = reverse("batch_receipt_pdf", args=[batch.id])
        lines = list(batch.payments.select_related("invoice__enrollment__student", "invoice__fee_type", "invoice__enrollment__school_year__school"))
    else:
        payment = get_object_or_404(Payment.objects.select_related("invoice__enrollment__student", "invoice__fee_type", "invoice__enrollment__school_year__school"), pk=request.GET.get("payment"))
        receipt_url = reverse("receipt_pdf", args=[payment.id])
        lines = [payment]
    first = lines[0].invoice.enrollment if lines else None
    whatsapp_url = ""
    if first:
        from common import whatsapp
        number = batch.receipt_number if batch else payment.receipt_number
        whatsapp_url = whatsapp.wa_url(whatsapp.family_phone(first.student),
                                       whatsapp.receipt_text(lines, number, first.school_year.school))
    return render(request, "finance/payments/done.html", {
        "whatsapp_url": whatsapp_url,
        "batch": batch, "payment": payment, "lines": lines, "receipt_url": receipt_url,
        "receipt_number": batch.receipt_number if batch else payment.receipt_number,
        "total": sum((p.amount for p in lines), Decimal("0")),
        "currency": first.school_year.school.currency if first else "FCFA",
        "enrollment": first,
    })


def _pdf_styles(scale=1.0):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    k = scale
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("SchoolName", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=13 * k, leading=15 * k))
    styles.add(ParagraphStyle("SchoolSmall", parent=styles["Normal"], fontSize=8.5 * k, leading=10 * k, textColor=colors.HexColor("#475569")))
    return {
        "styles": styles,
        "title": ParagraphStyle("T", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=17 * k, leading=20 * k, spaceAfter=4 * k),
        "center": ParagraphStyle("C", parent=styles["Normal"], alignment=1, fontSize=9 * k, leading=11 * k, textColor=colors.HexColor("#666666")),
        "label": ParagraphStyle("L", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9.5 * k, leading=11.5 * k),
        "value": ParagraphStyle("V", parent=styles["Normal"], fontSize=9.5 * k, leading=11.5 * k),
        "cell": ParagraphStyle("Ce", parent=styles["Normal"], fontSize=8.6 * k, leading=10.5 * k),
        "cellr": ParagraphStyle("Cr", parent=styles["Normal"], fontSize=8.6 * k, leading=10.5 * k, alignment=2),
        "cellb": ParagraphStyle("Cb", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.6 * k, leading=10.5 * k, alignment=2),
        "head": ParagraphStyle("H", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.6 * k, leading=10.5 * k, textColor=colors.white),
        "copy": ParagraphStyle("Cp", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8 * k, leading=10 * k, alignment=2,
                               textColor=colors.HexColor("#1565C0")),
    }


def receipts_two_per_page(response, items, title):
    """Plusieurs reçus, deux par feuille A4 paysage, côte à côte (comme les bulletins),
    séparés par un pointillé de découpe. ``items`` : [(établissement, build, mention)].
    Un reçu trop long est réduit pour tenir dans sa demi-page."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import BaseDocTemplate, Frame, FrameBreak, KeepInFrame, PageTemplate

    school = items[0][0]
    page_w, page_h = landscape(A4)
    half = page_w / 2
    margin = 9 * mm
    frame_w, frame_h = half - 2 * margin, page_h - margin - 14 * mm
    frames = [Frame(margin + i * half, 14 * mm, frame_w, frame_h, id=f"half{i}", leftPadding=0, rightPadding=0,
                    topPadding=0, bottomPadding=0) for i in (0, 1)]

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#94A3B8"))
        canvas.setDash(3, 3)
        canvas.line(half, 8 * mm, half, page_h - 8 * mm)
        canvas.setDash()
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.setFont("Helvetica", 6.5)
        motto = (getattr(school, "motto", "") or "").strip()
        for i in (0, 1):
            canvas.drawString(margin + i * half, 7 * mm, "Document généré par KIS Kalanso")
            if motto:
                canvas.drawRightString((i + 1) * half - margin, 7 * mm, motto[:70])
        canvas.restoreState()

    doc = BaseDocTemplate(response, pagesize=(page_w, page_h), title=title, author=school.name,
                          leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=14 * mm)
    doc.addPageTemplates([PageTemplate(id="two", frames=frames, onPage=decorate)])
    story = []
    for index, (_school, build, label) in enumerate(items):
        if index:
            story.append(FrameBreak())
        story.append(KeepInFrame(frame_w, frame_h, build(frame_w, _pdf_styles(scale=0.82), label), mode="shrink"))
    doc.build(story)
    return response


def two_copies_pdf(response, build_story, school, title):
    """Deux exemplaires du même reçu sur une feuille : parent à gauche, établissement à droite."""
    return receipts_two_per_page(response, [(school, build_story, "Exemplaire parent"),
                                            (school, build_story, "Exemplaire établissement")], title)


def _grid(data, widths, total_row=False):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle
    table = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F2D5C")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C8D0DA")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if total_row:
        style.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F3F6FA")))
    table.setStyle(TableStyle(style))
    return table


def batch_receipt_builder(batch):
    """(établissement, build) pour le reçu d'un encaissement groupé ; None s'il est vide.
    ``build(width, styles, copy_label=None)`` renvoie les éléments du reçu pour une largeur donnée."""
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer, Table

    payments = list(batch.payments.select_related(
        "invoice__enrollment__student", "invoice__enrollment__classe", "invoice__enrollment__school_year__school", "invoice__fee_type",
    ).order_by("id"))
    if not payments:
        return None
    school = payments[0].invoice.enrollment.school_year.school
    cur = school.currency

    def build(width, st, copy_label=None):
        k = width / (178 * mm)          # colonnes proportionnelles à la largeur disponible
        story = [Paragraph(copy_label, st["copy"])] if copy_label else []
        story += [_school_identity_story(school, st["styles"], width), Spacer(1, 6 * mm * k),
                  Paragraph("REÇU DE PAIEMENT", st["title"]), Paragraph(f"N° {escape(batch.receipt_number)}", st["center"]), Spacer(1, 5 * mm * k)]
        info = [[Paragraph("Date", st["label"]), Paragraph(batch.date.strftime("%d/%m/%Y"), st["value"]),
                 Paragraph("Année scolaire", st["label"]), Paragraph(escape(payments[0].invoice.enrollment.school_year.name), st["value"])]]
        if batch.payer_name:
            info.append([Paragraph("Versé par", st["label"]), Paragraph(escape(batch.payer_name), st["value"]), "", ""])
        story += [Table(info, colWidths=[28 * mm * k, width / 2 - 28 * mm * k, 32 * mm * k, width / 2 - 32 * mm * k], hAlign="LEFT"), Spacer(1, 5 * mm * k)]
        data = [[Paragraph(h, st["head"]) for h in ("Élève", "Classe", "Frais", "Montant du frais", "Versé ce jour", "Reste à payer")]]
        for p in payments:
            inv = p.invoice
            data.append([Paragraph(escape(str(inv.enrollment.student)), st["cell"]), Paragraph(escape(inv.enrollment.classe.display_name), st["cell"]),
                         Paragraph(escape(inv.label), st["cell"]), Paragraph(_money(inv.total_amount, cur), st["cellr"]),
                         Paragraph(_money(p.amount, cur), st["cellb"]), Paragraph(_money(inv.reste, cur), st["cellr"])])
        total = sum((p.amount for p in payments), Decimal("0"))
        remaining = sum((p.invoice.reste for p in payments), Decimal("0"))
        data.append([Paragraph("<b>TOTAL</b>", st["cell"]), "", "", "", Paragraph(_money(total, cur), st["cellb"]), Paragraph(_money(remaining, cur), st["cellr"])])
        cols = [w * mm * k for w in (40, 26, 38, 26, 24)]
        story += [_grid(data, cols + [width - sum(cols)], total_row=True), Spacer(1, 6 * mm * k)]
        if batch.comment:
            story += [Paragraph(f"<b>Commentaire :</b> {escape(batch.comment)}", st["value"]), Spacer(1, 4 * mm * k)]
        story += [Spacer(1, 10 * mm * k), Paragraph("Signature / Cachet de l'établissement", st["label"])]
        return story

    return school, build


@login_required
def batch_receipt_pdf(request, batch_id):
    """Reçu unique d'un encaissement groupé (plusieurs frais, plusieurs enfants)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate

    batch = get_object_or_404(PaymentBatch, pk=batch_id)
    built = batch_receipt_builder(batch)
    if not built:
        return HttpResponse("Reçu vide.", status=404)
    school, build = built
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="recu_{batch.receipt_number}.pdf"'
    if request.GET.get("exemplaires") == "2":
        return two_copies_pdf(response, build, school, f"Reçu {batch.receipt_number}")
    doc = SimpleDocTemplate(response, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=14 * mm, bottomMargin=16 * mm,
                            title=f"Reçu {batch.receipt_number}", author=school.name)
    story = build(A4[0] - 32 * mm, _pdf_styles())
    doc.build(story, onFirstPage=lambda c, d: _draw_internal_footer(c, d, school), onLaterPages=lambda c, d: _draw_internal_footer(c, d, school))
    return response


@login_required
def family_statement_pdf(request, enrollment_id):
    """Situation financière de toute la famille sur un seul document."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer

    enrollment = get_object_or_404(Enrollment.objects.select_related("student", "school_year__school"), pk=enrollment_id)
    family = family_enrollments(enrollment)
    school = enrollment.school_year.school
    cur = school.currency
    st = _pdf_styles()
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="situation_famille_{enrollment.student.last_name}.pdf"'
    doc = SimpleDocTemplate(response, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=14 * mm, bottomMargin=16 * mm,
                            title="Situation financière — famille", author=school.name)
    width = A4[0] - 32 * mm
    student = enrollment.student
    parents = student.responsible_label or "—"
    story = [_school_identity_story(school, st["styles"], width), Spacer(1, 6 * mm),
             Paragraph("FACTURE FAMILLE — SITUATION FINANCIÈRE", st["title"]),
             Paragraph(f"Année scolaire {escape(enrollment.school_year.name)} · Responsable : {escape(parents)}"
                       + (f" · Tél. {escape(student.responsible_phone)}" if student.responsible_phone else ""), st["center"]), Spacer(1, 6 * mm)]
    grand_total = grand_paid = Decimal("0")
    for member in family:
        invoices = list(Invoice.objects.filter(enrollment=member).select_related("fee_type", "enrollment__school_year").order_by("fee_type__name"))
        # Reliquats des autres années encore dus (anciennes années, années reprises).
        invoices += list(Invoice.objects.filter(enrollment__student_id=member.student_id, paid_amount__lt=F("total_amount"))
                         .exclude(enrollment=member).select_related("fee_type", "enrollment__school_year")
                         .order_by("enrollment__school_year__start_date", "fee_type__name"))
        data = [[Paragraph(h, st["head"]) for h in ("Frais", "Montant", "Payé", "Reste")]]
        total = paid = Decimal("0")
        for inv in invoices:
            label = inv.label
            if inv.enrollment_id != member.id and inv.enrollment.school_year.name not in label:
                label += f" ({inv.enrollment.school_year.name})"
            data.append([Paragraph(escape(label), st["cell"]), Paragraph(_money(inv.total_amount, cur), st["cellr"]),
                         Paragraph(_money(inv.paid_amount, cur), st["cellr"]), Paragraph(_money(inv.reste, cur), st["cellb"])])
            total += inv.total_amount
            paid += inv.paid_amount
        data.append([Paragraph("<b>Sous-total</b>", st["cell"]), Paragraph(_money(total, cur), st["cellr"]),
                     Paragraph(_money(paid, cur), st["cellr"]), Paragraph(_money(total - paid, cur), st["cellb"])])
        grand_total += total
        grand_paid += paid
        story.append(KeepTogether([
            Paragraph(f"<b>{escape(str(member.student))}</b> — {escape(member.classe.display_name)}"
                      + (f" · matricule {escape(member.student.matricule)}" if member.student.matricule else ""), st["value"]),
            Spacer(1, 2 * mm),
            _grid(data, [width - 3 * 34 * mm, 34 * mm, 34 * mm, 34 * mm], total_row=True),
            Spacer(1, 5 * mm),
        ]))
    summary = [[Paragraph(h, st["head"]) for h in ("Total famille", "Montant", "Payé", "Reste à payer")],
               [Paragraph(f"<b>{len(family)} enfant(s)</b>", st["cell"]), Paragraph(_money(grand_total, cur), st["cellr"]),
                Paragraph(_money(grand_paid, cur), st["cellr"]), Paragraph(_money(grand_total - grand_paid, cur), st["cellb"])]]
    story += [_grid(summary, [width - 3 * 34 * mm, 34 * mm, 34 * mm, 34 * mm])]
    doc.build(story, onFirstPage=lambda c, d: _draw_internal_footer(c, d, school), onLaterPages=lambda c, d: _draw_internal_footer(c, d, school))
    return response


@login_required
def receipts_print_pdf(request):
    """Impression groupée des reçus, deux par feuille (V8-7).

    ``?recu=b12&recu=p40`` : reçus choisis dans le journal (b = encaissement
    groupé, p = paiement isolé) ; ``?date=2026-10-13`` : tous les reçus du jour.
    """
    import datetime as _dt
    from .views import payment_receipt_builder

    keys = request.GET.getlist("recu")
    if request.GET.get("date"):
        try:
            day = _dt.date.fromisoformat(request.GET["date"])
        except ValueError:
            return HttpResponse("Date invalide.", status=400)
        keys = []
        for p in Payment.objects.filter(date=day, is_carryover=False).order_by("id"):
            key = f"b{p.batch_id}" if p.batch_id else f"p{p.pk}"
            if key not in keys:
                keys.append(key)
    items = []
    for key in dict.fromkeys(keys):
        built = None
        if key.startswith("b") and key[1:].isdigit():
            batch = PaymentBatch.objects.filter(pk=key[1:]).first()
            built = batch_receipt_builder(batch) if batch else None
        elif key.startswith("p") and key[1:].isdigit():
            payment = Payment.objects.filter(pk=key[1:], is_carryover=False).select_related(
                "invoice__enrollment__student", "invoice__enrollment__classe", "invoice__enrollment__school_year__school",
                "invoice__fee_type").first()
            if payment and payment.batch_id:
                built = batch_receipt_builder(payment.batch)
            elif payment:
                built = payment_receipt_builder(payment)
        if built:
            items.append((built[0], built[1], None))
    if not items:
        return HttpResponse("Aucun reçu à imprimer.", status=404)
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="recus.pdf"'
    return receipts_two_per_page(response, items, "Reçus")
