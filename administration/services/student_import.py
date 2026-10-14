"""Import Excel des élèves avec rapprochement des fiches existantes (retours du 07/10).

Chaque ligne du fichier est classée :
- « déjà connu » : même élève certain (matricule, ou même nom + indice commun
  sans contradiction) ; ses cases vides sont complétées automatiquement ;
- « à vérifier » : homonymes, nom proche appuyé par un indice, ou information
  contradictoire avec la fiche existante ; l'utilisateur décide ;
- « nouvel élève » : rien d'approchant.
Si aucune ligne n'est « à vérifier », l'import se fait directement.
"""
from dataclasses import dataclass, field

from django.db import transaction

from administration.services.student_matching import (
    COMPLETABLE_FIELDS, FIELD_LABELS, close_name, common_clues, comparable, fillable, hard_conflicts, norm, same_name,
)
from pedagogie.models import Enrollment, Student

DISPLAY_FIELDS = ["first_name", "last_name"] + COMPLETABLE_FIELDS


def _show(field, value):
    if value in (None, ""):
        return "—"
    if field == "date_of_birth":
        return value.strftime("%d/%m/%Y")
    if field == "sex":
        return {"M": "Garçon", "F": "Fille"}.get(value, value)
    if field == "recruitment_year":
        return f"{value}-{int(value) + 1}"
    return str(value)


@dataclass
class ImportRow:
    index: int
    line: int
    data: dict
    status: str = ""
    message: str = ""
    student: object = None                  # fiche proposée
    candidates: list = field(default_factory=list)   # [(id, libellé, indices)]
    fills: list = field(default_factory=list)        # [(libellé, valeur)]
    differences: list = field(default_factory=list)  # [(champ, libellé, actuel, fichier)]

    @property
    def name(self):
        return f"{self.data.get('last_name', '')} {self.data.get('first_name', '')}".strip()

    @property
    def default_choice(self):
        return str(self.student.pk) if self.student else ("skip" if self.status == "erreur" else "new")

    @property
    def needs_review(self):
        return self.status == "à vérifier"


def _label(student, year):
    e = student.enrollments.filter(school_year=year).select_related("classe__education_level", "classe__pedagogical_track").first()
    parts = [f"{student.last_name} {student.first_name}"]
    parts.append(student.matricule or "sans matricule")
    parts.append(student.date_of_birth.strftime("%d/%m/%Y") if student.date_of_birth else "naissance —")
    parts.append(e.classe.display_name if e else "pas inscrit cette année")
    return " · ".join(parts)


def _describe(row, student):
    row.fills = [(FIELD_LABELS[f], _show(f, row.data.get(f))) for f in fillable(student, row.data)]
    row.differences = []
    for f in DISPLAY_FIELDS:
        current, new = getattr(student, f), row.data.get(f)
        a, b = comparable(f, current), comparable(f, new)
        if a is not None and b is not None and a != b:
            row.differences.append((f, FIELD_LABELS[f], _show(f, current), _show(f, new)))


