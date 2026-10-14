from .models import Grade, Enrollment, BulletinItemResult


def moyenne_matiere(grade):
    """Moyenne officielle d'une matière pour l'évaluation."""
    return grade.moyenne()


def moyenne_generale(enrollment, term):
    """Moyenne officielle de la période.

    Lorsqu'un bulletin est paramétré pour la classe, ses lignes deviennent
    les lignes de référence de la moyenne : les matières existantes utilisent
    leurs résultats J4, tandis que les éléments personnalisés utilisent leur
    note finale saisie directement. Sans paramétrage, le calcul historique est
    conservé.
    """
    items = list(enrollment.classe.bulletin_items.filter(is_active=True).order_by("order", "id"))
    if not items:
        notes = list(
            Grade.objects.filter(enrollment=enrollment, term=term, evaluation__isnull=True)
            .select_related("subject", "enrollment__classe__education_level")
        )
        if not notes:
            return 0
        if notes[0].evaluation_mode == "F1":
            valid = [n.moyenne() for n in notes if n.composition is not None]
            return sum(valid) / len(valid) if valid else 0
        total_points = sum(n.total() for n in notes if n.composition is not None and n.class_average is not None)
        total_coeff = sum(n.coefficient for n in notes if n.composition is not None and n.class_average is not None)
        return total_points / total_coeff if total_coeff else 0

    mode = "F1" if enrollment.classe.education_level.school_type == "fundamental_1" else "SECONDARY"
    grades = {}
    for grade in Grade.objects.filter(enrollment=enrollment, term=term, evaluation__isnull=True).select_related("subject").order_by("id"):
        grades.setdefault(grade.subject_id, grade)
    direct = {
        r.bulletin_item_id: r
        for r in BulletinItemResult.objects.filter(enrollment=enrollment, term=term)
    }

    if mode == "F1":
        values = []
        for item in items:
            if item.subject_id:
                grade = grades.get(item.subject_id)
                if grade and grade.composition is not None:
                    values.append(grade.moyenne())
            else:
                result = direct.get(item.id)
                if result and result.note is not None:
                    values.append(float(result.note))
        return sum(values) / len(values) if values else 0

    total_points = 0.0
    total_coeff = 0.0
    for item in items:
        value = None
        if item.subject_id:
            grade = grades.get(item.subject_id)
            if grade and grade.composition is not None and grade.class_average is not None:
                value = grade.moyenne()
        else:
            # Un élément personnalisé suit la même règle A/B qu'une matière
            # classique en secondaire (cf. BulletinItemResult.moyenne()).
            result = direct.get(item.id)
            if result:
                value = result.moyenne()
        if value is not None:
            coeff = float(item.coefficient or 0)
            total_points += value * coeff
            total_coeff += coeff
    return total_points / total_coeff if total_coeff else 0


def classement(classe, term):
    results = []
    for enrollment in Enrollment.objects.filter(classe=classe).select_related("student"):
        results.append((enrollment, moyenne_generale(enrollment, term)))
    return sorted(results, key=lambda item: item[1], reverse=True)
