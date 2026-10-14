from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from decimal import Decimal
import unicodedata
from xml.sax.saxutils import escape
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse

from administration.models import SchoolYear
from common.pagination import paginate
from common.lazy import pandas as pd
from administration.forms import StudentForm
from administration.permissions import permission_required
from pedagogie.models import Enrollment, Classe, Student, EducationLevel, PedagogicalTrack, SchoolYearLevel, SchoolYearTrack
from finance.models import Invoice, Payment, StudentOption, FeeType, EnrollmentDiscount
from finance.services.discount_service import apply_enrollment_discount
from finance.services.grouped_payment import parse_amount, record_grouped_payment
from finance.services.options import add_option, read_quantity_price
from common.years import viewed_year


PIECE_SLOTS = 6


def save_enrollment_pieces(request, student, classe):
    """Pièces du dossier jointes à l'inscription (acte de naissance, vaccination…)."""
    from documents.models import Document
    for i in range(PIECE_SLOTS):
        upload = request.FILES.get(f"piece_file_{i}")
        if not upload:
            continue
        title = (request.POST.get(f"piece_type_{i}") or request.POST.get(f"piece_title_{i}") or "").strip() or upload.name
        Document.objects.create(title=title[:200], category="STUDENT", file=upload, student=student, classe=classe,
                                uploaded_by=request.user if request.user.is_authenticated else None)


