import unicodedata
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Q
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from common.pagination import paginate
from administration.models import TeacherPayment, OtherPersonnelPayment, SchoolYear
from django.urls import reverse
from administration.models import TeacherPayment, OtherPersonnelPayment, SchoolYear

from administration.forms import TeacherForm, OtherPersonnelForm
from administration.models import School, Teacher, OtherPersonnel
from common.years import viewed_year


def _current_school():
    return School.objects.filter(is_active=True).order_by("id").first()


def _allowed_teacher_profiles(school):
    allowed = set(school.enabled_school_types()) if school else set()
    profiles = []
    if School.SchoolType.FUNDAMENTAL_1 in allowed:
        profiles.append(Teacher.PedagogicalProfile.GENERALISTE)
    if School.SchoolType.FUNDAMENTAL_2 in allowed or School.SchoolType.HIGH_SCHOOL in allowed:
        profiles.append(Teacher.PedagogicalProfile.SPECIALISTE)
    if School.SchoolType.VOCATIONAL in allowed:
        profiles.append(Teacher.PedagogicalProfile.FORMATEUR_METIER)
    return [(value, Teacher.PedagogicalProfile(value).label) for value in profiles]


@login_required
def teacher_list(request):
    school = _current_school()
    if not school:
        return redirect("startup")
    teachers = Teacher.objects.select_related("user").all()
    contract_type = request.GET.get("statut", "")
    profile = request.GET.get("profil", "")
    search = request.GET.get("q", "").strip()
    allowed_profiles = _allowed_teacher_profiles(school)
    allowed_values = {value for value, _ in allowed_profiles}
    if profile not in allowed_values:
        profile = ""
    if contract_type:
        teachers = teachers.filter(contract_type=contract_type)
    if profile:
        teachers = teachers.filter(pedagogical_profile=profile)
    if search:
        teachers = teachers.filter(
            Q(employee_number__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
        )
    page_obj = paginate(request, teachers)
    return render(request, "administration/teachers/list.html", {
        "teachers": page_obj,
        "page_obj": page_obj,
        "contract_types": Teacher.ContractType.choices,
        "profiles": allowed_profiles,
        "selected_status": contract_type,
        "selected_profile": profile,
        "search": search,
    })


def _is_modal_request(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _modal_reload_response():
    return HttpResponse("", headers={"HX-Trigger": "kisModalReload"})


@login_required
def teacher_create(request):
    school = _current_school()
    if not school:
        return redirect("startup")
    form = TeacherForm(request.POST or None, request.FILES or None, school=school)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Enseignant enregistré.")
        if _is_modal_request(request):
            return _modal_reload_response()
        return redirect("teacher_list")
    if _is_modal_request(request):
        return render(request, "administration/teachers/_modal_form.html", {"form": form, "action_url": request.path})
    return render(request, "administration/teachers/form.html", {
        "form": form, "title": "Nouvel enseignant", "school": school,
    })


@login_required
def teacher_edit(request, pk):
    school = _current_school()
    teacher = get_object_or_404(Teacher.objects.select_related("user"), pk=pk)
    form = TeacherForm(request.POST or None, request.FILES or None, instance=teacher, school=school)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Enseignant mis à jour.")
        if _is_modal_request(request):
            return _modal_reload_response()
        return redirect("teacher_list")
    if _is_modal_request(request):
        return render(request, "administration/teachers/_modal_form.html", {"form": form, "action_url": request.path})
    return render(request, "administration/teachers/form.html", {
        "form": form, "title": "Modifier l'enseignant", "school": school, "teacher": teacher,
    })


@login_required
def teacher_pdf(request):
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    school=_current_school(); teachers=list(Teacher.objects.select_related("user").order_by("last_name","first_name"))
    buffer=BytesIO(); doc=SimpleDocTemplate(buffer,pagesize=A4,rightMargin=12*mm,leftMargin=12*mm,topMargin=12*mm,bottomMargin=12*mm,title="Liste des enseignants")
    styles=getSampleStyleSheet(); small=ParagraphStyle("Ts",parent=styles["Normal"],fontSize=8,leading=10); title=ParagraphStyle("Tt",parent=styles["Title"],fontSize=14,alignment=1,spaceAfter=5*mm)
    story=[Paragraph(f"<b>{escape(school.name)}</b>",small),Paragraph("LISTE DES ENSEIGNANTS",title)]
    data=[["N°","Matricule","Enseignant","Statut","Profil","Spécialité","Téléphone","Rémunération"]]
    for i,t in enumerate(teachers,1):
        remuneration=(f"{t.monthly_salary:,.0f} FCFA/mois" if t.contract_type==Teacher.ContractType.PERMANENT and t.monthly_salary is not None else f"{t.hourly_rate:,.0f} FCFA/h" if t.hourly_rate is not None else "—")
        data.append([str(i),t.employee_number,t.full_name,t.get_contract_type_display(),t.get_pedagogical_profile_display() or "—",t.specialty or "—",t.phone or "—",remuneration])
    table=Table(data,colWidths=[8*mm,22*mm,35*mm,22*mm,23*mm,28*mm,24*mm,28*mm],repeatRows=1); table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.3,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),7),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story += [table,Spacer(1,5*mm),Paragraph("Document interne de gestion de l'établissement.",small)]; doc.build(story)
    response=HttpResponse(buffer.getvalue(),content_type="application/pdf"); response["Content-Disposition"]='inline; filename="liste-enseignants.pdf"'; return response

