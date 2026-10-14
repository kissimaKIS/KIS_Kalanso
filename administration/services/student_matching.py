"""Reconnaître un même élève malgré des fiches incomplètes (import Excel, doublons).

Règles (retours du 07/10) :
- même matricule : même élève ;
- même nom et prénom, ou nom proche (« Alimamy » / « Almamy »), appuyé par un
  indice commun (téléphone d'un parent, nom du père ou de la mère, date de
  naissance) et sans contradiction : même élève probable ;
- des informations contradictoires (deux dates de naissance, deux matricules)
  ne sont jamais tranchées automatiquement.
"""
import difflib
import re
import unicodedata

COMPLETABLE_FIELDS = [
    "sex", "date_of_birth", "place_of_birth", "recruitment_year", "matricule", "father_name", "mother_name",
    "father_phone", "mother_phone", "whatsapp_phone", "contact_name", "contact_phone", "contact_relation",
]
FIELD_LABELS = {
    "first_name": "Prénom", "last_name": "Nom", "sex": "Sexe", "date_of_birth": "Date de naissance",
    "place_of_birth": "Lieu de naissance", "matricule": "Matricule", "father_name": "Père",
    "mother_name": "Mère", "father_phone": "Tél. père", "mother_phone": "Tél. mère", "whatsapp_phone": "WhatsApp",
    "recruitment_year": "Année de recrutement", "contact_name": "Personne de contact",
    "contact_phone": "Tél. contact", "contact_relation": "Lien de parenté",
}
PHONE_FIELDS = ("father_phone", "mother_phone", "whatsapp_phone", "contact_phone")
NAME_FIELDS = ("father_name", "mother_name", "place_of_birth", "contact_name", "contact_relation")


def norm(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def phone(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("223") and len(digits) > 8:
        digits = digits[3:]
    return digits if len(digits) >= 8 else ""


def _get(obj, field):
    return obj.get(field) if isinstance(obj, dict) else getattr(obj, field, None)


def comparable(field, value):
    if value in (None, ""):
        return None
    if field in PHONE_FIELDS:
        return phone(value) or None
    if field in ("date_of_birth", "recruitment_year"):
        return value
    if field == "sex":
        return str(value).upper()[:1]
    return norm(value) or None


def similar(a, b, threshold=0.8):
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    if a == b:
        return True
    if a.split(" ")[0] == b.split(" ")[0] and (a.startswith(b) or b.startswith(a)):
        return True  # « Adama F » / « Adama Fousseyni »
    return difflib.SequenceMatcher(None, a, b).ratio() >= threshold


def same_name(a, b):
    return norm(_get(a, "first_name")) == norm(_get(b, "first_name")) and norm(_get(a, "last_name")) == norm(_get(b, "last_name"))


def close_name(a, b):
    return similar(_get(a, "last_name"), _get(b, "last_name"), 0.85) and similar(_get(a, "first_name"), _get(b, "first_name"))


def common_clues(a, b):
    """Indices partagés : téléphones, noms des parents, date de naissance."""
    clues = []
    phones_a = {phone(_get(a, f)) for f in PHONE_FIELDS} - {""}
    phones_b = {phone(_get(b, f)) for f in PHONE_FIELDS} - {""}
    if phones_a & phones_b:
        clues.append("même téléphone de parent")
    for field, label in (("father_name", "même père"), ("mother_name", "même mère")):
        va, vb = comparable(field, _get(a, field)), comparable(field, _get(b, field))
        if va and va == vb:
            clues.append(label)
    if _get(a, "date_of_birth") and _get(a, "date_of_birth") == _get(b, "date_of_birth"):
        clues.append("même date de naissance")
    return clues


def conflicts(a, b, fields=COMPLETABLE_FIELDS):
    """Champs remplis des deux côtés avec des valeurs différentes."""
    found = []
    for field in fields:
        va, vb = comparable(field, _get(a, field)), comparable(field, _get(b, field))
        if va is not None and vb is not None and va != vb:
            found.append(field)
    return found


def hard_conflicts(a, b):
    """Contradictions qui empêchent de conclure seul : date de naissance, matricule, sexe."""
    return [f for f in conflicts(a, b, ("date_of_birth", "matricule", "sex"))]


def fillable(student, data):
    """Champs vides de la fiche que le fichier peut compléter."""
    return [f for f in COMPLETABLE_FIELDS
            if comparable(f, getattr(student, f, None)) is None and comparable(f, data.get(f)) is not None]


def find_duplicates(students=None):
    """Paires de fiches probablement identiques dans la base, triées de la plus sûre à la moins sûre."""
    from pedagogie.models import Student

    students = list(students if students is not None else Student.objects.all())
    by_last = {}
    for s in students:
        key = norm(s.last_name)[:4]
        by_last.setdefault(key, []).append(s)
    pairs = []
    for group in by_last.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if not close_name(a, b):
                    continue
                if hard_conflicts(a, b):
                    continue
                clues = common_clues(a, b)
                exact = same_name(a, b)
                if not clues and not exact:
                    continue
                reasons = (["nom identique"] if exact else ["nom proche"]) + clues
                score = len(clues) * 2 + (1 if exact else 0)
                keep, drop = sorted((a, b), key=lambda s: (-completeness(s), s.pk))
                pairs.append({"keep": keep, "drop": drop, "reasons": reasons, "score": score,
                              "sure": bool(clues)})
    pairs.sort(key=lambda p: (-p["score"], norm(p["keep"].last_name), norm(p["keep"].first_name)))
    return pairs


def completeness(student):
    filled = sum(1 for f in COMPLETABLE_FIELDS if comparable(f, getattr(student, f, None)) is not None)
    return filled + (1 if student.photo else 0)