@login_required
def enrollment_create(request):
    """Inscription complète dans le contexte de la seule année active.

    Une classe réelle peut être réutilisée si elle existe déjà ; sinon elle est
    créée automatiquement à partir du niveau/parcours/groupe saisi dans le
    même parcours d'inscription. Les frais obligatoires sont appliqués par la
    finance ; les options sont choisies ici.
    """
    year = SchoolYear.objects.filter(is_active=True).select_related("school").first()
    if not year:
        messages.error(request, "Aucune année scolaire active n'est configurée.")
        return redirect("school_year_list")

    school = year.school
    classes = Classe.objects.filter(school_year=year).select_related(
        "education_level", "pedagogical_track"
    ).order_by("education_level__order", "education_level__name", "pedagogical_track__name", "group", "name")

    form = StudentForm(request.POST or None, request.FILES or None,
                       initial={"recruitment_year": year.start_date.year})
    selected_class = request.POST.get("classe", "")
    selected_type = request.POST.get("student_type", "regulier")

    # La classe est la seule source de vérité pour le niveau et le parcours.
    # Le formulaire ne demande donc plus un niveau séparé qui pourrait être
    # incohérent avec la classe choisie.
    target_class = classes.filter(pk=selected_class).first() if selected_class else None

    # Les frais de base dépendent du secteur de la classe. Ils ne doivent donc
    # être affichés qu'une fois la classe connue, et uniquement pour son secteur.
    available_fees = FeeType.objects.none()
    required_fees = FeeType.objects.none()
    optional_fees = FeeType.objects.none()
    if target_class:
        required_filter = Q(
            is_required=True,
            category__in=[FeeType.Category.REGISTRATION, FeeType.Category.TUITION],
        ) & (
            Q(classe=target_class)
            | Q(classe__isnull=True, education_level=target_class.education_level)
            | Q(
                classe__isnull=True, education_level__isnull=True,
                school_type=target_class.education_level.school_type
            )
        )
        optional_filter = Q(category=FeeType.Category.OPTIONAL) & (
            Q(classe=target_class) | Q(classe__isnull=True)
        )
        available_fees = FeeType.objects.filter(
            Q(required_filter) | Q(optional_filter), school_year=year, is_active=True
        ).order_by("category", "name")
        required_fees = available_fees.filter(category__in=[FeeType.Category.REGISTRATION, FeeType.Category.TUITION])
        optional_fees = available_fees.filter(category=FeeType.Category.OPTIONAL)

    if request.method == "POST" and form.is_valid():
        if selected_type not in dict(Enrollment.TYPE_CHOICES):
            form.add_error(None, "Type d'élève invalide.")
        else:
            try:
                with transaction.atomic():
                    if not target_class:
                        raise ValueError("Sélectionnez une classe pour l'inscription.")

                    if selected_type == "cl" and not target_class.education_level.allows_free_candidate:
                        raise ValueError("Le statut candidat libre n'est pas autorisé pour ce niveau.")

                    student = form.save(commit=False)
                    # Matricule proposé automatiquement : on recalcule le n° d'ordre au moment
                    # d'enregistrer, au cas où un autre élève l'aurait pris entre-temps.
                    from administration.services import matricule as mat
                    if not student.matricule or mat.is_auto(student.matricule, school):
                        proposal = mat.propose(school, student.recruitment_year, student.sex)
                        if proposal:
                            student.matricule = proposal
                    student.save()
                    enrollment = Enrollment.objects.create(
                        student=student, classe=target_class, school_year=year,
                        student_type=selected_type,
                    )
                    save_enrollment_pieces(request, student, target_class)

                    # La remise est un ajustement financier de l'inscription, jamais un type de frais.
                    discount_type = (request.POST.get("discount_type") or "").strip()
                    discount_value = (request.POST.get("discount_value") or "").strip()
                    discount_reason = (request.POST.get("discount_reason") or "").strip()
                    discount_note = (request.POST.get("discount_note") or "").strip()

                    # Les frais optionnels sont choisis au moment de l'inscription.
                    optional_ids = set(request.POST.getlist("optional_fees"))
                    for fee in FeeType.objects.filter(
                        pk__in=optional_ids, school_year=year,
                        category=FeeType.Category.OPTIONAL, is_active=True).filter(Q(classe=target_class) | Q(classe__isnull=True)
                    ):
                        quantity, unit_price = read_quantity_price(request.POST, fee)
                        add_option(enrollment, fee, quantity, unit_price)

                    if discount_value:
                        if discount_type not in dict(EnrollmentDiscount.DiscountType.choices):
                            raise ValidationError("Type de remise invalide.")
                        apply_enrollment_discount(
                            enrollment, discount_type, discount_value,
                            discount_reason, discount_note,
                        )

                    # Paiement initial facultatif : plusieurs frais peuvent être
                    # réglés en une fois (ex. inscription + 1er trimestre) ;
                    # un seul reçu groupé est alors produit.
                    payment_comment = (request.POST.get("payment_comment") or "").strip()
                    batch = None
                    lines = []
                    for fee_id in dict.fromkeys(request.POST.getlist("pay_fee")):
                        amount = parse_amount(request.POST.get(f"pay_amount_{fee_id}"))
                        if not amount:
                            continue
                        invoice = Invoice.objects.filter(
                            enrollment=enrollment, fee_type_id=fee_id
                        ).first()
                        if not invoice:
                            raise ValidationError("Un frais choisi n'est pas facturé pour cette inscription.")
                        # Frais détaillé en postes : ventilation choisie sur le formulaire.
                        alloc = []
                        for index, line in enumerate(invoice.lines.all()):
                            if str(index) not in request.POST.getlist(f"pay_line_{fee_id}"):
                                continue
                            part = parse_amount(request.POST.get(f"pay_line_amount_{fee_id}_{index}"))
                            if part:
                                alloc.append((line, part))
                        lines.append((invoice, amount, alloc) if alloc else (invoice, amount))
                    if lines:
                        batch = record_grouped_payment(
                            lines,
                            payer_name=student.responsible_name,
                            comment=payment_comment,
                            user=request.user,
                        )

                messages.success(request, f"Inscription de {student} enregistrée.")
                from django.urls import reverse
                if batch:
                    # Confirmation dans l'application ; reçu unique dans une fenêtre séparée.
                    return redirect(f"{reverse('payment_done')}?batch={batch.id}")
                if request.POST.get("then_pay"):
                    return redirect("grouped_payment", enrollment_id=enrollment.id)
                return redirect("student_detail", student_id=student.id)
            except ValidationError as exc:
                form.add_error(None, " ".join(exc.messages))
            except ValueError as exc:
                form.add_error(None, str(exc))

    import json
    from administration.services import matricule as mat
    sigle = mat.school_sigle(school)
    next_number = mat.next_number(sigle)
    from documents.models import STUDENT_PIECES
    return render(request, "administration/students/enrollment_form.html", {
        "student_pieces": STUDENT_PIECES, "piece_slots": range(6),
        "matricule_sigle_json": json.dumps(sigle), "matricule_next_json": json.dumps(next_number),
        "matricule_example": mat.build(year.start_date.year, sigle, next_number, "M"),
        "form": form, "classes": classes,
        "available_fees": available_fees, "required_fees": required_fees, "optional_fees": optional_fees, "school_year": year,
        "selected_class": selected_class,
        "selected_student_type": selected_type,
    })


