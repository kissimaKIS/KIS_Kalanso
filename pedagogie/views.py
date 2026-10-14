from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from administration.models import SchoolYear
from .selectors.classes import ordered_classes
from .models import Bulletin, BulletinItem, BulletinItemResult, BulletinLock, Classe, Enrollment, Evaluation, EvaluationSubject, Grade, Subject, Term
from .utils import classement, moyenne_generale
from .forms import EvaluationForm
from .permissions import TeacherScope
from administration.permissions.middleware import deny
from common.years import viewed_year


def _is_modal_request(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _modal_reload_response():
    return HttpResponse("", headers={"HX-Trigger": "kisModalReload"})


def _active_year():
    return viewed_year()


@login_required
def evaluation_create(request):
    year = _active_year()
    form = EvaluationForm(request.POST or None, school_year=year)
    if request.method == "POST" and year and form.is_valid():
        form.save()
        if _is_modal_request(request):
            return _modal_reload_response()
        return redirect("term_list")
    if _is_modal_request(request):
        return render(request, "pedagogie/evaluations/_modal_form.html", {"form": form, "school_year": year})
    return render(request, "pedagogie/evaluations/form.html", {"form": form, "school_year": year})


@login_required
def evaluation_subjects(request):
    year = _active_year()
    classe_id = request.GET.get("classe_id") or request.GET.get("classe")
    classe = Classe.objects.filter(pk=classe_id, school_year=year).select_related("education_level", "pedagogical_track").first() if classe_id and year else None
    links = classe.applicable_subject_links().filter(subject__is_active=True).order_by("order", "subject__name") if classe else []
    return render(request, "pedagogie/evaluations/_subjects.html", {"links": links, "classe": classe})


@login_required
def term_list(request):
    year = _active_year()
    scope = TeacherScope(request.user)
    allowed_class_ids = scope.class_ids()
    terms = Term.objects.filter(school_year=year).order_by("order", "id") if year else Term.objects.none()
    class_qs = Classe.objects.filter(school_year=year) if year else Classe.objects.none()
    if allowed_class_ids is not None:
        class_qs = class_qs.filter(pk__in=allowed_class_ids)
    classes = ordered_classes(class_qs) if year else Classe.objects.none()
    evaluations = Evaluation.objects.filter(classe__in=class_qs).select_related(
        "classe__education_level", "classe__pedagogical_track", "term"
    ).prefetch_related("subject_links__subject") if year else Evaluation.objects.none()
    grouped = []
    evaluation_map = {}
    for evaluation in evaluations.order_by("classe__education_level__order", "classe__group", "date", "id"):
        evaluation_map.setdefault(evaluation.classe_id, []).append(evaluation)
    configured = set(
        BulletinItem.objects.filter(classe__in=class_qs, is_active=True).values_list("classe_id", flat=True)
    )
    for classe in classes:
        # Le paramétrage du bulletin est une étape préalable à la saisie des notes.
        # Une fois configuré, les onglets de saisie proviennent exclusivement de
        # ces lignes de bulletin.
        grouped.append({
            "classe": classe,
            "evaluations": evaluation_map.get(classe.id, []),
            "bulletin_configured": classe.id in configured,
        })
    return render(request, "pedagogie/terms/list.html", {
        "terms": terms, "school_year": year, "classes": classes, "class_groups": grouped,
        "teacher_scope": not scope.unrestricted,
    })


@login_required
def term_create(request):
    year = viewed_year()
    errors = []
    name = (request.POST.get("name") or "").strip()
    raw_order = (request.POST.get("order") or "1").strip()
    try:
        order = int(raw_order)
    except (TypeError, ValueError):
        order = 1
        errors.append("L’ordre doit être un nombre entier positif.")
    if request.method == "POST" and year:
        if not name:
            errors.append("Le nom de la période est obligatoire.")
        if order < 1:
            errors.append("L’ordre doit être supérieur ou égal à 1.")
        if len(name) > 50:
            errors.append("Le nom de la période ne doit pas dépasser 50 caractères.")
        if Term.objects.filter(school_year=year, name=name).exists():
            errors.append("Cette période existe déjà pour l’année scolaire active.")
        if not errors:
            Term.objects.create(school_year=year, name=name, order=order)
            if _is_modal_request(request):
                return _modal_reload_response()
            return redirect("term_list")
    context = {"school_year": year, "action_url": request.path, "errors": errors, "name": name, "order": raw_order}
    if _is_modal_request(request):
        return render(request, "pedagogie/terms/_modal_form.html", context)
    return render(request, "pedagogie/terms/form.html", context)


@login_required
@transaction.atomic
def grade_entry(request, enrollment_id, term_id):
    """Ancien parcours individuel conservé pour compatibilité."""
    enrollment = get_object_or_404(Enrollment, pk=enrollment_id)
    term = get_object_or_404(Term, pk=term_id)
    links = enrollment.classe.applicable_subject_links().filter(subject__is_active=True).order_by("order", "subject__name")
    subjects = [link.subject for link in links]
    if request.method == "POST" and BulletinLock.get_for(enrollment.classe_id, term.id):
        messages.error(request, BulletinLock.MESSAGE.format(classe=enrollment.classe.display_name, term=term.name))
        return redirect("grade_entry", enrollment_id=enrollment.id, term_id=term.id)
    if request.method == "POST":
        for subject in subjects:
            composition = request.POST.get(f"composition_{subject.id}") or None
            class_average = request.POST.get(f"class_average_{subject.id}") or None
            if composition is None and class_average is None:
                continue
            # evaluation=None : la note du bulletin, distincte des notes
            # d'évaluations (sinon plusieurs lignes correspondent).
            Grade.objects.update_or_create(
                enrollment=enrollment, subject=subject, term=term, evaluation=None,
                defaults={"composition": composition, "class_average": class_average},
            )
        return redirect("grade_entry", enrollment_id=enrollment.id, term_id=term.id)
    grade_map = {g.subject_id: g for g in Grade.objects.filter(enrollment=enrollment, term=term, evaluation__isnull=True)}
    rows = [{
        "subject": subject,
        "name": next((link.name for link in links if link.subject_id == subject.id), subject.name),
        "grade": grade_map.get(subject.id),
        "coefficient": next((link.coefficient for link in links if link.subject_id == subject.id), subject.coefficient),
    } for subject in subjects]
    return render(request, "pedagogie/grades/form.html", {
        "enrollment": enrollment, "term": term, "rows": rows,
        "mode": "F1" if enrollment.classe.education_level.school_type == "fundamental_1" else "SECONDARY",
        "average": moyenne_generale(enrollment, term),
    })


@login_required
@transaction.atomic
def bulletin_config(request, classe_id):
    """Paramétrage des lignes du bulletin pour une classe."""
    classe = get_object_or_404(Classe, pk=classe_id)
    items = list(BulletinItem.objects.filter(classe=classe, is_active=True).select_related("subject").order_by("order", "id"))
    links = list(classe.applicable_subject_links().filter(subject__is_active=True).order_by("order", "name", "subject__name"))
    selected_subject_ids = {item.subject_id for item in items if item.subject_id}
    available_links = [link for link in links if link.subject_id not in selected_subject_ids]
    locked_terms = [lock.term for lock in BulletinLock.objects.filter(classe=classe).select_related("term").order_by("term__order")]

    if request.method == "POST" and locked_terms:
        # Ajouter une ligne ou changer un coefficient modifierait les moyennes
        # de bulletins déjà verrouillés.
        messages.error(request, "Paramétrage bloqué : bulletins verrouillés pour " + ", ".join(t.name for t in locked_terms)
                       + ". Déverrouillez-les d'abord si une correction est nécessaire.")
        return redirect("bulletin_config", classe_id=classe.id)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_subject":
            # Plusieurs matières peuvent être ajoutées en une seule fois.
            subject_ids = []
            raw_subject_ids = request.POST.getlist("subject_ids")
            # Compatibilité avec les anciens formulaires/tests qui envoyaient
            # encore un seul champ `subject_id`.
            if not raw_subject_ids:
                legacy_subject_id = request.POST.get("subject_id")
                if legacy_subject_id:
                    raw_subject_ids = [legacy_subject_id]
            for raw_id in raw_subject_ids:
                try:
                    subject_ids.append(int(raw_id))
                except (TypeError, ValueError):
                    continue
            existing_subject_ids = set(
                BulletinItem.objects.filter(classe=classe, subject__isnull=False).values_list("subject_id", flat=True)
            )
            next_order = max([item.order for item in items], default=0) + 1
            for subject_id in subject_ids:
                link = next((link for link in links if link.subject_id == subject_id), None)
                if not link or subject_id in existing_subject_ids:
                    continue
                BulletinItem.objects.create(
                    classe=classe, subject=link.subject, coefficient=link.coefficient,
                    max_score=10 if classe.education_level.school_type == "fundamental_1" else 20,
                    order=next_order,
                )
                existing_subject_ids.add(subject_id)
                next_order += 1
        elif action == "add_custom":
            label = (request.POST.get("label") or "").strip()
            coefficient_raw = request.POST.get("coefficient") or "1"
            max_score_raw = request.POST.get("max_score") or ("10" if classe.education_level.school_type == "fundamental_1" else "20")
            try:
                coefficient = float(coefficient_raw)
                max_score = float(max_score_raw)
            except (TypeError, ValueError):
                coefficient = 0
                max_score = 0
            if label and coefficient > 0 and max_score > 0:
                BulletinItem.objects.create(
                    classe=classe, label=label, coefficient=coefficient, max_score=max_score,
                    order=(items[-1].order + 1 if items else 1),
                )
        elif action in {"delete", "up", "down"}:
            try:
                item_id = int(request.POST.get("item_id"))
            except (TypeError, ValueError):
                item_id = None
            item = BulletinItem.objects.filter(pk=item_id, classe=classe, is_active=True).first() if item_id else None
            if item:
                ordered = list(BulletinItem.objects.filter(classe=classe, is_active=True).order_by("order", "id"))
                idx = ordered.index(item)
                if action == "delete":
                    item.is_active = False
                    item.save(update_fields=["is_active"])
                else:
                    target = idx - 1 if action == "up" else idx + 1
                    if 0 <= target < len(ordered):
                        other = ordered[target]
                        item.order, other.order = other.order, item.order
                        item.save(update_fields=["order"])
                        other.save(update_fields=["order"])
        return redirect("bulletin_config", classe_id=classe.id)

    return render(request, "pedagogie/grades/bulletin_config.html", {
        "classe": classe, "items": items, "available_links": available_links, "locked_terms": locked_terms,
        "default_max_score": 10 if classe.education_level.school_type == "fundamental_1" else 20,
    })


@login_required
@transaction.atomic
def class_results(request, classe_id, term_id):
    """Saisie des notes d'une classe selon les onglets du bulletin configuré."""
    classe = get_object_or_404(Classe, pk=classe_id)
    term = get_object_or_404(Term, pk=term_id)
    if term.school_year_id != classe.school_year_id:
        return HttpResponse("L'évaluation et la classe doivent appartenir à la même année scolaire.", status=400)
    scope = TeacherScope(request.user)
    if not scope.can_access_class(classe.id):
        return deny(request, "Cette classe ne fait pas partie de vos affectations.")

    bulletin_items = list(BulletinItem.objects.filter(classe=classe, is_active=True).select_related("subject").order_by("order", "id"))
    allowed_subjects = scope.subject_ids(classe.id)
    if allowed_subjects is not None:
        # Professeur spécialiste : seules ses matières sont saisissables ; les
        # éléments personnalisés (sans matière) relèvent du titulaire.
        bulletin_items = [item for item in bulletin_items if item.subject_id in allowed_subjects]
        if not bulletin_items:
            return deny(request, "Le bulletin de cette classe n'est pas encore paramétré pour vos matières. Contactez le directeur des études.")
    # Le bulletin doit être paramétré avant toute saisie de notes. Les onglets
    # ne sont plus dérivés automatiquement du programme : ils reflètent
    # exactement les lignes retenues dans le paramétrage du bulletin.
    if not bulletin_items:
        if not scope.unrestricted:
            return deny(request, "Le bulletin de cette classe n'est pas encore paramétré. Contactez le directeur des études.")
        return redirect("bulletin_config", classe_id=classe.id)
    tabs = bulletin_items

    enrollments = list(Enrollment.objects.filter(classe=classe).select_related("student").order_by("student__first_name", "student__last_name"))
    for enrollment in enrollments:
        # Même instance de classe pour tous : son programme n'est chargé qu'une fois.
        enrollment.classe = classe
    selected_id = (request.POST.get("item_id") or request.GET.get("item")) if bulletin_items else (request.POST.get("subject_id") or request.GET.get("subject"))
    if selected_id:
        try:
            selected_id = int(selected_id)
        except (TypeError, ValueError):
            selected_id = None
    if bulletin_items:
        selected_item = next((item for item in tabs if item.id == selected_id), None)
        if selected_item is None and tabs:
            selected_item = tabs[0]
        selected_link = selected_item if selected_item else None
    else:
        selected_item = None
        selected_link = next((link for link in tabs if link.subject_id == selected_id), tabs[0] if tabs else None)

    lock = BulletinLock.get_for(classe.id, term.id)
    if request.method == "POST" and lock:
        messages.error(request, BulletinLock.MESSAGE.format(classe=classe.display_name, term=term.name))
        return redirect(request.get_full_path())
    if request.method == "POST" and selected_link:
        errors = []
        is_custom = bool(bulletin_items and selected_item and selected_item.subject_id is None)
        is_f1 = classe.education_level.school_type == "fundamental_1"
        max_score = float(selected_item.max_score) if is_custom else (10 if is_f1 else 20)
        for enrollment in enrollments:
            if is_custom and is_f1:
                raw = request.POST.get(f"note_{enrollment.id}_{selected_item.id}")
                if raw in (None, ""):
                    continue
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    errors.append(f"{enrollment.student.first_name} {enrollment.student.last_name} : valeur invalide.")
                    continue
                if value < 0 or value > max_score:
                    errors.append(f"{enrollment.student.first_name} {enrollment.student.last_name} : la note doit être comprise entre 0 et {max_score}.")
            elif is_custom:
                # Élément personnalisé en secondaire : même règle A/B qu'une matière
                # classique, pas une note unique héritée de F1.
                composition_raw = request.POST.get(f"composition_{enrollment.id}_{selected_item.id}")
                average_raw = request.POST.get(f"class_average_{enrollment.id}_{selected_item.id}")
                for raw in (composition_raw, average_raw):
                    if raw not in (None, ""):
                        try:
                            value = float(raw)
                        except (TypeError, ValueError):
                            errors.append(f"{enrollment.student.first_name} {enrollment.student.last_name} : valeur invalide.")
                            continue
                        if value < 0 or value > max_score:
                            errors.append(f"{enrollment.student.first_name} {enrollment.student.last_name} : la note doit être comprise entre 0 et {max_score}.")
                has_composition = composition_raw not in (None, "")
                has_average = average_raw not in (None, "")
                if has_composition != has_average:
                    errors.append(
                        f"{enrollment.student.first_name} {enrollment.student.last_name} : "
                        "la composition et la moyenne de classe A sont toutes les deux "
                        "requises pour ce niveau avant d'enregistrer."
                    )
            else:
                subject = selected_item.subject if bulletin_items else selected_link.subject
                composition_raw = request.POST.get(f"composition_{enrollment.id}_{subject.id}") or None
                class_average = request.POST.get(f"class_average_{enrollment.id}_{subject.id}") or None
                if composition_raw is None and class_average is None:
                    continue
                is_f1 = classe.education_level.school_type == "fundamental_1"
                if is_f1 and class_average is not None:
                    errors.append(
                        f"{enrollment.student.first_name} {enrollment.student.last_name} : "
                        "la moyenne de classe A n'est pas utilisée en Fondamentale 1."
                    )
                elif not is_f1 and (composition_raw is None or class_average is None):
                    # Le modèle Grade exige les deux valeurs pour ce niveau (cf. Grade.clean).
                    # Sans ce contrôle préalable, un enregistrement partiel provoque une
                    # erreur serveur (500) au lieu d'un message clair pour l'utilisateur.
                    errors.append(
                        f"{enrollment.student.first_name} {enrollment.student.last_name} : "
                        "la composition et la moyenne de classe A sont toutes les deux "
                        "requises pour ce niveau avant d'enregistrer."
                    )
        if errors:
            for error in errors:
                messages.error(request, error)
        if not errors:
            if is_custom and is_f1:
                for enrollment in enrollments:
                    raw = request.POST.get(f"note_{enrollment.id}_{selected_item.id}")
                    if raw in (None, ""):
                        continue
                    result, _ = BulletinItemResult.objects.update_or_create(
                        enrollment=enrollment, bulletin_item=selected_item, term=term,
                        defaults={"note": raw, "class_average": None, "composition": None},
                    )
                    result.full_clean()
                    result.save()
            elif is_custom:
                for enrollment in enrollments:
                    composition = request.POST.get(f"composition_{enrollment.id}_{selected_item.id}") or None
                    class_average = request.POST.get(f"class_average_{enrollment.id}_{selected_item.id}") or None
                    if composition is None and class_average is None:
                        continue
                    result, _ = BulletinItemResult.objects.update_or_create(
                        enrollment=enrollment, bulletin_item=selected_item, term=term,
                        defaults={"note": None, "class_average": class_average, "composition": composition},
                    )
                    result.full_clean()
                    result.save()
            else:
                subject = selected_item.subject if bulletin_items else selected_link.subject
                existing = {
                    g.enrollment_id: g
                    for g in Grade.objects.filter(
                        enrollment__in=enrollments, subject=subject, term=term, evaluation__isnull=True,
                    )
                }
                for enrollment in enrollments:
                    composition = request.POST.get(f"composition_{enrollment.id}_{subject.id}") or None
                    class_average = request.POST.get(f"class_average_{enrollment.id}_{subject.id}") or None
                    if composition is None and class_average is None:
                        continue
                    grade = existing.get(enrollment.id) or Grade(enrollment=enrollment, subject=subject, term=term)
                    grade.enrollment = enrollment
                    grade.term = term
                    grade.composition = composition
                    grade.class_average = class_average
                    # Validation métier avant l'unique écriture (auparavant :
                    # écriture, validation, puis seconde écriture). Les clés
                    # (élève, matière, période) viennent d'être chargées et
                    # l'unicité est garantie par ``existing`` : inutile de les
                    # revérifier une à une en base.
                    grade.full_clean(exclude=["enrollment", "subject", "term", "evaluation"])
                    grade.save()
            return redirect(f"{request.path}?item={selected_link.id if bulletin_items else selected_link.subject_id}")

    mode = "F1" if classe.education_level.school_type == "fundamental_1" else "SECONDARY"
    if bool(bulletin_items and selected_item and selected_item.subject_id is None):
        result_map = {r.enrollment_id: r for r in BulletinItemResult.objects.filter(bulletin_item=selected_item, term=term)}
        rows = [{"enrollment": e, "result": result_map.get(e.id)} for e in enrollments]
    else:
        subject = selected_item.subject if bulletin_items and selected_item else (selected_link.subject if selected_link else None)
        grade_map = {g.enrollment_id: g for g in Grade.objects.filter(enrollment__classe=classe, term=term, subject=subject, evaluation__isnull=True)} if subject else {}
        rows = [{"enrollment": e, "grade": grade_map.get(e.id)} for e in enrollments]

    return render(request, "pedagogie/grades/results.html", {
        "classe": classe, "term": term, "links": tabs,
        "selected_link": selected_item or selected_link, "rows": rows, "mode": mode,
        "bulletin_configured": bool(bulletin_items),
        "is_custom": bool(bulletin_items and selected_item and selected_item.subject_id is None),
        "teacher_scope": not scope.unrestricted,
        "lock": lock,
    })


@login_required
def class_bulletins(request, classe_id, term_id):
    """Espace bulletins d'une classe : liste complète et impression en lot."""
    classe = get_object_or_404(Classe, pk=classe_id)
    term = get_object_or_404(Term, pk=term_id)
    if term.school_year_id != classe.school_year_id:
        return HttpResponse("La classe et la période doivent appartenir à la même année scolaire.", status=400)

    terms = list(Term.objects.filter(school_year=classe.school_year).order_by("order", "id"))
    enrollments = list(
        Enrollment.objects.filter(classe=classe)
        .select_related("student")
        .order_by("student__first_name", "student__last_name")
    )
    # Un bulletin logique existe pour chaque inscription/période ; les notes
    # restent dans Grade et sont lues au moment de l'impression.
    from common.views import bulletins_for
    bulletins = {b.enrollment_id: b for b in bulletins_for(enrollments, term)}
    from common import whatsapp
    for enrollment in enrollments:
        enrollment.whatsapp_url = whatsapp.wa_url(whatsapp.family_phone(enrollment.student),
                                                  whatsapp.bulletin_text(enrollment, term, classe.school_year.school))

    return render(request, "pedagogie/grades/bulletins.html", {
        "classe": classe,
        "term": term,
        "terms": terms,
        "enrollments": enrollments,
        "bulletins": bulletins,
        "lock": BulletinLock.get_for(classe.id, term.id),
    })


@login_required
@require_POST
def bulletin_lock_toggle(request, classe_id, term_id):
    """Verrouille ou déverrouille les bulletins d'une classe pour une période."""
    classe = get_object_or_404(Classe, pk=classe_id)
    term = get_object_or_404(Term, pk=term_id, school_year_id=classe.school_year_id)
    if request.POST.get("action") == "unlock":
        deleted, _ = BulletinLock.objects.filter(classe=classe, term=term).delete()
        if deleted:
            messages.success(request, f"Bulletins de {classe.display_name} ({term.name}) déverrouillés : la saisie est rouverte.")
    else:
        _, created = BulletinLock.objects.get_or_create(classe=classe, term=term, defaults={"locked_by": request.user})
        if created:
            messages.success(request, f"Bulletins de {classe.display_name} ({term.name}) verrouillés.")
    return redirect("class_bulletins", classe_id=classe.id, term_id=term.id)


@login_required
@transaction.atomic
def evaluation_results(request, evaluation_id):
    """Saisie par onglets des matières retenues pour une évaluation."""
    evaluation = get_object_or_404(
        Evaluation.objects.select_related("classe__education_level", "classe__pedagogical_track", "term"),
        pk=evaluation_id,
    )
    classe = evaluation.classe
    scope = TeacherScope(request.user)
    if not scope.can_access_class(classe.id):
        return deny(request, "Cette classe ne fait pas partie de vos affectations.")
    links = list(evaluation.subject_links.select_related("subject").order_by("order", "subject__name"))
    allowed_subjects = scope.subject_ids(classe.id)
    if allowed_subjects is not None:
        links = [link for link in links if link.subject_id in allowed_subjects]
        if not links:
            return deny(request, "Aucune de vos matières n'est concernée par cette évaluation.")
    contextual_links = {link.subject_id: link for link in classe.applicable_subject_links()}
    for link in links:
        link.display_name = contextual_links.get(link.subject_id).name if link.subject_id in contextual_links else link.subject.name
    enrollments = list(Enrollment.objects.filter(classe=classe).select_related("student").order_by("student__first_name", "student__last_name"))
    mode = "F1" if classe.education_level.school_type == "fundamental_1" else "SECONDARY"
    # La distinction A (moyenne de classe) / B (composition) reflète le calcul
    # officiel d'une VRAIE composition de période. Une évaluation ponctuelle
    # (interrogation, devoir…) n'a qu'une seule note : lui appliquer ce
    # découpage n'a pas de sens et n'était qu'un héritage du modèle Grade
    # (partagé avec le bulletin). Ici, une seule évaluation à la fois est de
    # toute façon saisie : "une seule matière visible" correspond au fait que
    # la matière sélectionnée est bien la seule affichée dans le tableau.
    single_note = mode != "F1" and evaluation.nature == Evaluation.Nature.PUNCTUAL
    selected_subject_id = request.POST.get("subject_id") or request.GET.get("subject") or (links[0].subject_id if links else None)
    try:
        selected_subject_id = int(selected_subject_id) if selected_subject_id else None
    except (TypeError, ValueError):
        selected_subject_id = links[0].subject_id if links else None
    selected_link = next((link for link in links if link.subject_id == selected_subject_id), links[0] if links else None)

    errors = []
    if request.method == "POST":
        if not selected_link:
            errors.append("Aucune matière n'est sélectionnée pour cette évaluation.")
        else:
            max_score = 10 if mode == "F1" else 20
            if single_note:
                for enrollment in enrollments:
                    raw = request.POST.get(f"note_{enrollment.id}_{selected_link.subject_id}")
                    if raw not in (None, ""):
                        try:
                            value = float(raw)
                        except (TypeError, ValueError):
                            errors.append(f"{enrollment.student.first_name} {enrollment.student.last_name} : valeur invalide.")
                            continue
                        if value < 0 or value > max_score:
                            errors.append(
                                f"{enrollment.student.first_name} {enrollment.student.last_name} : la note doit être comprise entre 0 et {max_score}."
                            )
            else:
                for enrollment in enrollments:
                    composition_raw = request.POST.get(f"composition_{enrollment.id}_{selected_link.subject_id}")
                    average_raw = request.POST.get(f"class_average_{enrollment.id}_{selected_link.subject_id}")
                    for label, raw in (("composition", composition_raw), ("class_average", average_raw)):
                        if raw not in (None, ""):
                            try:
                                value = float(raw)
                            except (TypeError, ValueError):
                                errors.append(f"{enrollment.student.first_name} {enrollment.student.last_name} : valeur invalide.")
                                continue
                            if value < 0 or value > max_score:
                                errors.append(
                                    f"{enrollment.student.first_name} {enrollment.student.last_name} : la note doit être comprise entre 0 et {max_score}."
                                )
                if mode == "F1":
                    for enrollment in enrollments:
                        if request.POST.get(f"class_average_{enrollment.id}_{selected_link.subject_id}") not in (None, ""):
                            errors.append(
                                f"{enrollment.student.first_name} {enrollment.student.last_name} : "
                                "la moyenne de classe A n'est pas utilisée en Fondamentale 1."
                            )
                else:
                    for enrollment in enrollments:
                        composition_raw = request.POST.get(f"composition_{enrollment.id}_{selected_link.subject_id}")
                        average_raw = request.POST.get(f"class_average_{enrollment.id}_{selected_link.subject_id}")
                        has_composition = composition_raw not in (None, "")
                        has_average = average_raw not in (None, "")
                        if has_composition != has_average:
                            # Grade.clean() exige composition ET moyenne de classe A ensemble
                            # pour ce niveau : sans ce contrôle, l'enregistrement partiel plante
                            # avec une erreur serveur au lieu d'un message clair.
                            errors.append(
                                f"{enrollment.student.first_name} {enrollment.student.last_name} : "
                                "la composition et la moyenne de classe A doivent être saisies "
                                "ensemble pour ce niveau."
                            )
        if not errors:
            for enrollment in enrollments:
                if single_note:
                    note = request.POST.get(f"note_{enrollment.id}_{selected_link.subject_id}") or None
                    if note is None:
                        continue
                    # Une seule note saisie : elle est reflétée dans A et B pour rester
                    # compatible avec Grade (qui exige les deux hors F1), sans fausser la
                    # moyenne — (note + note*2) / 3 = note.
                    composition, class_average = note, note
                else:
                    composition = request.POST.get(f"composition_{enrollment.id}_{selected_link.subject_id}") or None
                    class_average = request.POST.get(f"class_average_{enrollment.id}_{selected_link.subject_id}") or None
                    if composition is None and class_average is None:
                        continue
                grade, _ = Grade.objects.update_or_create(
                    enrollment=enrollment, subject=selected_link.subject, term=evaluation.term, evaluation=evaluation,
                    defaults={"composition": composition, "class_average": class_average},
                )
                grade.full_clean()
                grade.save()
            return redirect("evaluation_results", evaluation_id=evaluation.id)

    grade_map = {
        g.enrollment_id: g
        for g in Grade.objects.filter(evaluation=evaluation, subject=selected_link.subject)
    } if selected_link else {}
    rows = [{"enrollment": enrollment, "grade": grade_map.get(enrollment.id)} for enrollment in enrollments]
    has_saved_notes = bool(grade_map)
    return render(request, "pedagogie/grades/evaluation_results.html", {
        "evaluation": evaluation, "classe": classe, "links": links, "selected_link": selected_link,
        "rows": rows, "mode": mode, "single_note": single_note, "has_saved_notes": has_saved_notes,
        "errors": errors,
    })


@login_required
def class_ponctuel_summary(request, classe_id, term_id):
    """Point d'entrée du bulletin non officiel (évaluations ponctuelles).

    Liste, par élève, si des notes d'évaluations ponctuelles existent pour la
    période, avec un lien d'impression individuel et un lien d'impression
    groupée pour toute la classe.
    """
    from .models import Evaluation as EvaluationModel

    classe = get_object_or_404(Classe, pk=classe_id)
    term = get_object_or_404(Term, pk=term_id)
    if term.school_year_id != classe.school_year_id:
        return HttpResponse("La classe et la période doivent appartenir à la même année scolaire.", status=400)

    enrollments = list(
        Enrollment.objects.filter(classe=classe)
        .select_related("student")
        .order_by("student__first_name", "student__last_name")
    )
    grade_counts = {}
    for row in (
        Grade.objects.filter(
            enrollment__classe=classe, term=term, evaluation__nature=EvaluationModel.Nature.PUNCTUAL,
        ).values("enrollment_id").annotate(count=Count("id"))
    ):
        grade_counts[row["enrollment_id"]] = row["count"]

    rows = [{"enrollment": e, "count": grade_counts.get(e.id, 0)} for e in enrollments]
    return render(request, "pedagogie/grades/ponctuel_summary.html", {
        "classe": classe, "term": term, "rows": rows,
        "has_any": any(r["count"] for r in rows),
    })


@login_required
def evaluation_sheet_print(request, evaluation_id, subject_id):
    evaluation = get_object_or_404(Evaluation.objects.select_related("classe__education_level", "term"), pk=evaluation_id)
    link = get_object_or_404(evaluation.subject_links.select_related("subject"), subject_id=subject_id)
    if not TeacherScope(request.user).can_access_subject(evaluation.classe_id, link.subject_id):
        return deny(request, "Cette matière ne fait pas partie de vos affectations.")
    contextual_link = next((item for item in evaluation.classe.applicable_subject_links() if item.subject_id == link.subject_id), None)
    link.display_name = contextual_link.name if contextual_link else link.subject.name
    enrollments = Enrollment.objects.filter(classe=evaluation.classe).select_related("student").order_by("student__first_name", "student__last_name")
    mode = "F1" if evaluation.classe.education_level.school_type == "fundamental_1" else "SECONDARY"
    return render(request, "pedagogie/grades/print_sheet.html", {
        "classe": evaluation.classe, "term": evaluation.term, "evaluation": evaluation,
        "link": link, "enrollments": enrollments, "mode": mode,
    })


@login_required
def grade_sheet_print(request, classe_id, term_id, subject_id):
    """Fiche vierge imprimable pour collecter les notes d'une matière."""
    classe = get_object_or_404(Classe, pk=classe_id)
    term = get_object_or_404(Term, pk=term_id)
    link = get_object_or_404(classe.applicable_subject_links().filter(subject__is_active=True), subject_id=subject_id)
    if not TeacherScope(request.user).can_access_subject(classe.id, link.subject_id):
        return deny(request, "Cette matière ne fait pas partie de vos affectations.")
    enrollments = Enrollment.objects.filter(classe=classe).select_related("student").order_by("student__first_name", "student__last_name")
    mode = "F1" if classe.education_level.school_type == "fundamental_1" else "SECONDARY"
    return render(request, "pedagogie/grades/print_sheet.html", {
        "classe": classe, "term": term, "link": link, "enrollments": enrollments, "mode": mode,
    })