def analyze(rows_data, year):
    """``rows_data`` : liste de (n° de ligne, dict des champs). Retourne des ImportRow."""
    students = list(Student.objects.all())
    by_initial = {}
    for s in students:
        by_initial.setdefault(norm(s.last_name)[:1], []).append(s)
    by_matricule = {s.matricule.strip().lower(): s for s in students if s.matricule}
    enrolled_now = set(Enrollment.objects.filter(school_year=year).values_list("student_id", flat=True))
    result, seen = [], {}
    for index, (line, data) in enumerate(rows_data):
        row = ImportRow(index=index, line=line, data=data)
        result.append(row)
        if not data.get("first_name") or not data.get("last_name"):
            row.status, row.message = "erreur", "Prénom et Nom sont obligatoires (ligne ignorée)"
            continue
        key = (data.get("matricule") or "").lower() or (norm(data["first_name"]), norm(data["last_name"]), data.get("date_of_birth"))
        if key in seen:
            row.status, row.message = "erreur", f"{data['first_name']} {data['last_name']} apparaît deux fois dans le fichier (déjà ligne {seen[key]}, ligne ignorée)"
            continue
        seen[key] = line
        by_mat = by_matricule.get((data.get("matricule") or "").strip().lower()) if data.get("matricule") else None
        pool = by_initial.get(norm(data["last_name"])[:1], [])
        exact = [s for s in pool if same_name(data, s)]
        close = [s for s in pool if s not in exact and close_name(data, s)]

        def clues(s):
            found = common_clues(data, s)
            if s.pk in enrolled_now:
                found.append("déjà inscrit cette année")
            return found

        row.candidates = [(str(s.pk), _label(s, year), clues(s)) for s in ([by_mat] if by_mat else []) + exact + close
                          if s is not None][:10]
        # dédoublonne (la fiche au matricule peut aussi être dans « exact »)
        unique, ids = [], set()
        for c in row.candidates:
            if c[0] not in ids:
                ids.add(c[0]); unique.append(c)
        row.candidates = unique

        if by_mat:
            row.student = by_mat
            _describe(row, by_mat)
            if not close_name(data, by_mat):
                row.status, row.message = "à vérifier", f"Ce matricule appartient déjà à {by_mat.last_name} {by_mat.first_name} : vérifiez."
            elif row.differences:
                row.status, row.message = "à vérifier", "Même matricule, mais des informations diffèrent : choisissez celles à garder."
            else:
                row.status, row.message = "déjà connu", "Même matricule."
            continue
        sure = [s for s in exact if not hard_conflicts(data, s) and clues(s)]
        if len(sure) == 1:
            s = sure[0]
            row.student = s
            _describe(row, s)
            if row.differences:
                row.status, row.message = "à vérifier", "Même élève probable, mais des informations diffèrent : choisissez celles à garder."
            else:
                row.status, row.message = "déjà connu", "Même élève : " + ", ".join(clues(s)) + "."
            continue
        if exact:
            row.status = "à vérifier"
            row.message = ("Plusieurs élèves portent ce nom : choisissez le bon ou créez une nouvelle fiche."
                           if len(exact) > 1 else
                           "Un élève porte déjà ce nom, sans indice commun ou avec une information contradictoire : même élève ou homonyme ?")
            continue
        close_sure = [s for s in close if not hard_conflicts(data, s) and clues(s)]
        if close_sure:
            row.student = close_sure[0] if len(close_sure) == 1 else None
            if row.student:
                _describe(row, row.student)
            row.status, row.message = "à vérifier", "Nom proche d'un élève existant qui partage un indice : même élève avec une autre orthographe ?"
            continue
        row.status, row.message = "nouvel élève", ""
    return result


@transaction.atomic
def apply(rows, year, classe, decisions=None, replacements=None):
    """Enregistre l'import. ``decisions`` : {index: id | "new" | "skip"} ;
    ``replacements`` : {index: {champs à remplacer par la valeur du fichier}}."""
    decisions = decisions or {}
    replacements = replacements or {}
    report = {"created": 0, "completed": 0, "updated": 0, "enrolled": 0, "already": 0, "skipped": 0,
              "elsewhere": [], "errors": [], "notes": []}
    for row in rows:
        if row.status == "erreur":
            report["errors"].append(f"Ligne {row.line} : {row.message}")
            continue
        choice = str(decisions.get(row.index, row.default_choice))
        if choice == "skip":
            report["skipped"] += 1
            continue
        data = row.data
        if choice == "new":
            values = {f: data.get(f) for f in DISPLAY_FIELDS if data.get(f) not in (None, "")}
            if values.get("matricule") and Student.objects.filter(matricule=values["matricule"]).exists():
                report["notes"].append(f"Ligne {row.line} : matricule {values.pop('matricule')} déjà utilisé, fiche créée sans matricule")
            student = Student.objects.create(**values)
            report["created"] += 1
        else:
            student = Student.objects.filter(pk=choice).first()
            if not student:
                report["errors"].append(f"Ligne {row.line} : fiche choisie introuvable")
                continue
            changed = []
            for f in fillable(student, data):
                if f == "matricule" and Student.objects.filter(matricule=data[f]).exclude(pk=student.pk).exists():
                    continue
                setattr(student, f, data[f]); changed.append(f)
            if changed:
                report["completed"] += 1
            replaced = []
            for f in replacements.get(row.index, ()):
                if f not in DISPLAY_FIELDS or data.get(f) in (None, ""):
                    continue
                if f == "matricule" and Student.objects.filter(matricule=data[f]).exclude(pk=student.pk).exists():
                    report["notes"].append(f"Ligne {row.line} : matricule {data[f]} déjà utilisé par une autre fiche, non remplacé")
                    continue
                setattr(student, f, data[f]); replaced.append(f)
            if replaced:
                report["updated"] += 1
            if changed or replaced:
                student.save()
        enrollment, is_new = Enrollment.objects.get_or_create(student=student, school_year=year, defaults={"classe": classe})
        if is_new:
            report["enrolled"] += 1
        elif enrollment.classe_id == classe.id:
            report["already"] += 1
        else:
            report["elsewhere"].append(f"{student} (déjà inscrit(e) en {enrollment.classe.display_name})")
    return report
