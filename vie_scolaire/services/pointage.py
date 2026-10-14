"""Pointage par QR code (retours V8-8).

Circuit
-------
1. KIS prépare un **paquet de pointage** (liste des personnes et de leur code,
   adresse du serveur et clé) : fichier à envoyer au téléphone, ou chargé
   directement par le téléphone sur le réseau local.
2. Le téléphone scanne **hors connexion** : badges du personnel (entrée ou
   sortie) et cartes d'identité des élèves (présence). Chaque passage reçoit un
   numéro unique sur le téléphone.
3. Synchronisation : envoi direct au serveur sur le réseau local, ou fichier
   « relevé » chargé dans KIS. Un même passage envoyé deux fois n'est compté
   qu'une fois (téléphone + numéro).

Effets
------
- Personnel (enseignants et autre personnel) : la présence du jour est créée
  ou complétée — heure d'entrée = premier passage « entrée », heure de sortie
  = dernier passage « sortie ». Retard si une heure d'arrivée est réglée.
- Élèves : présence du jour (« Présent ») si aucune présence n'est encore
  enregistrée pour ce jour.

Codes reconnus
--------------
- ``KIS-ENS-<matricule>`` : badge d'un enseignant ;
- ``KIS-PER-<matricule>`` : badge d'un autre membre du personnel ;
- ``KIS-ELV-<n°>`` : carte d'un élève sans matricule ;
- sinon, la première ligne du QR de la carte d'identité élève : son matricule.
"""
import datetime
import json

from django.db import IntegrityError, transaction
from django.utils import timezone

from administration.models import OtherPersonnel, SchoolYear, Teacher
from pedagogie.models import Enrollment, Student
from vie_scolaire.models import Attendance, OtherPersonnelAttendance, PointageConfig, PointageScan, TeacherAttendance

PACKAGE_FORMAT = "kis-pointage-paquet"
EXPORT_FORMAT = "kis-pointage-releve"
VERSION = 1


def teacher_code(teacher):
    return f"KIS-ENS-{teacher.employee_number}"


def personnel_code(person):
    return f"KIS-PER-{person.employee_number}"


def student_code(student):
    return student.matricule or f"KIS-ELV-{student.pk}"


def resolve(code):
    """(type, objet) pour un code lu ; (UNKNOWN, None) s'il n'est pas reconnu."""
    text = (code or "").strip()
    first = text.splitlines()[0].strip() if text else ""
    upper = first.upper()
    if upper.startswith("KIS-ENS-"):
        teacher = Teacher.objects.filter(employee_number__iexact=first[8:]).first()
        return (PointageScan.Person.TEACHER, teacher) if teacher else (PointageScan.Person.UNKNOWN, None)
    if upper.startswith("KIS-PER-"):
        person = OtherPersonnel.objects.filter(employee_number__iexact=first[8:]).first()
        return (PointageScan.Person.STAFF, person) if person else (PointageScan.Person.UNKNOWN, None)
    if upper.startswith("KIS-ELV-") and first[8:].isdigit():
        student = Student.objects.filter(pk=int(first[8:])).first()
        return (PointageScan.Person.STUDENT, student) if student else (PointageScan.Person.UNKNOWN, None)
    if first and first != "-":
        student = Student.objects.filter(matricule__iexact=first).first()
        if student:
            return PointageScan.Person.STUDENT, student
    return PointageScan.Person.UNKNOWN, None


# ---------------------------------------------------------------- paquet
def build_package(school, server_urls=()):
    """Liste des personnes à reconnaître sur le téléphone (année active)."""
    config = PointageConfig.get()
    year = SchoolYear.objects.filter(is_active=True).first()
    people = []
    for t in Teacher.objects.filter(is_active=True).order_by("last_name", "first_name"):
        people.append({"code": teacher_code(t), "name": f"{t.last_name} {t.first_name}".strip(), "type": "teacher",
                       "detail": "Enseignant"})
    for p in OtherPersonnel.objects.filter(is_active=True).order_by("last_name", "first_name"):
        people.append({"code": personnel_code(p), "name": f"{p.last_name} {p.first_name}".strip(), "type": "staff",
                       "detail": p.function})
    if year:
        for e in (Enrollment.objects.filter(school_year=year).select_related("student", "classe")
                  .order_by("classe__name", "student__last_name", "student__first_name")):
            people.append({"code": student_code(e.student), "name": f"{e.student.last_name} {e.student.first_name}",
                           "type": "student", "detail": e.classe.display_name})
    return {
        "format": PACKAGE_FORMAT, "version": VERSION,
        "school": {"name": school.name if school else ""},
        "school_year": year.name if year else "",
        "generated_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M:%S"),
        "server": {"urls": list(server_urls), "key": config.api_key},
        "people": people,
    }


# ---------------------------------------------------------------- application des passages
def _year_for(day):
    return (SchoolYear.objects.filter(start_date__lte=day, end_date__gte=day, is_archive=False).order_by("-is_active").first()
            or SchoolYear.objects.filter(is_active=True).first())


