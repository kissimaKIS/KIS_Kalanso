import unicodedata
from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Case, CharField, Count, F, Sum, Value, When
from django.db.models.functions import Coalesce, Concat, NullIf
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.html import escape
from administration.models import SchoolYear
from finance.models import Payment
from ..models import BudgetCategory, BudgetEntry
from ..forms import BudgetEntryForm
from common.pagination import paginate
from common.years import viewed_year


def _is_modal_request(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _modal_reload_response():
    return HttpResponse("", headers={"HX-Trigger": "kisModalReload"})


SCHOOL_GROUPS = [
    ("registration", "Frais d'inscription"),
    ("reenrollment", "Frais de réinscription"),
    ("tuition", "Scolarité"),
    ("optional", "Options"),
    ("arrears", "Reliquats des années passées"),
]
SCHOOL_LABELS = dict(SCHOOL_GROUPS)
SCHOOL_ORDER = {key: index for index, (key, _) in enumerate(SCHOOL_GROUPS)}


def _budget_filters(request, entries):
    category_id = (request.GET.get("category") or "").strip()
    kind = (request.GET.get("kind") or "").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    if category_id == "school_payments" or category_id.startswith("school:"):
        entries = entries.none()
    elif category_id.isdigit():
        entries = entries.filter(category_id=int(category_id))
    if kind in {"REVENUE", "EXPENSE"}:
        entries = entries.filter(kind=kind)
    if date_from:
        entries = entries.filter(date__gte=date_from)
    if date_to:
        entries = entries.filter(date__lte=date_to)
    return entries, {"category": category_id, "kind": kind, "date_from": date_from, "date_to": date_to}


def _school_payments(year, filters):
    """Encaissements scolaires de l'année selon les filtres (catégorie, type, période)."""
    payments = Payment.objects.filter(invoice__enrollment__school_year=year)
    category = filters.get("category") or ""
    if category.startswith("school:"):
        payments = payments.filter(invoice__fee_type__category=category.split(":", 1)[1])
    elif category and category != "school_payments":
        payments = payments.none()
    if filters.get("kind") == "EXPENSE":
        payments = payments.none()
    if filters.get("date_from"):
        payments = payments.filter(date__gte=filters["date_from"])
    if filters.get("date_to"):
        payments = payments.filter(date__lte=filters["date_to"])
    return payments


def _school_rows(payments):
    """Recettes scolaires regroupées : une ligne par jour et par type de frais
    (inscription, scolarité, options…), au lieu d'une ligne par versement."""
    grouped = (payments.order_by().values("date", "invoice__fee_type__category")
               .annotate(total=Sum("amount"), n=Count("id")))
    rows = []
    for g in grouped:
        key = g["invoice__fee_type__category"]
        label = SCHOOL_LABELS.get(key, "Autres frais")
        plural = "s" if g["n"] > 1 else ""
        rows.append({"date": g["date"], "label": f"Encaissements du jour — {label} ({g['n']} versement{plural})",
                     "category": f"Recettes scolaires · {label}", "kind": "Recette", "amount": g["total"],
                     "notes": "—", "sort": 1, "order": SCHOOL_ORDER.get(key, 9)})
    return rows


def _school_totals(payments):
    totals = {row["invoice__fee_type__category"]: row["total"] for row in
              payments.order_by().values("invoice__fee_type__category").annotate(total=Sum("amount"))}
    return [{"key": key, "label": label, "amount": totals[key]} for key, label in SCHOOL_GROUPS if totals.get(key)]


def _filtered_operations(year, filters):
    entries = BudgetEntry.objects.filter(school_year=year).select_related("category")
    entries, _ = _budget_filters(type("R", (), {"GET": filters})(), entries)
    operations = [{"date": e.date, "label": e.label, "category": str(e.category), "kind": e.get_kind_display(),
                   "amount": e.amount, "notes": e.notes or "—", "sort": 0, "order": 0} for e in entries]
    operations += _school_rows(_school_payments(year, filters))
    # Plus récent d'abord ; dans une journée, les recettes scolaires dans l'ordre inscription, scolarité…
    operations.sort(key=lambda x: (-x["date"].toordinal(), x["sort"], x["order"]))
    return operations


@login_required
def budget_list(request):
    year = viewed_year()
    base_entries = BudgetEntry.objects.filter(school_year=year).select_related("category") if year else BudgetEntry.objects.none()
    entries, filters = _budget_filters(request, base_entries)
    manual_revenue = entries.filter(kind="REVENUE").aggregate(v=Sum("amount"))["v"] or Decimal("0")
    expenses = entries.filter(kind="EXPENSE").aggregate(v=Sum("amount"))["v"] or Decimal("0")
    payments = _school_payments(year, filters) if year else Payment.objects.none()
    payment_revenue = payments.aggregate(v=Sum("amount"))["v"] or Decimal("0")
    revenue = manual_revenue + payment_revenue
    operations = _filtered_operations(year, filters) if year else []
    page_obj = paginate(request, operations)
    categories = BudgetCategory.objects.filter(is_active=True).order_by("name")
    return render(request, "pilotage/budget/list.html", {
        "entries": entries, "operations": page_obj, "page_obj": page_obj, "revenue": revenue,
        "manual_revenue": manual_revenue, "payment_revenue": payment_revenue,
        "school_totals": _school_totals(payments) if year else [], "school_groups": SCHOOL_GROUPS,
        "expenses": expenses, "balance": revenue - expenses,
        "categories": categories, "filters": filters, "currency": year.school.currency if year else "FCFA",
    })


@login_required
def budget_create(request):
    year = viewed_year()
    form = BudgetEntryForm(request.POST or None)
    if request.method == "POST" and form.is_valid() and year:
        obj = form.save(commit=False)
        new_category = form.cleaned_data.get("new_category")
        if new_category:
            category, _ = BudgetCategory.objects.get_or_create(name=new_category, defaults={"is_active": True})
            if not category.is_active:
                category.is_active = True
                category.save(update_fields=["is_active"])
            obj.category = category
        obj.school_year = year
        obj.created_by = request.user
        obj.save()
        messages.success(request, "Opération budgétaire enregistrée.")
        if _is_modal_request(request):
            return _modal_reload_response()
        return redirect("budget_list")
    if _is_modal_request(request):
        return render(request, "pilotage/budget/_modal_entry_form.html", {"form": form, "action_url": request.path})
    return render(request, "pilotage/budget/form.html", {"form": form})


@login_required
def import_budget(request):
    """Importe des opérations budgétaires (recettes/dépenses) depuis Excel.

    Pensé pour la migration d'un tableau Excel existant de recettes/dépenses :
    chaque ligne du fichier devient une opération budgétaire indépendante
    (pas de fusion par identifiant, contrairement aux imports élèves/personnel,
    car un tableau de recettes/dépenses n'a normalement pas de clé stable).
    """
    year = viewed_year()
    if not year:
        messages.error(request, "Aucune année scolaire active n'est configurée.")
        return redirect("budget_list")
    if request.method == "POST":
        uploaded = request.FILES.get("file")
        if not uploaded:
            messages.error(request, "Sélectionnez un fichier Excel.")
            return redirect("import_budget")
        try:
            import pandas as pd
            from collections import Counter
            from common.excel_import import ImportFileError, prepare, read_excel, summary
            df = prepare(read_excel(uploaded), "budget", {
                "Libellé": "label", "Type": "kind", "Montant": "amount",
                "Date": "date", "Catégorie": "category", "Observation": "notes",
            }, ("label", "kind", "amount"))

            def normalize(value):
                if value is None or pd.isna(value):
                    return ""
                if isinstance(value, float) and value.is_integer():
                    value = int(value)
                text = str(value).strip()
                return "" if text.lower() == "nan" else text

            def normalize_kind(value):
                text = unicodedata.normalize("NFKD", normalize(value)).encode("ascii", "ignore").decode("ascii").lower()
                if text in {"recette", "recettes", "revenue", "entree", "revenu"}:
                    return "REVENUE"
                if text in {"depense", "depenses", "expense", "sortie"}:
                    return "EXPENSE"
                return None

            # Anti-doublon : une opération identique (type, libellé, montant,
            # catégorie et date si le fichier en donne une) déjà présente dans
            # l'année n'est pas recréée. Si le fichier contient volontairement
            # deux opérations identiques, les deux sont gardées : on compare le
            # nombre d'occurrences du fichier à celui déjà en base.
            existing = Counter()
            existing_no_date = Counter()
            for e in BudgetEntry.objects.filter(school_year=year).select_related("category"):
                base = (e.kind, e.label.strip().lower(), Decimal(e.amount).normalize(), e.category.name.strip().lower())
                existing[base + (e.date,)] += 1
                existing_no_date[base] += 1
            seen = Counter()

            created, duplicates, errors = 0, 0, []
            with transaction.atomic():
                for idx, row in df.iterrows():
                    line = idx + 2
                    label = normalize(row.get("label"))
                    kind = normalize_kind(row.get("kind"))
                    amount_raw = row.get("amount")
                    amount_missing = amount_raw is None or (isinstance(amount_raw, float) and pd.isna(amount_raw))
                    if not label or kind is None or amount_missing:
                        errors.append(f"Ligne {line} : Libellé, Type (Recette ou Dépense) et Montant sont obligatoires.")
                        continue
                    try:
                        amount = Decimal(str(amount_raw).replace(" ", "").replace(",", "."))
                    except (InvalidOperation, ValueError):
                        errors.append(f"Ligne {line} : montant invalide ({amount_raw}).")
                        continue
                    if amount <= 0:
                        errors.append(f"Ligne {line} : le montant doit être supérieur à zéro.")
                        continue

                    category_name = (normalize(row.get("category")) if "category" in df.columns else "") or "Import Excel"
                    has_date = False
                    date_value = row.get("date") if "date" in df.columns else None
                    if date_value is not None and not pd.isna(date_value):
                        try:
                            date_value = pd.to_datetime(date_value, dayfirst=True).date()
                            has_date = True
                        except Exception:
                            errors.append(f"Ligne {line} : date illisible ({date_value}).")
                            continue
                    else:
                        date_value = timezone.localdate()

                    base = (kind, label.lower(), amount.normalize(), category_name.lower())
                    key = base + (date_value,) if has_date else base
                    seen[key] += 1
                    already = (existing[key] if has_date else existing_no_date[key])
                    if seen[key] <= already:
                        duplicates += 1
                        continue

                    category, _ = BudgetCategory.objects.get_or_create(name=category_name, defaults={"is_active": True})
                    if not category.is_active:
                        category.is_active = True
                        category.save(update_fields=["is_active"])
                    notes = normalize(row.get("notes")) if "notes" in df.columns else ""
                    BudgetEntry.objects.create(
                        school_year=year, category=category, kind=kind, label=label,
                        amount=amount, date=date_value, notes=notes,
                        created_by=request.user if request.user.is_authenticated else None,
                    )
                    created += 1

            if created == 0 and duplicates and not errors:
                messages.warning(request, f"Ce fichier a déjà été importé : ses {duplicates} opération(s) sont déjà dans le budget {year.name}. Rien n'a été ajouté.")
            else:
                text = summary([
                    f"{created} opération(s) importée(s)",
                    f"{duplicates} déjà présente(s) dans le budget, non dupliquée(s)" if duplicates else "",
                ], errors)
                (messages.warning if errors else messages.success)(request, text)
            return redirect("budget_list")
        except ImportFileError as exc:
            messages.error(request, f"Import refusé : {exc}")
        except Exception as exc:
            messages.error(request, f"Import impossible : {exc}")
    return render(request, "pilotage/budget/import_budget.html", {"year": year})


@login_required
def budget_pdf(request):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from finance.views import _school_identity_story, _draw_internal_footer

    year = viewed_year()
    if not year:
        return HttpResponse("Aucune année scolaire active.", status=404)
    entries = BudgetEntry.objects.filter(school_year=year).select_related("category")
    entries, filters = _budget_filters(request, entries)
    operations = _filtered_operations(year, filters)
    revenue = sum((o["amount"] for o in operations if o["kind"] == "Recette"), Decimal("0"))
    expenses = sum((o["amount"] for o in operations if o["kind"] == "Dépense"), Decimal("0"))
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="budget.pdf"'
    doc = SimpleDocTemplate(response, pagesize=landscape(A4), rightMargin=12*mm, leftMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm, title="Budget")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, leading=10))
    styles.add(ParagraphStyle("SchoolSmall", parent=styles["Normal"], fontSize=8.5, leading=10))
    styles.add(ParagraphStyle("SchoolName", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=11, leading=13))
    styles.add(ParagraphStyle("TitleK", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=colors.HexColor("#17365D")))
    story = [_school_identity_story(year.school, styles, landscape(A4)[0]-24*mm), Spacer(1, 5*mm), Paragraph("BUDGET", styles["TitleK"]), Paragraph(f"Année scolaire : {escape(year.name)}", styles["Small"])]
    active_filters=[]
    if filters["category"]:
        if filters["category"] == "school_payments": active_filters.append("Catégorie : Recettes scolaires")
        elif filters["category"].startswith("school:"): active_filters.append("Catégorie : Recettes scolaires · " + escape(SCHOOL_LABELS.get(filters["category"][7:], "")))
        elif filters["category"].isdigit():
            c=BudgetCategory.objects.filter(pk=int(filters["category"])).first(); active_filters.append(f"Catégorie : {escape(c.name) if c else '—'}")
    if filters["kind"]: active_filters.append("Type : " + ("Recette" if filters["kind"] == "REVENUE" else "Dépense"))
    if filters["date_from"]: active_filters.append(f"Du : {escape(filters['date_from'])}")
    if filters["date_to"]: active_filters.append(f"Au : {escape(filters['date_to'])}")
    if active_filters: story.append(Paragraph(" — ".join(active_filters), styles["Small"]))
    story.append(Spacer(1, 4*mm))
    data=[["Date","Libellé","Catégorie","Type","Montant","Observation"]]
    for o in operations:
        data.append([o["date"].strftime("%d/%m/%Y"), Paragraph(escape(o["label"]), styles["Small"]), Paragraph(escape(o["category"]), styles["Small"]), o["kind"], f"{o['amount']:,.0f} {year.school.currency}", Paragraph(escape(str(o["notes"])), styles["Small"])])
    data.append(["","TOTAL RECETTES","", "Recette", f"{revenue:,.0f} {year.school.currency}",""])
    data.append(["","TOTAL DÉPENSES","", "Dépense", f"{expenses:,.0f} {year.school.currency}",""])
    data.append(["","SOLDE","", "", f"{revenue-expenses:,.0f} {year.school.currency}",""])
    table=Table(data, colWidths=[24*mm,72*mm,45*mm,25*mm,35*mm,65*mm], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17365D")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#CBD5E1")),("VALIGN",(0,0),(-1,-1),"TOP"),("ALIGN",(4,1),(4,-1),"RIGHT"),("BACKGROUND",(0,-3),(-1,-1),colors.HexColor("#F1F5F9")),("FONTNAME",(0,-3),(-1,-1),"Helvetica-Bold")]))
    story.append(table)
    doc.build(story, onFirstPage=lambda c, d: _draw_internal_footer(c, d, year.school), onLaterPages=lambda c, d: _draw_internal_footer(c, d, year.school))
    return response