@login_required
def enrollment_fees(request):
    """Retourne les frais applicables à l'inscription selon la classe choisie.

    L'année scolaire reste celle qui est active ; la classe est donc le seul
    paramètre métier nécessaire pour rafraîchir la liste sans quitter le parcours.
    """
    year = SchoolYear.objects.filter(is_active=True).select_related("school").first()
    if not year:
        return render(request, "administration/students/_enrollment_fees.html", {
            "available_fees": [], "school_year": None,
        }, status=400)

    classes = Classe.objects.filter(school_year=year, school=year.school)
    selected_class = request.GET.get("classe", "")
    target_class = classes.filter(pk=selected_class).first() if selected_class else None

    available_fees = FeeType.objects.none()
    required_fees = FeeType.objects.none()
    optional_fees = FeeType.objects.none()
    if target_class:
        required_filter = Q(
            is_required=True,
            category__in=[FeeType.Category.REGISTRATION, FeeType.Category.TUITION],
        ) & (
            Q(classe=target_class)
            | Q(classe__isnull=True, education_level=target_class.education_level)
            | Q(
                classe__isnull=True, education_level__isnull=True,
                school_type=target_class.education_level.school_type
            )
        )
        optional_filter = Q(category=FeeType.Category.OPTIONAL) & (
            Q(classe=target_class) | Q(classe__isnull=True)
        )
        available_fees = FeeType.objects.filter(
            Q(required_filter) | Q(optional_filter), school_year=year, is_active=True
        ).order_by("category", "name")
        required_fees = available_fees.filter(category__in=[FeeType.Category.REGISTRATION, FeeType.Category.TUITION])
        optional_fees = available_fees.filter(category=FeeType.Category.OPTIONAL)

    required_total = sum((fee.amount for fee in required_fees), Decimal("0"))
    optional_total = Decimal("0")
    gross_total = required_total + optional_total

    return render(request, "administration/students/_enrollment_fees.html", {
        "available_fees": available_fees, "required_fees": required_fees, "optional_fees": optional_fees,
        "school_year": year, "required_total": required_total, "optional_total": optional_total,
        "gross_total": gross_total,
    })


@login_required
def student_list(request):
    """Élèves inscrits, pour l'année active ou n'importe quelle année passée.

    ``?annee=<id>`` affiche une année précise (y compris clôturée),
    ``?annee=all`` cherche dans toutes les années (un ancien élève, par exemple).
    """
    active = SchoolYear.objects.filter(is_active=True).select_related("school").first()
    all_years = list(SchoolYear.objects.select_related("school").order_by("-start_date"))
    if not all_years:
        messages.error(request, "Aucune année scolaire n'est configurée.")
        return redirect("school_year_list")

    selected_year = (request.GET.get("annee") or "").strip()
    all_mode = selected_year == "all"
    year = None
    if selected_year and not all_mode:
        year = next((y for y in all_years if str(y.pk) == selected_year), None)
    if year is None and not all_mode:
        year = viewed_year() or active or all_years[0]
    school = (year or active or all_years[0]).school

    query = (request.GET.get("q") or "").strip()
    classe_id = (request.GET.get("classe") or "").strip()
    enrollments = Enrollment.objects.filter(classe__school=school).select_related(
        "student", "classe", "classe__education_level", "classe__pedagogical_track", "school_year"
    )
    if not all_mode:
        enrollments = enrollments.filter(school_year=year)

    if query:
        enrollments = enrollments.filter(
            Q(student__first_name__icontains=query)
            | Q(student__last_name__icontains=query)
            | Q(student__matricule__icontains=query)
        )
    if classe_id:
        enrollments = enrollments.filter(classe_id=classe_id)

    enrollments = enrollments.order_by("student__last_name", "student__first_name", "-school_year__start_date")
    classes = Classe.objects.filter(school_year=year, school=school).select_related(
        "education_level", "pedagogical_track"
    ).order_by("education_level__order", "education_level__name", "group", "name") if year else Classe.objects.none()

    counts = enrollments.aggregate(
        total=Count("id"),
        boys=Count("id", filter=Q(student__sex="M")),
        girls=Count("id", filter=Q(student__sex="F")),
        unknown=Count("id", filter=Q(student__sex__isnull=True)),
    )
    page_obj = paginate(request, enrollments)
    return render(request, "administration/students/list.html", {
        "enrollments": page_obj,
        "page_obj": page_obj,
        "classes": classes,
        "viewed_year": year,
        "all_years": all_years,
        "all_mode": all_mode,
        "is_current_year": bool(year and active and year.pk == active.pk),
        "selected_year": selected_year,
        "query": query,
        "selected_classe": classe_id,
        "total_students": counts["total"],
        "boys": counts["boys"],
        "girls": counts["girls"],
        "unknown_sex": counts["unknown"],
    })


