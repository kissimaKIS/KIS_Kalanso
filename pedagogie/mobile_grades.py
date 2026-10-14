"""Saisie des notes sur téléphone ou tablette, sans internet.

Fondamental (1er et 2nd cycle), lycée et centre professionnel.

Deux sortes de paquets :
- *par enseignant* : ses classes et ses matières (lignes personnalisées
  seulement s'il est affecté à toute la classe, comme à l'écran) ;
- *par classe* : toutes les lignes du bulletin des classes choisies, Conduite
  comprise, pour une saisie par le secrétariat ou la direction.

Deux modes de notes :
- ``single`` (Fondamentale 1) : une note unique, sur 10 pour une matière ;
- ``ab`` (Fondamentale 2, lycée, centre) : A = moyenne de classe, B = composition.

Circuit :
1. Kalanso crée un *paquet* JSON pour une période : feuilles (classe × ligne du
   bulletin), élèves et notes déjà connues. Le paquet est conservé en base
   (MobileGradePackage) et porte une signature.
2. L'application mobile « KIS Kalanso Notes » ouvre le paquet, l'enseignant
   saisit hors ligne puis renvoie un fichier *notes* JSON (WhatsApp, Bluetooth…).
3. Kalanso charge ce fichier (MobileGradeSubmission), contrôle chaque ligne,
   montre l'aperçu des changements, puis enregistre après validation.

Le format des deux fichiers est décrit dans docs/format_saisie_mobile.md.
"""
import json
import uuid
from dataclasses import dataclass, field

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (BulletinItem, BulletinItemResult, BulletinLock, Enrollment, Grade, MobileGradePackage,
                     MobileGradeSubmission, Teaching)

PACKAGE_FORMAT = "kis-kalanso-paquet"
NOTES_FORMAT = "kis-kalanso-notes"
VERSION = 1
MOBILE_SCHOOL_TYPES = {"fundamental_1", "fundamental_2", "high_school", "vocational"}
MAX_FILE_SIZE = 5 * 1024 * 1024
FIELDS_AB = [
    {"key": "class_average", "label": "Moyenne de classe (A)"},
    {"key": "composition", "label": "Composition (B)"},
]
FIELDS_SINGLE = [{"key": "note", "label": "Note"}]
_SALT = "kis-kalanso.mobile-grades"


class MobileImportError(Exception):
    """Fichier refusé ; le message est montré tel quel."""


def _signer():
    return signing.Signer(salt=_SALT)


def _student_label(student):
    return f"{student.last_name} {student.first_name}".strip()


# ---------------------------------------------------------------------------
# Export : paquet de saisie
# ---------------------------------------------------------------------------

@dataclass
class SheetPlan:
    """Une feuille = une classe et soit une matière, soit une ligne personnalisée du bulletin."""
    classe: object
    subject: object = None
    item: object = None

    @property
    def sheet_id(self):
        return f"{self.classe.id}-{self.subject.id}" if self.subject else f"{self.classe.id}-i{self.item.id}"

    @property
    def label(self):
        return self.subject.name if self.subject else _item_label(self.item)

    @property
    def single(self):
        """Fondamentale 1 : une seule note par élève."""
        return self.classe.education_level.school_type == "fundamental_1"

    @property
    def mode(self):
        return "single" if self.single else "ab"

    @property
    def scale(self):
        if self.item:
            return float(self.item.max_score)
        return 10.0 if self.single else 20.0

    @property
    def empty(self):
        return (None,) if self.single else (None, None)


def _item_label(item):
    return item.label or (item.subject.name if item.subject_id else "Élément")