@login_required
def teacher_payment_list(request):
    school=_current_school(); year=viewed_year()
    payments=TeacherPayment.objects.filter(school_year=year).select_related("teacher__user") if year else TeacherPayment.objects.none()
    q=request.GET.get("q","").strip()
    if q: payments=payments.filter(Q(teacher__employee_number__icontains=q)|Q(teacher__first_name__icontains=q)|Q(teacher__last_name__icontains=q))
    return render(request,"administration/teachers/payments.html",{"payments":payments,"teachers":Teacher.objects.select_related("user").filter(is_active=True),"school_year":year,"search":q})

@login_required
def teacher_payment_create(request):
    from django import forms
    year=viewed_year()
    if not year: return redirect("teacher_list")
    class PaymentForm(forms.Form):
        teacher=forms.ModelChoiceField(queryset=Teacher.objects.select_related("user").filter(is_active=True),label="Enseignant")
        period=forms.CharField(max_length=30,label="Période",help_text="Ex. Septembre 2026")
        amount=forms.DecimalField(max_digits=12,decimal_places=2,label="Montant payé")
        paid_at=forms.DateField(label="Date de paiement",widget=forms.DateInput(format="%Y-%m-%d", attrs={"type":"date"}),initial=timezone.localdate)
        note=forms.CharField(required=False,label="Observation")
    form=PaymentForm(request.POST or None)
    if request.method=="POST" and form.is_valid():
        obj=TeacherPayment(teacher=form.cleaned_data["teacher"],school_year=year,period=form.cleaned_data["period"].strip(),amount=form.cleaned_data["amount"],paid_at=form.cleaned_data["paid_at"],note=form.cleaned_data["note"].strip()); obj.save(); messages.success(request,"Salaire enseignant enregistré."); return redirect("teacher_payment_list")
    return render(request,"administration/teachers/payment_form.html",{"form":form,"school_year":year})