def _whatsapp_balance(student, invoices):
    """Lien WhatsApp « rappel de paiement » vers le parent, s'il reste quelque chose à payer."""
    from common import whatsapp
    if not any(i.reste > 0 for i in invoices):
        return ""
    school = invoices[0].enrollment.school_year.school
    return whatsapp.wa_url(whatsapp.family_phone(student), whatsapp.balance_text(student, invoices, school))


@login_required
def student_detail(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    from administration.documents_fondamental import is_fundamental
    from pedagogie.models import Term
    enrollments = list(student.enrollments.select_related("classe__education_level", "school_year").order_by("-school_year__start_date"))
    terms_by_year = {}
    for term in Term.objects.filter(school_year__in=[e.school_year_id for e in enrollments]).order_by("order", "id"):
        terms_by_year.setdefault(term.school_year_id, []).append(term)
    for e in enrollments:
        e.is_fundamental = is_fundamental(e)
        e.terms = terms_by_year.get(e.school_year_id, [])
    has_fundamental = any(e.is_fundamental for e in enrollments)
    documents = list(student.documents.select_related("classe").order_by("-uploaded_at"))
    invoices = list(Invoice.objects.filter(enrollment__student=student).select_related("fee_type", "enrollment__classe", "enrollment__school_year").prefetch_related("lines").order_by("-enrollment__school_year__start_date", "fee_type__category", "fee_type__name"))
    for invoice in invoices:
        # Postes (inscription, manuel, uniformes…) et argent reçu pas encore réparti.
        invoice.detail_lines = list(invoice.lines.all())
        invoice.to_ventilate = max(Decimal("0"), invoice.paid_amount - sum((l.paid_amount for l in invoice.detail_lines), Decimal("0"))) if invoice.detail_lines else Decimal("0")
    payments = Payment.objects.filter(invoice__enrollment__student=student).select_related("invoice__fee_type", "invoice__enrollment__school_year")
    options = StudentOption.objects.filter(enrollment__student=student, is_active=True).select_related("fee_type")
    # Inscription de l'année en cours (sinon la plus récente hors reprise) pour les actions de facturation ;
    # l'encaissement reprend toutes les factures ouvertes de l'élève, reliquats antérieurs compris.
    real = [e for e in enrollments if not e.school_year.is_archive]
    current_enrollment = next((e for e in real if e.school_year.is_active), real[0] if real else None)
    total_due = sum((i.reste for i in invoices), Decimal("0"))
    pay_enrollment = current_enrollment or (enrollments[0] if enrollments else None)
    if not total_due and not (current_enrollment and current_enrollment.school_year.is_active):
        pay_enrollment = None
    return render(request, "administration/students/student_detail.html", {
        "student": student, "enrollments": enrollments, "invoices": invoices, "documents": documents,
        "whatsapp_balance_url": _whatsapp_balance(student, invoices),
        "payments": payments, "options": options, "has_fundamental": has_fundamental,
        "current_enrollment": current_enrollment, "pay_enrollment": pay_enrollment, "total_due": total_due,
    })


@login_required
@permission_required("students.manage")
def student_edit(request, student_id):
    """Permet aux rôles habilités de corriger les informations d'un élève."""
    student = get_object_or_404(Student, id=student_id)
    form = StudentForm(request.POST or None, request.FILES or None, instance=student)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Informations de {student} mises à jour.")
        return redirect("student_detail", student_id=student.id)
    return render(request, "administration/students/edit_student.html", {"form": form, "student": student})


@login_required
def add_student(request, classe_id):
    year = SchoolYear.objects.filter(is_active=True).first()
    classe = get_object_or_404(Classe, id=classe_id, school_year=year)
    form = StudentForm(request.POST or None, request.FILES or None, initial={"recruitment_year": year.start_date.year})
    if request.method == "POST" and form.is_valid():
        from administration.services import matricule as mat
        with transaction.atomic():
            student = form.save(commit=False)
            if not student.matricule or mat.is_auto(student.matricule, year.school):
                student.matricule = mat.propose(year.school, student.recruitment_year, student.sex) or student.matricule
            student.save()
            Enrollment.objects.create(student=student, classe=classe, school_year=year)
        messages.success(request, "Élève enregistré.")
        return redirect("student_detail", student_id=student.id)
    return render(request, "administration/students/add_student.html", {"form": form, "classe": classe})


def _student_import_normalize_text(value):
    """Convertit une cellule Excel (NaN, nombre, texte…) en chaîne propre.

    Un Matricule ou un numéro de téléphone saisi comme nombre dans Excel
    arrive ici sous forme de float (ex. 70999999.0) : sans ce traitement, il
    serait stocké avec un ".0" parasite.
    """
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _student_import_parse_date(value):
    """Convertit une cellule Excel (date réelle ou texte JJ/MM/AAAA…) en date.

    ``pandas.to_datetime`` reconnaît aussi bien une vraie date Excel qu'un
    texte comme « 24/06/2010 » — contrairement à l'ancien code qui passait la
    valeur brute au champ Django, provoquant l'erreur « Le format de date...
    n'est pas valide » dès que la colonne Excel était au format texte.
    """
    if value is None or pd.isna(value):
        return None
    try:
        return pd.to_datetime(value, dayfirst=True).date()
    except (ValueError, TypeError):
        return None


@login_required
@permission_required("students.manage")
def import_students(request, classe_id):
    """Import Excel des élèves d'une classe.

    Les lignes sûres sont importées directement (fiches existantes complétées,
    nouveaux élèves créés). S'il y a des homonymes, des noms proches ou des
    informations contradictoires, une prévisualisation demande de trancher
    avant d'enregistrer quoi que ce soit.
    """
    from common import tmp_uploads
    from common.excel_import import ImportFileError, check_matricules, prepare, read_excel, summary
    from administration.services.student_import import DISPLAY_FIELDS, analyze, apply

    year = SchoolYear.objects.filter(is_active=True).first()
    classe = get_object_or_404(Classe, id=classe_id, school_year=year)

    def load(source):
        df = prepare(read_excel(source), "students", {
            "Prénom": "first_name", "Nom": "last_name", "Sexe": "sex", "DateNaissance": "date_of_birth",
            "Date de naissance": "date_of_birth", "Lieu": "place_of_birth", "Lieu de naissance": "place_of_birth",
            "Matricule": "matricule", "Père": "father_name", "Mère": "mother_name", "TelPère": "father_phone",
            "TelMère": "mother_phone", "WhatsApp": "whatsapp_phone",
            "Contact": "contact_name", "Personne de contact": "contact_name", "TelContact": "contact_phone",
            "Téléphone contact": "contact_phone", "Lien": "contact_relation", "Lien de parenté": "contact_relation",
            "Année de recrutement": "recruitment_year", "Recrutement": "recruitment_year",
        }, ("first_name", "last_name"))
        check_matricules(df, "matricule", "students")
        rows = []
        for idx, row in df.iterrows():
            data = {}
            for f in ("first_name", "last_name", "place_of_birth", "matricule", "father_name", "mother_name",
                      "father_phone", "mother_phone", "whatsapp_phone", "contact_name", "contact_phone", "contact_relation"):
                if f in df.columns:
                    data[f] = _student_import_normalize_text(row.get(f)) or None
            if "date_of_birth" in df.columns:
                data["date_of_birth"] = _student_import_parse_date(row.get("date_of_birth"))
            if "sex" in df.columns:
                data["sex"] = _student_import_normalize_sex(row.get("sex"))
            if "recruitment_year" in df.columns:
                raw = _student_import_normalize_text(row.get("recruitment_year"))
                digits = "".join(ch for ch in raw[:4] if ch.isdigit())
                data["recruitment_year"] = int(digits) if len(digits) == 4 else None
            rows.append((idx + 2, data))
        return rows

    def finish(report):
        r = report
        text = summary([
            f"{r['enrolled']} élève(s) inscrit(s) dans {classe.display_name}" + (f" dont {r['created']} nouvelle(s) fiche(s)" if r["created"] else ""),
            f"{r['completed']} fiche(s) existante(s) complétée(s)" if r["completed"] else "",
            f"{r['updated']} fiche(s) mise(s) à jour" if r["updated"] else "",
            f"{r['already']} déjà inscrit(s) dans cette classe, non dupliqué(s)" if r["already"] else "",
            f"{r['skipped']} ligne(s) non reprise(s) à votre demande" if r["skipped"] else "",
            f"{len(r['elsewhere'])} déjà inscrit(s) dans une autre classe cette année, non déplacé(s) : " + ", ".join(r["elsewhere"][:5]) + (" …" if len(r["elsewhere"]) > 5 else "") if r["elsewhere"] else "",
        ], r["errors"] + r["notes"])
        if r["enrolled"] == 0 and r["already"] and not r["elsewhere"] and not r["errors"] and not r["completed"] and not r["updated"]:
            messages.warning(request, f"Ce fichier a déjà été importé : ses {r['already']} élève(s) sont déjà inscrits dans {classe.display_name}. Rien n'a été ajouté.")
        else:
            (messages.warning if (r["errors"] or r["elsewhere"] or r["notes"]) else messages.success)(request, text)
        unknown_sex = Enrollment.objects.filter(school_year=year, classe=classe, student__sex__isnull=True).count()
        if unknown_sex:
            messages.info(request, f"{unknown_sex} élève(s) de la classe ont le sexe non renseigné : corrigez-le depuis leur fiche.")
        return redirect("classe_detail", classe_id=classe.id)

    if request.method == "POST":
        try:
            token = request.POST.get("token")
            if token and request.POST.get("confirm"):
                path = tmp_uploads.path(token)
                if not path:
                    raise ImportFileError("La prévisualisation a expiré : chargez de nouveau le fichier.")
                from io import BytesIO
                source = BytesIO(path.read_bytes())
                source.name = "import.xlsx"
                rows = analyze(load(source), year)
                decisions = {r.index: request.POST.get(f"choice_{r.index}", r.default_choice) for r in rows}
                replacements = {r.index: set(request.POST.getlist(f"replace_{r.index}")) for r in rows}
                report = apply(rows, year, classe, decisions, replacements)
                tmp_uploads.remove(token)
                return finish(report)
            uploaded = request.FILES.get("file")
            if not uploaded:
                messages.error(request, "Sélectionnez un fichier Excel.")
                return redirect("import_students", classe_id=classe.id)
            rows = analyze(load(uploaded), year)
            to_review = [r for r in rows if r.needs_review]
            if not to_review:
                return finish(apply(rows, year, classe))
            uploaded.seek(0)
            token = tmp_uploads.save(uploaded)
            return render(request, "administration/students/import_preview.html", {
                "classe": classe, "rows": rows, "to_review": to_review, "token": token,
                "counts": {s: sum(1 for r in rows if r.status == s) for s in ("déjà connu", "nouvel élève", "à vérifier", "erreur")},
            })
        except ImportFileError as exc:
            messages.error(request, f"Import refusé : {exc}")
        except Exception as exc:
            messages.error(request, f"Import impossible : {exc}")
    return render(request, "administration/students/import_students.html", {"classe": classe})


def _student_import_normalize_sex(value):
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    if normalized in {"m", "masculin", "male", "garcon", "g", "homme", "1"}:
        return "M"
    if normalized in {"f", "feminin", "female", "fille", "femme", "2"}:
        return "F"
    return None


@login_required
def certificat_frequentation_pdf(request, enrollment_id):
    from administration.certificat_pdf import render_certificat_frequentation_pdf
    enrollment = get_object_or_404(Enrollment.objects.select_related("student", "classe", "school_year__school"), id=enrollment_id)
    return render_certificat_frequentation_pdf(enrollment.student, enrollment)


@login_required
def student_list_pdf(request):
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    annee=(request.GET.get("annee") or "").strip()
    year=None
    if annee.isdigit(): year=SchoolYear.objects.filter(pk=annee).select_related("school").first()
    if year is None: year=SchoolYear.objects.filter(is_active=True).select_related("school").first()
    if not year: return HttpResponse("Aucune année scolaire active.",status=400)
    class_id=(request.GET.get("classe") or "").strip()
    classes=Classe.objects.filter(school_year=year).select_related("education_level").order_by("education_level__order","name")
    if class_id: classes=classes.filter(pk=class_id)
    classes=list(classes); buffer=BytesIO(); doc=SimpleDocTemplate(buffer,pagesize=A4,rightMargin=12*mm,leftMargin=12*mm,topMargin=12*mm,bottomMargin=14*mm,title="Liste des élèves par classe")
    styles=getSampleStyleSheet(); h=ParagraphStyle("OfficialH",parent=styles["Normal"],fontSize=8,leading=10,alignment=1); title=ParagraphStyle("OfficialTitle",parent=styles["Title"],fontSize=13,alignment=1,spaceAfter=5*mm); small=ParagraphStyle("OfficialSmall",parent=styles["Normal"],fontSize=7.5,leading=9)
    story=[]
    for idx,c in enumerate(classes):
        school=year.school; story.append(Paragraph(escape(school.ministry_name or "MINISTERE DE L’EDUCATION NATIONALE"),h)); story.append(Paragraph(escape(school.academy_name or ""),h))
        if c.education_level and c.education_level.school_type in {"fundamental_1","fundamental_2"}: story.append(Paragraph(escape(school.cap_name or ""),h))
        story.append(Paragraph(f"<b>{escape(school.name)}"+(f" ({escape(school.code)})" if school.code else "")+"</b>",h))
        contact=" — ".join([x for x in [school.address,school.city,f"Tél. : {school.phone}" if school.phone else "",school.email] if x])
        if contact: story.append(Paragraph(escape(contact),h))
        story.append(Spacer(1,3*mm)); story.append(Paragraph("LISTE DES ÉLÈVES",title)); story.append(Paragraph(f"Classe : <b>{escape(c.display_name)}</b> — Année scolaire : {escape(year.name)}",small)); story.append(Spacer(1,3*mm))
        ens=list(Enrollment.objects.filter(school_year=year,classe=c).select_related("student").order_by("student__last_name","student__first_name")); data=[["N°","Matricule","Prénoms et noms","Date de naissance","Sexe","Statut"]]
        for i,e in enumerate(ens,1): data.append([f"{i:02d}",e.student.matricule or "—",f"{e.student.first_name} {e.student.last_name}",e.student.date_of_birth.strftime("%d/%m/%Y") if e.student.date_of_birth else "—",e.student.get_sex_display() or "—",e.get_student_type_display()])
        table=Table(data,colWidths=[9*mm,24*mm,65*mm,28*mm,20*mm,28*mm],repeatRows=1); table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.3,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),7.5),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
        story += [table,Spacer(1,4*mm),Paragraph(f"Effectif : {len(ens)}",small)]
        if idx < len(classes)-1: story.append(PageBreak())
    def footer(canvas,doc):
        canvas.saveState(); canvas.setFont("Helvetica-Oblique",8); motto=getattr(year.school,"motto","")
        if motto: canvas.drawCentredString(A4[0]/2,7*mm,motto)
        canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer); response=HttpResponse(buffer.getvalue(),content_type="application/pdf"); response["Content-Disposition"]='inline; filename="liste-eleves-classes.pdf"'; return response