def teacher_sheets(teacher, term):
    """Feuilles (classe × matière) que l'enseignant peut saisir pour la période.

    Retourne (feuilles, avertissements). Une matière n'est proposée que si elle
    figure dans le bulletin paramétré de la classe, comme pour la saisie à l'écran.
    """
    sheets, warnings = [], []
    teachings = (
        Teaching.objects.filter(teacher=teacher, classe__school_year=term.school_year)
        .select_related("classe__education_level", "subject")
        .order_by("classe__education_level__order", "classe__group", "classe__name", "subject__name")
    )
    seen = set()
    for teaching in teachings:
        classe = teaching.classe
        if classe.education_level.school_type not in MOBILE_SCHOOL_TYPES:
            continue
        bulletin = list(BulletinItem.objects.filter(classe=classe, is_active=True).select_related("subject").order_by("order", "id"))
        items = {item.subject_id: item.subject for item in bulletin if item.subject_id}
        if not bulletin:
            warnings.append(f"{classe.display_name} : bulletin non paramétré, classe ignorée.")
            continue
        subjects = [teaching.subject] if teaching.subject_id else list(items.values())
        for subject in subjects:
            if subject.id not in items:
                warnings.append(f"{classe.display_name} — {subject.name} : matière absente du bulletin, ignorée.")
                continue
            key = (classe.id, "s", subject.id)
            if key not in seen:
                seen.add(key)
                sheets.append(SheetPlan(classe, subject=subject))
        if not teaching.subject_id:
            # Même règle qu'à l'écran : les lignes personnalisées (Conduite…)
            # reviennent à l'enseignant affecté à toute la classe.
            for item in bulletin:
                key = (classe.id, "i", item.id)
                if item.subject_id is None and key not in seen:
                    seen.add(key)
                    sheets.append(SheetPlan(classe, item=item))
    return sheets, warnings


def class_sheets(classes, term):
    """Toutes les lignes du bulletin des classes choisies (paquet par classe)."""
    sheets, warnings = [], []
    for classe in classes:
        if classe.school_year_id != term.school_year_id or classe.education_level.school_type not in MOBILE_SCHOOL_TYPES:
            continue
        bulletin = list(BulletinItem.objects.filter(classe=classe, is_active=True).select_related("subject").order_by("order", "id"))
        if not bulletin:
            warnings.append(f"{classe.display_name} : bulletin non paramétré, classe ignorée.")
            continue
        for item in bulletin:
            sheets.append(SheetPlan(classe, subject=item.subject) if item.subject_id else SheetPlan(classe, item=item))
    return sheets, warnings


def mobile_classes(term):
    """Classes de l'année proposées pour un paquet par classe."""
    from pedagogie.models import Classe
    return list(
        Classe.objects.filter(school_year=term.school_year, education_level__school_type__in=MOBILE_SCHOOL_TYPES)
        .select_related("education_level", "pedagogical_track")
        .order_by("education_level__school_type", "education_level__order", "group", "name")
    )


def mobile_teachers(term):
    """Enseignants ayant au moins une affectation saisissable pour l'année de la période."""
    from administration.models import Teacher
    return (
        Teacher.objects.filter(
            teachings__classe__school_year=term.school_year,
            teachings__classe__education_level__school_type__in=MOBILE_SCHOOL_TYPES,
        ).distinct().order_by("last_name", "first_name")
    )


def _to_float(value):
    return None if value is None else float(value)


def _current_values(plan, term, enrollment_ids):
    """{inscription: valeurs} des notes du bulletin déjà enregistrées.

    Valeurs : (note,) en mode « single », (A, B) en mode « ab ».
    """
    if plan.subject:
        rows = Grade.objects.filter(enrollment_id__in=enrollment_ids, subject=plan.subject, term=term, evaluation__isnull=True)
        if plan.single:
            return {r.enrollment_id: (_to_float(r.composition),) for r in rows}
    else:
        rows = BulletinItemResult.objects.filter(enrollment_id__in=enrollment_ids, bulletin_item=plan.item, term=term)
        if plan.single:
            return {r.enrollment_id: (_to_float(r.note),) for r in rows}
    return {r.enrollment_id: (_to_float(r.class_average), _to_float(r.composition)) for r in rows}