def _late_minutes(entry, start):
    if not entry or not start or entry <= start:
        return None
    delta = datetime.datetime.combine(datetime.date.today(), entry) - datetime.datetime.combine(datetime.date.today(), start)
    return max(1, int(delta.total_seconds() // 60))


def _apply_staff(model, field, person, scan, when, config):
    year = _year_for(when.date())
    if not year:
        return "aucune année scolaire pour cette date"
    record, _ = model.objects.get_or_create(**{field: person}, school_year=year, date=when.date(),
                                            defaults={"status": "PRESENT"})
    moment = when.time().replace(microsecond=0)
    if scan.kind == PointageScan.Kind.IN:
        if record.entry_time is None or moment < record.entry_time:
            record.entry_time = moment
    else:
        if record.exit_time is None or moment > record.exit_time:
            record.exit_time = moment
    if record.entry_time and record.exit_time and record.exit_time < record.entry_time:
        record.exit_time = None                     # sortie antérieure à l'entrée : passage incohérent ignoré
    late = _late_minutes(record.entry_time, config.staff_start_time)
    record.status, record.late_minutes = ("LATE", late) if late else ("PRESENT", None)
    record.save()
    return f"{scan.get_kind_display().lower()} à {moment:%H:%M}"


def _apply_student(student, when):
    enrollment = (Enrollment.objects.filter(student=student, school_year__start_date__lte=when.date(),
                                            school_year__end_date__gte=when.date())
                  .select_related("school_year").first())
    if not enrollment:
        return "élève non inscrit à cette date"
    if Attendance.objects.filter(enrollment=enrollment, date=when.date()).exists():
        return "présence déjà enregistrée"
    Attendance.objects.create(enrollment=enrollment, date=when.date(), status="PRESENT", note="Pointage QR")
    return "présent"


def _parse_when(raw):
    when = datetime.datetime.fromisoformat(str(raw)[:19])
    if timezone.is_naive(when):
        when = timezone.make_aware(when)
    return timezone.localtime(when)


def apply_export(data):
    """Applique un relevé envoyé par un téléphone. Retourne un résumé."""
    if not isinstance(data, dict) or data.get("format") != EXPORT_FORMAT:
        raise ValueError("Ce fichier n'est pas un relevé de pointage KIS Kalanso.")
    device = str(data.get("device_id") or "")[:64]
    if not device:
        raise ValueError("Relevé incomplet : téléphone non identifié.")
    config = PointageConfig.get()
    summary = {"received": 0, "applied": 0, "duplicates": 0, "unknown": 0, "errors": 0, "unknown_codes": []}
    for item in data.get("scans") or []:
        summary["received"] += 1
        try:
            scan_id = str(item["id"])[:64]
            code = str(item["code"])[:255]
            when = _parse_when(item["at"])
            kind = PointageScan.Kind.OUT if str(item.get("kind")).upper() == "OUT" else PointageScan.Kind.IN
        except (KeyError, TypeError, ValueError):
            summary["errors"] += 1
            continue
        if PointageScan.objects.filter(device_id=device, scan_id=scan_id).exists():
            summary["duplicates"] += 1
            continue
        person_type, person = resolve(code)
        scan = PointageScan(device_id=device, scan_id=scan_id, code=code, kind=kind, scanned_at=when, person_type=person_type)
        try:
            with transaction.atomic():
                if person_type == PointageScan.Person.TEACHER:
                    scan.teacher = person
                    scan.result = _apply_staff(TeacherAttendance, "teacher", person, scan, when, config)
                elif person_type == PointageScan.Person.STAFF:
                    scan.personnel = person
                    scan.result = _apply_staff(OtherPersonnelAttendance, "personnel", person, scan, when, config)
                elif person_type == PointageScan.Person.STUDENT:
                    scan.student = person
                    scan.result = _apply_student(person, when)
                else:
                    scan.result = "badge inconnu"
                scan.save()
        except IntegrityError:
            summary["duplicates"] += 1
            continue
        except Exception as exc:              # un passage illisible n'empêche pas les autres
            summary["errors"] += 1
            PointageScan.objects.get_or_create(device_id=device, scan_id=scan_id, defaults={
                "code": code, "kind": kind, "scanned_at": when, "result": f"erreur : {exc}"[:255]})
            continue
        if person_type == PointageScan.Person.UNKNOWN:
            summary["unknown"] += 1
            summary["unknown_codes"].append(code.splitlines()[0][:40] if code else "")
        else:
            summary["applied"] += 1
    return summary


def summary_text(summary):
    parts = [f"{summary['applied']} passage(s) enregistré(s)"]
    if summary["duplicates"]:
        parts.append(f"{summary['duplicates']} déjà reçu(s)")
    if summary["unknown"]:
        parts.append(f"{summary['unknown']} badge(s) inconnu(s)")
    if summary["errors"]:
        parts.append(f"{summary['errors']} illisible(s)")
    return ", ".join(parts) + "."


def load_json(raw):
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8-sig")
    return json.loads(raw)