@login_required
def carte_identite_pdf(request, enrollment_id):
    from administration.carte_identite_pdf import render_carte_identite_pdf
    enrollment = get_object_or_404(Enrollment.objects.select_related("student", "classe", "school_year__school"), id=enrollment_id)
    return render_carte_identite_pdf(enrollment)


@login_required
def cartes_identite_classe_pdf(request, classe_id):
    from administration.carte_identite_pdf import render_cartes_identite_classe_pdf
    classe = get_object_or_404(Classe, id=classe_id)
    enrollments = list(
        Enrollment.objects.filter(classe=classe, school_year=classe.school_year)
        .select_related("student", "classe", "school_year__school")
        .order_by("student__last_name", "student__first_name")
    )
    return render_cartes_identite_classe_pdf(enrollments)


def _pdf_response(data, filename):
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def _safe(student):
    return f"{student.first_name}_{student.last_name}".replace(" ", "_")


@login_required
def fiche_scolaire_pdf(request, student_id):
    from administration.documents_fondamental import render_fiche_scolaire
    student = get_object_or_404(Student, id=student_id)
    enrollment = student.enrollments.select_related("school_year__school").order_by("-school_year__start_date").first()
    if not enrollment:
        messages.error(request, "Cet élève n'a aucune inscription.")
        return redirect("student_detail", student_id=student.id)
    return _pdf_response(render_fiche_scolaire(student, enrollment.school_year.school), f"fiche-scolaire-{_safe(student)}.pdf")