def build_package(teacher, term, user=None, classes=None, label=""):
    """Paquet par enseignant (``teacher``) ou par classe (``classes``)."""
    if teacher is not None:
        sheets, warnings = teacher_sheets(teacher, term)
    else:
        sheets, warnings = class_sheets(classes or [], term)
        if not label:
            names = sorted({c.display_name for c in classes or []})
            label = ", ".join(names) if len(names) <= 3 else f"{len(names)} classes"
    if not sheets:
        raise MobileImportError("Aucune feuille de notes à saisir pour cette période. " + " ".join(warnings))
    uid = str(uuid.uuid4())
    school = term.school_year.school
    content = {
        "format": PACKAGE_FORMAT,
        "version": VERSION,
        "package_id": uid,
        "package_signature": _signer().sign(uid),
        "generated_at": timezone.now().isoformat(timespec="seconds"),
        "school": {"name": school.name, "code": school.code},
        "school_year": term.school_year.name,
        "term": {"id": term.id, "name": term.name},
        "scope": "teacher" if teacher is not None else "classes",
        "teacher": {"id": teacher.id, "name": teacher.full_name, "employee_number": teacher.employee_number} if teacher is not None else None,
        "label": teacher.full_name if teacher is not None else label,
        "sheets": [],
    }
    locked = []
    for plan in sheets:
        if BulletinLock.get_for(plan.classe.id, term.id):
            locked.append(plan.classe.display_name)
            continue
        enrollments = list(
            Enrollment.objects.filter(classe=plan.classe).select_related("student")
            .order_by("student__last_name", "student__first_name")
        )
        current = _current_values(plan, term, [e.id for e in enrollments])
        students = []
        for e in enrollments:
            line = {"enrollment_id": e.id, "matricule": e.student.matricule or "",
                    "last_name": e.student.last_name, "first_name": e.student.first_name}
            values = current.get(e.id, plan.empty)
            if plan.single:
                line["note"] = values[0]
            else:
                line["class_average"], line["composition"] = values
            students.append(line)
        sheet = {
            "sheet_id": plan.sheet_id,
            "kind": "subject" if plan.subject else "item",
            "mode": plan.mode,
            "classe": {"id": plan.classe.id, "name": plan.classe.display_name},
            "scale": plan.scale,
            "fields": FIELDS_SINGLE if plan.single else FIELDS_AB,
            "rule": "Une note par élève, ou laisser vide." if plan.single
                    else "Saisir les deux notes A et B ensemble, ou laisser les deux vides.",
            "students": students,
        }
        if plan.subject:
            sheet["subject"] = {"id": plan.subject.id, "name": plan.subject.name}
        else:
            sheet["subject"] = {"id": None, "name": plan.label}
            sheet["item"] = {"id": plan.item.id, "name": plan.label}
        content["sheets"].append(sheet)
    for name in sorted(set(locked)):
        warnings.append(f"{name} : bulletins verrouillés pour {term.name}, classe non envoyée.")
    if not content["sheets"]:
        raise MobileImportError("Aucune feuille à envoyer : " + " ".join(warnings))
    package = MobileGradePackage.objects.create(
        uid=uid, teacher=teacher, label=content["label"][:150], term=term, content=content,
        created_by=user if getattr(user, "pk", None) else None,
    )
    return package, warnings


def package_filename(package):
    def clean(text):
        return "".join(c if c.isalnum() else "_" for c in text).strip("_")
    return f"paquet_{clean(package.holder)[:60]}_{clean(package.term.name)}.json"