@login_required
def cash_statement_pdf(request):
    from decimal import Decimal
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from finance.views import _school_identity_story, _draw_internal_footer

    year = viewed_year()
    if not year:
        return HttpResponse("Aucune année scolaire active.", status=404)
    raw_filters = {
        "category": (request.GET.get("category") or "").strip(),
        "kind": (request.GET.get("kind") or "").strip(),
        "date_from": (request.GET.get("date_from") or "").strip(),
        "date_to": (request.GET.get("date_to") or "").strip(),
    }
    operations = _filtered_operations(year, raw_filters)
    operations = sorted(operations, key=lambda x: x["date"])
    balance = Decimal("0")
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="situation-caisse.pdf"'
    doc = SimpleDocTemplate(response, pagesize=landscape(A4), rightMargin=12*mm, leftMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm, title="Situation de caisse")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, leading=10))
    styles.add(ParagraphStyle("SchoolSmall", parent=styles["Normal"], fontSize=8.5, leading=10))
    styles.add(ParagraphStyle("SchoolName", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=11, leading=13))
    styles.add(ParagraphStyle("TitleK", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=colors.HexColor("#17365D")))
    story = [_school_identity_story(year.school, styles, landscape(A4)[0]-24*mm), Spacer(1, 5*mm), Paragraph("SITUATION DE CAISSE", styles["TitleK"]), Paragraph(f"Année scolaire : {escape(year.name)}", styles["Small"])]
    if raw_filters["date_from"] or raw_filters["date_to"]:
        period = f"Du {escape(raw_filters['date_from']) if raw_filters['date_from'] else 'début'} au {escape(raw_filters['date_to']) if raw_filters['date_to'] else 'fin'}"
        story.append(Paragraph(period, styles["Small"]))
    story.append(Spacer(1, 4*mm))
    data = [["Date", "Libellé", "Catégorie", "Entrée", "Sortie", "Solde cumulé"]]
    for op in operations:
        amount = Decimal(str(op["amount"]))
        entry = amount if op["kind"] == "Recette" else Decimal("0")
        sortie = amount if op["kind"] == "Dépense" else Decimal("0")
        balance += entry - sortie
        data.append([op["date"].strftime("%d/%m/%Y"), Paragraph(escape(str(op["label"])), styles["Small"]), Paragraph(escape(str(op["category"])), styles["Small"]), f"{entry:,.0f} {year.school.currency}" if entry else "—", f"{sortie:,.0f} {year.school.currency}" if sortie else "—", f"{balance:,.0f} {year.school.currency}"])
    if not operations:
        data.append(["", "Aucun mouvement sur la période sélectionnée.", "", "", "", "0"])
    table = Table(data, colWidths=[24*mm, 78*mm, 48*mm, 35*mm, 35*mm, 40*mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#17365D")), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 8),
        ("GRID", (0,0), (-1,-1), .3, colors.HexColor("#CBD5E1")), ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("ALIGN", (3,1), (-1,-1), "RIGHT"),
    ]))
    story.append(table)
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(f"Solde des mouvements affichés : <b>{balance:,.0f} {escape(year.school.currency)}</b>", styles["Small"]))
    story.append(Paragraph("Document interne de gestion — le solde présenté correspond aux mouvements affichés selon les filtres sélectionnés.", styles["Small"]))
    doc.build(story, onFirstPage=lambda c, d: _draw_internal_footer(c, d, year.school), onLaterPages=lambda c, d: _draw_internal_footer(c, d, year.school))
    return response