def _enrollment(enrollment_id):
    return get_object_or_404(
        Enrollment.objects.select_related("student", "classe__education_level", "school_year__school"), id=enrollment_id
    )


@login_required
def releve_notes_pdf(request, enrollment_id):
    from administration.documents_fondamental import render_releve_notes
    enrollment = _enrollment(enrollment_id)
    return _pdf_response(render_releve_notes(enrollment),
                         f"releve-notes-{enrollment.school_year.name}-{_safe(enrollment.student)}.pdf")


@login_required
def certificat_transfert_pdf(request, enrollment_id):
    from administration.documents_fondamental import render_certificat_transfert
    enrollment = _enrollment(enrollment_id)
    return _pdf_response(render_certificat_transfert(enrollment),
                         f"certificat-transfert-{_safe(enrollment.student)}.pdf")


@login_required
def fiche_inscription_vierge_pdf(request):
    from administration.fiche_inscription_pdf import render_fiche_inscription
    from administration.models import School
    school = School.objects.filter(is_active=True).first()
    year = SchoolYear.objects.filter(is_active=True).first()
    if not school:
        return redirect("startup")
    return _pdf_response(render_fiche_inscription(school, year=year), "fiche-inscription-vierge.pdf")


@login_required
def fiche_inscription_pdf(request, enrollment_id):
    from administration.fiche_inscription_pdf import render_fiche_inscription
    enrollment = _enrollment(enrollment_id)
    return _pdf_response(render_fiche_inscription(enrollment.school_year.school, enrollment=enrollment),
                         f"fiche-inscription-{_safe(enrollment.student)}.pdf")