@login_required
def teacher_payment_pdf(request):
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
    year=viewed_year(); payments=list(TeacherPayment.objects.filter(school_year=year).select_related("teacher__user") if year else [])
    buffer=BytesIO(); doc=SimpleDocTemplate(buffer,pagesize=landscape(A4),rightMargin=10*mm,leftMargin=10*mm,topMargin=10*mm,bottomMargin=10*mm,title="État des salaires des enseignants")
    styles=getSampleStyleSheet(); small=ParagraphStyle("Ps",parent=styles["Normal"],fontSize=8); title=ParagraphStyle("Pt",parent=styles["Title"],alignment=1,fontSize=14,spaceAfter=5*mm)
    story=[Paragraph(f"<b>{escape(year.school.name)}</b>",small),Paragraph("ÉTAT DES SALAIRES DES ENSEIGNANTS",title)]
    data=[["Enseignant","Matricule","Statut","Période","Montant payé","Date","Observation"]]; total=0
    for p in payments: data.append([p.teacher.full_name,p.teacher.employee_number,p.teacher.get_contract_type_display(),p.period,f"{p.amount:,.0f} FCFA",p.paid_at.strftime("%d/%m/%Y"),p.note or "—"]); total+=p.amount
    data.append(["TOTAL","","","",f"{total:,.0f} FCFA","",""])
    table=Table(data,colWidths=[45*mm,25*mm,28*mm,32*mm,35*mm,25*mm,65*mm],repeatRows=1); table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.3,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8)])); story.append(table); doc.build(story)
    response=HttpResponse(buffer.getvalue(),content_type="application/pdf"); response["Content-Disposition"]='inline; filename="salaires-enseignants.pdf"'; return response


@login_required
def other_personnel_payment_list(request):
    school = _current_school()
    year = viewed_year() if school else None
    payments = OtherPersonnelPayment.objects.filter(school_year=year, personnel__school=school).select_related("personnel") if year else OtherPersonnelPayment.objects.none()
    q = request.GET.get("q", "").strip()
    if q:
        payments = payments.filter(
            Q(personnel__employee_number__icontains=q)
            | Q(personnel__first_name__icontains=q)
            | Q(personnel__last_name__icontains=q)
            | Q(personnel__function__icontains=q)
        )
    return render(request, "administration/other_personnel/payments.html", {
        "payments": payments,
        "personnel": OtherPersonnel.objects.filter(school=school, is_active=True) if school else OtherPersonnel.objects.none(),
        "school_year": year,
        "search": q,
    })


@login_required
def other_personnel_payment_create(request):
    from django import forms
    school = _current_school()
    year = viewed_year() if school else None
    if not school or not year:
        return redirect("other_personnel_list")

    class PaymentForm(forms.Form):
        personnel = forms.ModelChoiceField(
            queryset=OtherPersonnel.objects.filter(school=school, is_active=True),
            label="Personnel",
        )
        period = forms.CharField(max_length=30, label="Période", help_text="Ex. Septembre 2026")
        amount = forms.DecimalField(max_digits=12, decimal_places=2, label="Montant payé", min_value=0.01)
        paid_at = forms.DateField(label="Date de paiement", widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}), initial=timezone.localdate)
        note = forms.CharField(required=False, label="Observation")

    form = PaymentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = OtherPersonnelPayment(
            personnel=form.cleaned_data["personnel"], school_year=year,
            period=form.cleaned_data["period"].strip(), amount=form.cleaned_data["amount"],
            paid_at=form.cleaned_data["paid_at"], note=form.cleaned_data["note"].strip(),
        )
        try:
            obj.save()
        except Exception as exc:
            form.add_error("period", str(exc))
        else:
            messages.success(request, "Salaire du personnel enregistré.")
            return redirect("other_personnel_payment_list")
    return render(request, "administration/other_personnel/payment_form.html", {"form": form, "school_year": year})