def package_json(package):
    return json.dumps(package.content, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------------------
# Import : fichier de notes
# ---------------------------------------------------------------------------

def read_submission(raw, filename="", user=None):
    """Contrôle d'en-tête puis enregistrement du dépôt (sans toucher aux notes)."""
    if len(raw) > MAX_FILE_SIZE:
        raise MobileImportError("Fichier trop volumineux pour un fichier de notes.")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise MobileImportError("Ce fichier n'est pas un fichier de notes KIS Kalanso (JSON illisible).")
    if not isinstance(data, dict):
        raise MobileImportError("Ce fichier n'est pas un fichier de notes KIS Kalanso.")
    if data.get("format") == PACKAGE_FORMAT:
        raise MobileImportError("Ce fichier est un paquet de saisie (envoyé à l'enseignant), pas un fichier de notes rempli.")
    if data.get("format") != NOTES_FORMAT:
        raise MobileImportError("Ce fichier n'est pas un fichier de notes KIS Kalanso.")
    if data.get("version") != VERSION:
        raise MobileImportError("Version du fichier non prise en charge. Mettez à jour l'application mobile ou KIS Kalanso.")
    uid = data.get("package_id")
    try:
        if _signer().unsign(str(data.get("package_signature") or "")) != uid:
            raise signing.BadSignature
    except signing.BadSignature:
        raise MobileImportError("Signature invalide : ce fichier ne provient pas d'un paquet créé par cet établissement.")
    package = MobileGradePackage.objects.filter(uid=uid).select_related("teacher", "term__school_year").first()
    if package is None:
        raise MobileImportError("Paquet inconnu dans cette installation de KIS Kalanso.")
    if not isinstance(data.get("sheets"), list):
        raise MobileImportError("Fichier incomplet : aucune feuille de notes.")
    return MobileGradeSubmission.objects.create(
        package=package, content=data, filename=filename[:255],
        imported_by=user if getattr(user, "pk", None) else None,
    )


def _number(value, scale):
    """None si vide ; float sinon. Lève ValueError pour une saisie invalide."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError
    number = float(str(value).replace(",", ".").strip())
    if number != number or number < 0 or number > scale:  # NaN ou hors barème
        raise ValueError
    return round(number, 2)


@dataclass
class Row:
    enrollment: object
    student: str
    old: tuple
    new: tuple
    status: str  # new, changed, same, empty, error
    message: str = ""


@dataclass
class SheetReport:
    title: str
    plan: object = None
    rows: list = field(default_factory=list)
    error: str = ""

    def count(self, status):
        return sum(1 for r in self.rows if r.status == status)

    @property
    def counts(self):
        return {s: self.count(s) for s in ("new", "changed", "same", "empty", "error")}


@dataclass
class Report:
    errors: list = field(default_factory=list)
    sheets: list = field(default_factory=list)

    @property
    def to_apply(self):
        return sum(s.count("new") + s.count("changed") for s in self.sheets if not s.error)

    @property
    def line_errors(self):
        return sum(s.count("error") for s in self.sheets) + sum(1 for s in self.sheets if s.error)


def analyse(submission):
    """Compare le fichier reçu aux notes actuelles, sans rien enregistrer."""
    from pedagogie.models import Classe, Subject

    package = submission.package
    term = package.term
    report = Report()
    if term.school_year.is_closed:
        report.errors.append(f"L'année {term.school_year.name} est clôturée : les notes ne peuvent plus être modifiées.")
        return report
    planned = {s["sheet_id"]: s for s in package.content.get("sheets", [])}
    seen_sheets = set()
    for sent in submission.content.get("sheets", []):
        sheet_id = str(sent.get("sheet_id", "")) if isinstance(sent, dict) else ""
        plan = planned.get(sheet_id)
        if plan is None:
            report.sheets.append(SheetReport(title=f"Feuille « {sheet_id or '?'} »", error="Feuille absente du paquet d'origine : ignorée."))
            continue
        if sheet_id in seen_sheets:
            report.sheets.append(SheetReport(title=f"{plan['classe']['name']} — {plan['subject']['name']}", error="Feuille présente deux fois dans le fichier : la seconde est ignorée."))
            continue
        seen_sheets.add(sheet_id)
        sheet = SheetReport(title=f"{plan['classe']['name']} — {plan['subject']['name']}")
        report.sheets.append(sheet)
        classe = Classe.objects.filter(pk=plan["classe"]["id"]).select_related("education_level").first()
        if plan.get("kind") == "item":
            item = BulletinItem.objects.filter(pk=plan["item"]["id"], classe=classe, is_active=True, subject__isnull=True).first() if classe else None
            target = SheetPlan(classe, item=item) if item else None
        else:
            subject = Subject.objects.filter(pk=plan["subject"]["id"]).first()
            target = SheetPlan(classe, subject=subject) if classe and subject else None
        if target is None:
            sheet.error = "Classe, matière ou ligne du bulletin supprimée depuis l'envoi du paquet."
            continue
        sheet.plan = target
        if BulletinLock.get_for(classe.id, term.id):
            sheet.error = f"Bulletins verrouillés pour {term.name} : aucune note de cette classe ne peut être modifiée."
            continue
        if package.teacher_id:
            teachings = Teaching.objects.filter(teacher=package.teacher, classe=classe)
            assigned = teachings.filter(subject__isnull=True).exists() or (target.subject and teachings.filter(subject=target.subject).exists())
            if not assigned:
                sheet.error = f"{package.teacher.full_name} n'est plus affecté(e) à cette classe pour cette matière."
                continue
        allowed = {s["enrollment_id"] for s in plan["students"]}
        enrollments = {
            e.id: e for e in Enrollment.objects.filter(classe=classe, id__in=allowed).select_related("student")
        }
        current = _current_values(target, term, list(enrollments))
        scale = target.scale
        keys = ("note",) if target.single else ("class_average", "composition")
        empty = target.empty
        done = set()
        for line in sent.get("grades") or []:
            if not isinstance(line, dict):
                continue
            eid = line.get("enrollment_id")
            enrollment = enrollments.get(eid)
            if enrollment is None:
                sheet.rows.append(Row(None, f"Inscription n° {eid}", empty, empty, "error",
                                      "Élève absent du paquet ou retiré de la classe."))
                continue
            if eid in done:
                continue
            done.add(eid)
            label = _student_label(enrollment.student)
            exists = eid in current
            old = current.get(eid, empty)
            try:
                new = tuple(_number(line.get(k), scale) for k in keys)
            except (TypeError, ValueError):
                sheet.rows.append(Row(enrollment, label, old, tuple(line.get(k) for k in keys), "error",
                                      f"Note invalide : chaque note doit être comprise entre 0 et {scale:g}."))
                continue
            if new == empty:
                sheet.rows.append(Row(enrollment, label, old, new, "empty", "Aucune note saisie : note actuelle conservée." if exists else ""))
            elif None in new:
                sheet.rows.append(Row(enrollment, label, old, new, "error", "A et B doivent être saisis ensemble."))
            elif old == new:
                sheet.rows.append(Row(enrollment, label, old, new, "same"))
            else:
                sheet.rows.append(Row(enrollment, label, old, new, "changed" if exists else "new"))
    if not report.sheets:
        report.errors.append("Le fichier ne contient aucune feuille de notes.")
    return report


def apply(submission, user=None):
    """Enregistre les lignes valides (nouvelles ou modifiées). Retourne le nombre de notes écrites."""
    try:
        return _apply(submission)
    except ValidationError as exc:
        raise MobileImportError(" ".join(exc.messages))


@transaction.atomic
def _apply(submission):
    submission = MobileGradeSubmission.objects.select_for_update().get(pk=submission.pk)
    if submission.status != MobileGradeSubmission.Status.PENDING:
        raise MobileImportError("Ce dépôt a déjà été traité.")
    report = analyse(submission)
    if report.errors:
        raise MobileImportError(" ".join(report.errors))
    term = submission.package.term
    written = 0
    for sheet in report.sheets:
        if sheet.error:
            continue
        for row in sheet.rows:
            if row.status not in ("new", "changed"):
                continue
            plan = sheet.plan
            if plan.subject:
                grade = Grade.objects.filter(enrollment=row.enrollment, subject=plan.subject, term=term, evaluation__isnull=True).first()
                grade = grade or Grade(enrollment=row.enrollment, subject=plan.subject, term=term)
                if plan.single:
                    grade.class_average, grade.composition = None, row.new[0]
                else:
                    grade.class_average, grade.composition = row.new
                grade.full_clean(exclude=["enrollment", "subject", "term", "evaluation"])
                grade.save()
            else:
                result = BulletinItemResult.objects.filter(enrollment=row.enrollment, bulletin_item=plan.item, term=term).first()
                result = result or BulletinItemResult(enrollment=row.enrollment, bulletin_item=plan.item, term=term)
                if plan.single:
                    result.note, result.class_average, result.composition = row.new[0], None, None
                else:
                    result.note = None
                    result.class_average, result.composition = row.new
                result.save()
            written += 1
    submission.status = MobileGradeSubmission.Status.APPLIED
    submission.applied_at = timezone.now()
    submission.applied_count = written
    submission.save(update_fields=["status", "applied_at", "applied_count"])
    return written