@login_required
@permission_required("data.correct")
def matricule_generate(request):
    """Génère les matricules de toute l'école au format AA + sigle + n° + genre (ex. 22IQRA1M).

    Les élèves sans année de recrutement ou sans sexe sont d'abord proposés à
    la saisie ; la renumérotation ne se fait qu'une fois toutes les fiches complètes.
    """
    from administration.services import matricule as mat

    year = SchoolYear.objects.filter(is_active=True).select_related("school").first()
    if not year:
        return redirect("school_year_list")
    school = year.school
    if request.method == "POST" and request.POST.get("action") == "complete":
        saved = 0
        errors = []
        for key, value in request.POST.items():
            if not key.startswith("year_"):
                continue
            pk = key[5:]
            student = Student.objects.filter(pk=pk).first()
            if not student:
                continue
            raw_year = (value or "").strip()
            sex = (request.POST.get(f"sex_{pk}") or "").strip()
            changed = []
            if raw_year:
                if not raw_year.isdigit() or not 1980 <= int(raw_year) <= year.start_date.year + 1:
                    errors.append(f"{student} : année « {raw_year} » invalide")
                    continue
                student.recruitment_year = int(raw_year); changed.append("recruitment_year")
            if sex in ("M", "F"):
                student.sex = sex; changed.append("sex")
            if changed:
                Student.objects.filter(pk=student.pk).update(**{f: getattr(student, f) for f in changed})
                saved += 1
        if errors:
            messages.warning(request, "Non enregistré : " + " ; ".join(errors[:5]))
        if saved:
            messages.success(request, f"{saved} fiche(s) complétée(s).")
        return redirect("matricule_generate")
    if request.method == "POST" and request.POST.get("action") == "generate":
        try:
            total, changed = mat.regenerate_all(school, request.user)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("matricule_generate")
        messages.success(request, f"Matricules mis à jour : {total} élève(s), dont {changed} matricule(s) modifié(s).")
        return redirect("student_list")
    rows, incomplete = mat.plan(school)
    return render(request, "administration/students/matricules.html", {
        "rows": rows, "incomplete": incomplete, "sigle": mat.school_sigle(school),
        "example": mat.build(year.start_date.year, mat.school_sigle(school), 1, "M"),
        "changed": sum(1 for r in rows if r["old"] != r["new"]),
        "max_year": year.start_date.year,
    })