@login_required
def other_personnel_payment_pdf(request):
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
    school = _current_school()
    year = viewed_year() if school else None
    payments = list(OtherPersonnelPayment.objects.filter(school_year=year, personnel__school=school).select_related("personnel") if year else [])
    q = request.GET.get("q", "").strip()
    if q:
        payments = [p for p in payments if q.lower() in " ".join([p.personnel.employee_number, p.personnel.first_name, p.personnel.last_name, p.personnel.function]).lower()]
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=10*mm, leftMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm, title="État des salaires du personnel")
    styles = getSampleStyleSheet()
    small = ParagraphStyle("OpsSmall", parent=styles["Normal"], fontSize=8)
    title = ParagraphStyle("OpsTitle", parent=styles["Title"], alignment=1, fontSize=14, spaceAfter=5*mm)
    story = [Paragraph(f"<b>{escape(school.name)}</b>", small), Paragraph("ÉTAT DES SALAIRES DU PERSONNEL NON ENSEIGNANT", title)]
    data = [["Personnel", "Matricule", "Fonction", "Statut", "Période", "Montant payé", "Date", "Observation"]]
    total = 0
    for p in payments:
        data.append([f"{p.personnel.first_name} {p.personnel.last_name}".strip(), p.personnel.employee_number, p.personnel.function, p.personnel.get_contract_type_display(), p.period, f"{p.amount:,.0f} FCFA", p.paid_at.strftime("%d/%m/%Y"), p.note or "—"])
        total += p.amount
    data.append(["TOTAL", "", "", "", "", f"{total:,.0f} FCFA", "", ""])
    table = Table(data, colWidths=[42*mm, 24*mm, 38*mm, 28*mm, 30*mm, 35*mm, 25*mm, 55*mm], repeatRows=1)
    table.setStyle(TableStyle([("GRID", (0,0), (-1,-1), .3, colors.grey), ("BACKGROUND", (0,0), (-1,0), colors.lightgrey), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTNAME", (0,-1), (-1,-1), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 8)]))
    story.append(table)
    doc.build(story)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="salaires-autre-personnel.pdf"'
    return response

@login_required
def other_personnel_pdf(request):
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    school = _current_school()
    if not school:
        return redirect("startup")
    personnel = list(OtherPersonnel.objects.filter(school=school).order_by("last_name", "first_name"))
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), rightMargin=10*mm, leftMargin=10*mm,
        topMargin=10*mm, bottomMargin=10*mm, title="Liste du personnel non enseignant"
    )
    styles = getSampleStyleSheet()
    small = ParagraphStyle("OpsSmall", parent=styles["Normal"], fontSize=8, leading=10)
    title = ParagraphStyle("OpsTitle", parent=styles["Title"], fontSize=14, alignment=1, spaceAfter=5*mm)
    story = [
        Paragraph(f"<b>{escape(school.name)}</b>", small),
        Paragraph("LISTE DU PERSONNEL NON ENSEIGNANT", title),
    ]
    data = [["N°", "Matricule", "Nom et prénom(s)", "Fonction", "Statut", "Téléphone", "État"]]
    for i, person in enumerate(personnel, 1):
        data.append([
            str(i), person.employee_number, f"{person.last_name} {person.first_name}",
            person.function, person.get_contract_type_display(), person.phone or "—",
            "Actif" if person.is_active else "Inactif",
        ])
    if not personnel:
        data.append(["", "", "Aucun membre du personnel enregistré.", "", "", "", ""])
    table = Table(data, colWidths=[10*mm, 28*mm, 55*mm, 45*mm, 30*mm, 35*mm, 22*mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), .3, colors.grey),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story += [table, Spacer(1, 4*mm), Paragraph("Document interne de gestion de l'établissement.", small)]
    doc.build(story)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="liste-personnel-non-enseignant.pdf"'
    return response


@login_required
def other_personnel_list(request):
    school = _current_school()
    if not school:
        return redirect("startup")
    personnel = OtherPersonnel.objects.filter(school=school)
    search = request.GET.get("q", "").strip()
    status = request.GET.get("statut", "")
    if search:
        personnel = personnel.filter(
            Q(employee_number__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(function__icontains=search)
        )
    if status in {value for value, _ in OtherPersonnel.ContractType.choices}:
        personnel = personnel.filter(contract_type=status)
    return render(request, "administration/other_personnel/list.html", {
        "personnel": personnel,
        "search": search,
        "selected_status": status,
        "contract_types": OtherPersonnel.ContractType.choices,
    })


@login_required
def other_personnel_create(request):
    school = _current_school()
    if not school:
        return redirect("startup")
    form = OtherPersonnelForm(request.POST or None, request.FILES or None, school=school)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Membre du personnel enregistré.")
        if request.headers.get("HX-Request") or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return HttpResponse("", headers={"HX-Trigger": "kisModalReload"})
        return redirect("other_personnel_list")
    if request.headers.get("HX-Request") or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return render(request, "administration/other_personnel/_modal_form.html", {"form": form, "action_url": request.path})
    return render(request, "administration/other_personnel/form.html", {"form": form, "title": "Nouveau membre du personnel"})


@login_required
def other_personnel_edit(request, pk):
    school = _current_school()
    if not school:
        return redirect("startup")
    obj = get_object_or_404(OtherPersonnel, pk=pk, school=school)
    form = OtherPersonnelForm(request.POST or None, request.FILES or None, instance=obj, school=school)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Membre du personnel mis à jour.")
        if request.headers.get("HX-Request") or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return HttpResponse("", headers={"HX-Trigger": "kisModalReload"})
        return redirect("other_personnel_list")
    if request.headers.get("HX-Request") or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return render(request, "administration/other_personnel/_modal_form.html", {"form": form, "action_url": request.path})
    return render(request, "administration/other_personnel/form.html", {"form": form, "title": "Modifier le personnel"})


def _normalize_text(value):
    """Convertit une cellule Excel (NaN, nombre, texte…) en chaîne propre.

    Un Matricule ou un Téléphone saisi comme nombre dans Excel arrive ici sous
    forme de float (ex. 70999999.0) : sans ce traitement, il serait stocké
    avec un ".0" parasite. Les nombres entiers sont donc reconvertis en texte
    sans décimale.
    """
    import pandas as pd
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _normalize_ascii(text):
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()


def _parse_excel_date(value):
    import pandas as pd
    if value is None or pd.isna(value):
        return None
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def _parse_excel_number(value):
    import pandas as pd
    if value is None or pd.isna(value):
        return None
    return value


@login_required
def import_teachers(request):
    """Importe/actualise des enseignants depuis un fichier Excel.

    Modèle repris de l'import des élèves : le Matricule identifie la ligne
    (création si inconnu, mise à jour sinon), pour permettre de faire migrer
    un tableau Excel existant sans tout ressaisir. Aucun compte utilisateur
    n'est créé : les comptes de connexion se créent explicitement dans
    Administration → Utilisateurs.
    """
    school = _current_school()
    if not school:
        return redirect("startup")
    if request.method == "POST":
        uploaded = request.FILES.get("file")
        if not uploaded:
            messages.error(request, "Sélectionnez un fichier Excel.")
            return redirect("import_teachers")
        try:
            from common.excel_import import ImportFileError, check_matricules, prepare, read_excel, summary
            df = prepare(read_excel(uploaded), "teachers", {
                "Matricule": "employee_number", "Prénom": "first_name", "Nom": "last_name",
                "Téléphone": "phone", "Email": "email", "Adresse": "address",
                "Statut": "contract_type", "Profil": "pedagogical_profile",
                "Spécialité": "specialty", "Diplôme": "qualification",
                "SalaireMensuel": "monthly_salary", "TauxHoraire": "hourly_rate",
                "DateRecrutement": "hire_date",
            }, ("employee_number", "first_name", "last_name"))
            check_matricules(df, "employee_number", "teachers")

            allowed_profiles = {value for value, _ in _allowed_teacher_profiles(school)}

            def normalize_contract(value):
                text = _normalize_ascii(_normalize_text(value))
                if text in {"vacataire", "vac"}:
                    return Teacher.ContractType.VACATAIRE
                return Teacher.ContractType.PERMANENT

            def normalize_profile(value):
                text = _normalize_ascii(_normalize_text(value)).replace("_", " ")
                mapping = {
                    "generaliste": Teacher.PedagogicalProfile.GENERALISTE,
                    "specialiste": Teacher.PedagogicalProfile.SPECIALISTE,
                    "formateur metier": Teacher.PedagogicalProfile.FORMATEUR_METIER,
                }
                profile = mapping.get(text, "")
                return profile if profile in allowed_profiles else ""

            created, updated, errors = 0, 0, []
            with transaction.atomic():
                for idx, row in df.iterrows():
                    employee_number = _normalize_text(row.get("employee_number"))
                    first_name = _normalize_text(row.get("first_name"))
                    last_name = _normalize_text(row.get("last_name"))
                    if not employee_number or not first_name or not last_name:
                        errors.append(f"Ligne {idx + 2} : Matricule, Prénom et Nom sont obligatoires.")
                        continue

                    teacher = Teacher.objects.filter(employee_number=employee_number).first()
                    is_new = teacher is None
                    if is_new:
                        # Aucun compte utilisateur n'est créé : la fiche
                        # enseignant porte elle-même l'identité.
                        teacher = Teacher(employee_number=employee_number)
                    teacher.first_name = first_name
                    teacher.last_name = last_name
                    email = _normalize_text(row.get("email"))
                    if email:
                        teacher.email = email

                    contract_type = normalize_contract(row.get("contract_type")) if "contract_type" in df.columns else (teacher.contract_type or Teacher.ContractType.PERMANENT)
                    profile = normalize_profile(row.get("pedagogical_profile")) if "pedagogical_profile" in df.columns else ""
                    monthly_salary = _parse_excel_number(row.get("monthly_salary")) if "monthly_salary" in df.columns else teacher.monthly_salary
                    hourly_rate = _parse_excel_number(row.get("hourly_rate")) if "hourly_rate" in df.columns else teacher.hourly_rate
                    # Un vacataire n'a pas de salaire mensuel fixe ; un permanent n'a pas de taux horaire.
                    if contract_type == Teacher.ContractType.VACATAIRE:
                        monthly_salary = None
                    else:
                        hourly_rate = None

                    teacher.phone = _normalize_text(row.get("phone")) or teacher.phone
                    teacher.address = _normalize_text(row.get("address")) or teacher.address
                    teacher.specialty = _normalize_text(row.get("specialty")) or teacher.specialty
                    teacher.qualification = _normalize_text(row.get("qualification")) or teacher.qualification
                    teacher.contract_type = contract_type
                    if profile:
                        teacher.pedagogical_profile = profile
                    teacher.monthly_salary = monthly_salary
                    teacher.hourly_rate = hourly_rate
                    if "hire_date" in df.columns:
                        hire_date = _parse_excel_date(row.get("hire_date"))
                        if hire_date:
                            teacher.hire_date = hire_date

                    try:
                        teacher.full_clean(exclude=["user"])
                    except ValidationError as exc:
                        errors.append(f"Ligne {idx + 2} ({employee_number}) : {'; '.join(exc.messages)}")
                        continue

                    teacher.save()
                    created += int(is_new)
                    updated += int(not is_new)

            text = summary([
                f"{created} enseignant(s) créé(s)",
                f"{updated} déjà existant(s) (même matricule) mis à jour, sans doublon" if updated else "",
            ], errors)
            (messages.warning if errors else messages.success)(request, text)
            return redirect("teacher_list")
        except ImportFileError as exc:
            messages.error(request, f"Import refusé : {exc}")
        except Exception as exc:
            messages.error(request, f"Import impossible : {exc}")
    return render(request, "administration/teachers/import_teachers.html", {"school": school})


@login_required
def import_other_personnel(request):
    """Importe/actualise le personnel non enseignant depuis un fichier Excel."""
    school = _current_school()
    if not school:
        return redirect("startup")
    if request.method == "POST":
        uploaded = request.FILES.get("file")
        if not uploaded:
            messages.error(request, "Sélectionnez un fichier Excel.")
            return redirect("import_other_personnel")
        try:
            from common.excel_import import ImportFileError, check_matricules, prepare, read_excel, summary
            df = prepare(read_excel(uploaded), "personnel", {
                "Matricule": "employee_number", "Prénom": "first_name", "Nom": "last_name",
                "Fonction": "function", "Statut": "contract_type", "Téléphone": "phone",
                "Email": "email", "Adresse": "address", "DateNaissance": "date_of_birth",
                "DateRecrutement": "hire_date", "SalaireMensuel": "monthly_salary",
                "TauxHoraire": "hourly_rate",
            }, ("employee_number", "first_name", "last_name", "function"))
            check_matricules(df, "employee_number", "personnel")

            def normalize_contract(value):
                text = _normalize_ascii(_normalize_text(value))
                mapping = {
                    "permanent": OtherPersonnel.ContractType.PERMANENT,
                    "contractuel": OtherPersonnel.ContractType.CONTRACTUEL,
                    "vacataire": OtherPersonnel.ContractType.VACATAIRE,
                    "temporaire": OtherPersonnel.ContractType.TEMPORAIRE,
                }
                return mapping.get(text, OtherPersonnel.ContractType.PERMANENT)

            created, updated, errors = 0, 0, []
            with transaction.atomic():
                for idx, row in df.iterrows():
                    employee_number = _normalize_text(row.get("employee_number"))
                    first_name = _normalize_text(row.get("first_name"))
                    last_name = _normalize_text(row.get("last_name"))
                    function = _normalize_text(row.get("function"))
                    if not employee_number or not first_name or not last_name or not function:
                        errors.append(f"Ligne {idx + 2} : Matricule, Prénom, Nom et Fonction sont obligatoires.")
                        continue

                    person = OtherPersonnel.objects.filter(school=school, employee_number=employee_number).first()
                    is_new = person is None
                    if is_new:
                        person = OtherPersonnel(school=school, employee_number=employee_number)

                    person.first_name = first_name
                    person.last_name = last_name
                    person.function = function
                    if "contract_type" in df.columns:
                        person.contract_type = normalize_contract(row.get("contract_type"))
                    person.phone = _normalize_text(row.get("phone")) or person.phone
                    person.email = _normalize_text(row.get("email")) or person.email
                    person.address = _normalize_text(row.get("address")) or person.address
                    if "date_of_birth" in df.columns:
                        date_of_birth = _parse_excel_date(row.get("date_of_birth"))
                        if date_of_birth:
                            person.date_of_birth = date_of_birth
                    if "hire_date" in df.columns:
                        hire_date = _parse_excel_date(row.get("hire_date"))
                        if hire_date:
                            person.hire_date = hire_date
                    if "monthly_salary" in df.columns:
                        person.monthly_salary = _parse_excel_number(row.get("monthly_salary"))
                    if "hourly_rate" in df.columns:
                        person.hourly_rate = _parse_excel_number(row.get("hourly_rate"))
                    if person.contract_type == OtherPersonnel.ContractType.VACATAIRE:
                        person.monthly_salary = None

                    try:
                        person.full_clean()
                    except ValidationError as exc:
                        errors.append(f"Ligne {idx + 2} ({employee_number}) : {'; '.join(exc.messages)}")
                        continue

                    person.save()
                    created += int(is_new)
                    updated += int(not is_new)

            text = summary([
                f"{created} membre(s) du personnel créé(s)",
                f"{updated} déjà existant(s) (même matricule) mis à jour, sans doublon" if updated else "",
            ], errors)
            (messages.warning if errors else messages.success)(request, text)
            return redirect("other_personnel_list")
        except ImportFileError as exc:
            messages.error(request, f"Import refusé : {exc}")
        except Exception as exc:
            messages.error(request, f"Import impossible : {exc}")
    return render(request, "administration/other_personnel/import_personnel.html", {"school": school})
