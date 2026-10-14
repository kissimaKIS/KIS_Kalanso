"""Corrections réservées à la direction : annuler, supprimer, changer de classe (V5-10)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from administration.models import CorrectionLog
from administration.permissions import permission_required
from administration.services import corrections as svc
from common.pagination import paginate
from finance.models import Invoice, Payment
from pedagogie.models import Classe, Enrollment, Student

KINDS = {
    "annuler-paiement": "Annuler un paiement",
    "supprimer-facture": "Supprimer une facture",
    "changer-classe": "Changer de classe",
    "supprimer-inscription": "Supprimer une inscription",
    "supprimer-eleve": "Supprimer l'élève",
}


def _target(kind, pk):
    if kind == "annuler-paiement":
        payment = get_object_or_404(Payment.objects.select_related(
            "invoice__fee_type", "invoice__enrollment__student", "invoice__enrollment__school_year", "batch"), pk=pk)
        return payment, payment.invoice.enrollment.student
    if kind == "supprimer-facture":
        invoice = get_object_or_404(Invoice.objects.select_related(
            "fee_type", "enrollment__student", "enrollment__school_year"), pk=pk)
        return invoice, invoice.enrollment.student
    if kind in ("changer-classe", "supprimer-inscription"):
        enrollment = get_object_or_404(Enrollment.objects.select_related(
            "student", "school_year", "classe__education_level", "classe__pedagogical_track"), pk=pk)
        return enrollment, enrollment.student
    if kind == "supprimer-eleve":
        student = get_object_or_404(Student, pk=pk)
        return student, student
    raise Http404


def _consequences(kind, obj, new_classe=None):
    """Ce que la correction va réellement changer, affiché avant de confirmer."""
    lines, blockers = [], []
    if kind == "annuler-paiement":
        lines.append(f"Le montant {obj.amount:,.0f} est retiré de la facture « {obj.invoice.fee_type.name} » : son reste à payer augmente d'autant.".replace(",", " "))
        if obj.batch_id:
            others = obj.batch.payments.exclude(pk=obj.pk).count()
            lines.append(f"Ce paiement fait partie du reçu groupé {obj.batch.receipt_number}"
                         + (f" ({others} autre(s) ligne(s) conservée(s))." if others else " : le reçu entier est annulé."))
        lines.append("Le numéro de reçu ne sera jamais réattribué ; l'annulation figure au journal des corrections.")
        if obj.invoice.enrollment.school_year.is_closed and not obj.invoice.enrollment.school_year.is_archive:
            blockers.append("l'année scolaire est clôturée")
    elif kind == "supprimer-facture":
        if obj.payments.exists():
            blockers.append("cette facture porte des paiements : annulez-les d'abord")
        lines.append(f"La facture de {obj.total_amount:,.0f} disparaît de la situation de l'élève.".replace(",", " "))
        if obj.fee_type.category == "optional":
            lines.append("L'option correspondante est aussi retirée à l'élève.")
        if obj.enrollment.school_year.is_closed and not obj.enrollment.school_year.is_archive:
            blockers.append("l'année scolaire est clôturée")
    elif kind == "changer-classe":
        if new_classe:
            to_delete, to_create, blocking = svc.class_change_preview(obj, new_classe)
            if to_delete:
                lines.append("Frais retirés : " + ", ".join(i.fee_type.name for i in to_delete) + ".")
            if to_create:
                lines.append("Frais ajoutés : " + ", ".join(f"{f.name} ({f.amount:,.0f})".replace(",", " ") for f in to_create) + ".")
            if not to_delete and not to_create:
                lines.append("Les frais restent identiques (même niveau).")
            if blocking:
                blockers.append("frais déjà payés qui ne s'appliquent pas à la nouvelle classe : "
                                + ", ".join(i.fee_type.name for i in blocking) + " (annulez d'abord ces paiements)")
        lines.append("Les présences, la discipline et les options sont conservées.")
        if obj.school_year.is_closed:
            blockers.append("l'année scolaire est clôturée")
    elif kind == "supprimer-inscription":
        blockers += svc.enrollment_blockers(obj)
        lines.append(f"Seront supprimés : {obj.invoices.count()} facture(s), {obj.grades.count()} note(s), "
                     f"{obj.attendance_records.count()} présence(s), {obj.discipline_incidents.count()} incident(s).")
        lines.append("La fiche de l'élève est conservée.")
    elif kind == "supprimer-eleve":
        for e in obj.enrollments.select_related("school_year"):
            blockers += [f"{e.school_year.name} : {b}" for b in svc.enrollment_blockers(e)]
        lines.append(f"La fiche, ses {obj.enrollments.count()} inscription(s) et tout ce qui s'y rattache "
                     "(factures, notes, présences, documents) seront supprimés.")
    return lines, blockers


@login_required
@permission_required("data.correct")
def correction(request, kind, pk):
    if kind not in KINDS:
        raise Http404
    obj, student = _target(kind, pk)
    classes = None
    new_classe = None
    if kind == "changer-classe":
        classes = Classe.objects.filter(school_year=obj.school_year).exclude(pk=obj.classe_id).select_related(
            "education_level", "pedagogical_track").order_by("education_level__order", "group", "name")
        class_id = request.POST.get("classe") or request.GET.get("classe")
        if class_id:
            new_classe = classes.filter(pk=class_id).first()
    error = None
    if request.method == "POST":
        reason = request.POST.get("reason", "")
        try:
            if kind == "annuler-paiement":
                svc.cancel_payment(obj, reason, request.user)
                messages.success(request, "Paiement annulé. L'opération est inscrite au journal des corrections.")
            elif kind == "supprimer-facture":
                svc.delete_invoice(obj, reason, request.user)
                messages.success(request, "Facture supprimée.")
            elif kind == "changer-classe":
                if not new_classe:
                    raise ValidationError("Choisissez la nouvelle classe.")
                svc.change_enrollment_class(obj, new_classe, reason, request.user)
                messages.success(request, f"{student} est désormais en {new_classe.display_name}.")
            elif kind == "supprimer-inscription":
                svc.delete_enrollment(obj, reason, request.user)
                messages.success(request, "Inscription supprimée.")
            elif kind == "supprimer-eleve":
                svc.delete_student(obj, reason, request.user)
                messages.success(request, f"L'élève {student} a été supprimé.")
                return redirect("student_list")
            return redirect("student_detail", student_id=student.id)
        except ValidationError as exc:
            error = " ".join(exc.messages)
    lines, blockers = _consequences(kind, obj, new_classe)
    return render(request, "administration/corrections/confirm.html", {
        "kind": kind, "title": KINDS[kind], "obj": obj, "student": student,
        "classes": classes, "new_classe": new_classe, "lines": lines, "blockers": blockers,
        "error": error, "reason": request.POST.get("reason", ""),
    })


@login_required
@permission_required("data.correct")
def correction_log(request):
    logs = CorrectionLog.objects.select_related("user")
    action = request.GET.get("action", "")
    if action:
        logs = logs.filter(action=action)
    page_obj = paginate(request, logs, 30)
    return render(request, "administration/corrections/log.html", {
        "page_obj": page_obj, "actions": CorrectionLog.Action.choices, "action": action,
    })


# --------------------------------------------------------------------------
# Doublons d'élèves : liste des fiches probablement identiques et fusion
# --------------------------------------------------------------------------
def _student_card(student):
    from administration.services.student_matching import COMPLETABLE_FIELDS, FIELD_LABELS
    enrollments = list(student.enrollments.select_related("classe__education_level", "classe__pedagogical_track", "school_year")
                       .order_by("-school_year__start_date"))
    fields = []
    for f in ["first_name", "last_name"] + COMPLETABLE_FIELDS:
        value = getattr(student, f)
        if f == "sex":
            value = student.get_sex_display() if value else ""
        elif f == "date_of_birth" and value:
            value = value.strftime("%d/%m/%Y")
        fields.append((FIELD_LABELS[f], value or "—"))
    from finance.models import Invoice, Payment
    return {
        "student": student, "fields": fields,
        "enrollments": [f"{e.school_year.name} · {e.classe.display_name}" for e in enrollments],
        "invoices": Invoice.objects.filter(enrollment__student=student).count(),
        "payments": Payment.objects.filter(invoice__enrollment__student=student).count(),
    }


@login_required
@permission_required("data.correct")
def student_duplicates(request):
    from administration.services.student_matching import find_duplicates
    pairs = find_duplicates()
    show_all = request.GET.get("tous") == "1"
    shown = pairs if show_all else [p for p in pairs if p["sure"]]
    return render(request, "administration/corrections/duplicates.html", {
        "pairs": shown, "hidden": len(pairs) - len(shown), "show_all": show_all,
    })


@login_required
@permission_required("data.correct")
def student_merge_pick(request, student_id):
    """Choisir la fiche à fusionner avec celle-ci (recherche par nom, matricule ou téléphone)."""
    from administration.services.student_matching import close_name, common_clues
    student = get_object_or_404(Student, pk=student_id)
    q = (request.GET.get("q") or "").strip()
    others = Student.objects.exclude(pk=student.pk)
    if q:
        from django.db.models import Q
        results = list(others.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(matricule__icontains=q)
                                     | Q(father_phone__icontains=q) | Q(mother_phone__icontains=q))[:30])
    else:
        results = [s for s in others.filter(last_name__istartswith=student.last_name[:3]) if close_name(student, s)][:30]
    return render(request, "administration/corrections/merge_pick.html", {
        "student": student, "q": q,
        "results": [(s, common_clues(student, s)) for s in results],
    })


@login_required
@permission_required("data.correct")
def student_merge(request, keep_id, drop_id):
    from administration.services.student_merge import merge_preview, merge_students
    keep = get_object_or_404(Student, pk=keep_id)
    drop = get_object_or_404(Student, pk=drop_id)
    error = None
    if request.method == "POST":
        try:
            merge_students(keep, drop, request.POST.get("reason", ""), request.user)
        except ValidationError as exc:
            error = " ".join(exc.messages)
        else:
            messages.success(request, f"Fiches fusionnées : tout est désormais sur la fiche de {keep}.")
            return redirect("student_detail", student_id=keep.pk)
    lines, blockers = merge_preview(keep, drop)
    return render(request, "administration/corrections/merge.html", {
        "keep": _student_card(keep), "drop": _student_card(drop), "lines": lines, "blockers": blockers,
        "error": error, "reason": request.POST.get("reason", ""),
    })
