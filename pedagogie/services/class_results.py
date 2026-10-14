"""Calcul groupé des résultats d'une classe pour une période.

Le bulletin d'un élève a besoin de sa moyenne, mais aussi de son rang, donc
de la moyenne de TOUS les élèves de la classe. Calculé élève par élève, cela
coûtait ~200 requêtes par bulletin et l'impression d'une classe devenait
quadratique (plus de 9 000 requêtes et 13 s pour 60 élèves).

``ClassTermResults`` charge en une poignée de requêtes les lignes du bulletin,
le programme, toutes les notes et tous les résultats directs de la classe,
puis applique exactement les mêmes règles que ``pedagogie.utils.moyenne_generale``
et ``Bulletin.lignes``.
"""
from decimal import Decimal

from pedagogie.bulletin_appreciations import appreciation_for


class ClassTermResults:
    def __init__(self, classe, term):
        from pedagogie.models import BulletinItem, BulletinItemResult, Enrollment, Grade

        self.classe = classe
        self.term = term
        self.mode = "F1" if classe.education_level.school_type == "fundamental_1" else "SECONDARY"
        self.items = list(
            BulletinItem.objects.filter(classe=classe, is_active=True)
            .select_related("subject").order_by("order", "id")
        )
        self.links = {link.subject_id: link for link in classe.applicable_subject_links()}
        self.enrollments = list(
            Enrollment.objects.filter(classe=classe, school_year_id=classe.school_year_id)
            .select_related("student").order_by("student__last_name", "student__first_name", "id")
        )
        enrollment_ids = [e.id for e in self.enrollments]
        self.grades = {}
        for grade in (
            Grade.objects.filter(enrollment_id__in=enrollment_ids, term=term, evaluation__isnull=True)
            .select_related("subject").order_by("id")
        ):
            self.grades.setdefault(grade.enrollment_id, {}).setdefault(grade.subject_id, grade)
        self.direct = {}
        for result in BulletinItemResult.objects.filter(enrollment_id__in=enrollment_ids, term=term):
            self.direct.setdefault(result.enrollment_id, {})[result.bulletin_item_id] = result
        self._averages = {}
        self._ranks = None

    # Règles de calcul -------------------------------------------------
    def _grade_average(self, grade):
        if grade.composition is None:
            return 0
        if self.mode == "F1":
            return grade.composition
        if grade.class_average is None:
            return 0
        return (grade.class_average + (grade.composition * 2)) / 3

    def coefficient(self, grade):
        link = self.links.get(grade.subject_id)
        return link.coefficient if link else grade.subject.coefficient

    def _grade_total(self, grade):
        return Decimal(str(self._grade_average(grade))) * self.coefficient(grade)

    def item_display_name(self, item):
        if item.subject_id:
            link = self.links.get(item.subject_id)
            return link.name if link else item.subject.name
        return item.label

    def average(self, enrollment_id):
        if enrollment_id not in self._averages:
            self._averages[enrollment_id] = self._compute_average(enrollment_id)
        return self._averages[enrollment_id]

    def _compute_average(self, enrollment_id):
        grades = self.grades.get(enrollment_id, {})
        direct = self.direct.get(enrollment_id, {})
        if not self.items:
            notes = sorted(grades.values(), key=lambda g: g.id)
            if not notes:
                return 0
            if self.mode == "F1":
                valid = [self._grade_average(n) for n in notes if n.composition is not None]
                return sum(valid) / len(valid) if valid else 0
            complete = [n for n in notes if n.composition is not None and n.class_average is not None]
            total_points = sum(self._grade_total(n) for n in complete)
            total_coeff = sum(self.coefficient(n) for n in complete)
            return total_points / total_coeff if total_coeff else 0

        if self.mode == "F1":
            values = []
            for item in self.items:
                if item.subject_id:
                    grade = grades.get(item.subject_id)
                    if grade and grade.composition is not None:
                        values.append(self._grade_average(grade))
                else:
                    result = direct.get(item.id)
                    if result and result.note is not None:
                        values.append(float(result.note))
            return sum(values) / len(values) if values else 0

        total_points = 0.0
        total_coeff = 0.0
        for item in self.items:
            value = None
            if item.subject_id:
                grade = grades.get(item.subject_id)
                if grade and grade.composition is not None and grade.class_average is not None:
                    value = self._grade_average(grade)
            else:
                result = direct.get(item.id)
                if result:
                    value = result.moyenne_for_mode(self.mode)
            if value is not None:
                coeff = float(item.coefficient or 0)
                total_points += value * coeff
                total_coeff += coeff
        return total_points / total_coeff if total_coeff else 0

    def rank(self, enrollment_id):
        if self._ranks is None:
            scores = []
            for enrollment in self.enrollments:
                try:
                    score = self.average(enrollment.id)
                except Exception:
                    continue
                if score is not None:
                    scores.append((enrollment.id, score))
            scores.sort(key=lambda item: item[1], reverse=True)
            self._ranks = {eid: position for position, (eid, _s) in enumerate(scores, start=1)}
        return self._ranks.get(enrollment_id)

    def lines(self, enrollment_id):
        result = []
        mode = self.mode
        grades = self.grades.get(enrollment_id, {})
        direct = self.direct.get(enrollment_id, {})
        if not self.items:
            for grade in sorted(grades.values(), key=lambda g: g.subject.name):
                moyenne = self._grade_average(grade)
                link = self.links.get(grade.subject_id)
                row = {
                    "subject": grade.subject,
                    "display_name": link.name if link else grade.subject.name,
                    "moyenne": moyenne,
                    "appreciation": appreciation_for(moyenne, 10 if mode == "F1" else 20),
                }
                if mode == "F1":
                    row["composition"] = grade.composition
                else:
                    total = self._grade_total(grade)
                    row.update({
                        "moyenne_de_classe": grade.class_average, "note_de_composition": grade.composition,
                        "class_average": grade.class_average, "composition": grade.composition,
                        "coefficient": self.coefficient(grade), "moyenne_coeff": total, "total": total,
                    })
                result.append(row)
            return result

        for item in self.items:
            if item.subject_id:
                grade = grades.get(item.subject_id)
                moyenne = self._grade_average(grade) if grade else None
                row = {
                    "subject": item.subject,
                    "display_name": self.item_display_name(item),
                    "moyenne": moyenne,
                    "appreciation": appreciation_for(moyenne, 10 if mode == "F1" else 20) if moyenne is not None else "",
                    "bulletin_item": item,
                }
                if mode == "F1":
                    row["composition"] = grade.composition if grade else None
                else:
                    row["moyenne_de_classe"] = grade.class_average if grade else None
                    row["note_de_composition"] = grade.composition if grade else None
                    row["class_average"] = row["moyenne_de_classe"]
                    row["composition"] = row["note_de_composition"]
                    row["coefficient"] = item.coefficient
                    row["moyenne_coeff"] = (moyenne * float(item.coefficient)) if moyenne is not None else None
                    row["total"] = row["moyenne_coeff"]
                result.append(row)
            else:
                found = direct.get(item.id)
                moyenne = found.moyenne_for_mode(mode) if found else None
                row = {
                    "subject": None,
                    "display_name": self.item_display_name(item),
                    "moyenne": moyenne,
                    "appreciation": appreciation_for(moyenne, float(item.max_score)) if moyenne is not None else "",
                    "bulletin_item": item,
                    "is_custom": True,
                }
                if mode == "F1":
                    row["composition"] = moyenne
                else:
                    row["moyenne_de_classe"] = float(found.class_average) if found and found.class_average is not None else None
                    row["note_de_composition"] = float(found.composition) if found and found.composition is not None else None
                    row["class_average"] = row["moyenne_de_classe"]
                    row["composition"] = row["note_de_composition"]
                    row["coefficient"] = item.coefficient
                    row["moyenne_coeff"] = (moyenne * float(item.coefficient)) if moyenne is not None else None
                    row["total"] = row["moyenne_coeff"]
                result.append(row)
        return result
