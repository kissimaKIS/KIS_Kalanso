"""Outils communs aux imports Excel (élèves, enseignants, personnel, budget).

- lecture du fichier avec un message clair si ce n'est pas un Excel lisible ;
- reconnaissance des en-têtes sans tenir compte des accents, majuscules et
  espaces (« Prénom », « PRENOM », « prenom » sont la même colonne) ;
- refus d'un fichier qui ressemble à un autre type de liste (un fichier
  d'élèves dans l'import du personnel, par exemple) ;
- liste précise des colonnes obligatoires manquantes.
"""
import unicodedata


class ImportFileError(Exception):
    """Fichier refusé en entier ; le message est montré tel quel."""


# Colonnes caractéristiques de chaque type de fichier → ce qu'elles trahissent.
_STUDENT = {"pere", "mere", "telpere", "telmere", "whatsapp", "lieu", "lieudenaissance", "sexe"}
_TEACHER = {"profil", "specialite", "diplome"}
_PERSONNEL = {"fonction"}
_STAFF = {"statut", "salairemensuel", "tauxhoraire", "daterecrutement"}  # enseignants et autre personnel
_BUDGET = {"montant", "libelle", "categorie"}
_PEOPLE = {"prenom", "matricule"}

LOOKS_LIKE = [
    (_STUDENT, "une liste d'élèves"),
    (_PERSONNEL, "une liste du personnel non enseignant"),
    (_TEACHER, "une liste d'enseignants"),
    (_STAFF, "une liste du personnel (enseignants ou autre personnel)"),
    (_BUDGET, "un tableau de recettes et dépenses (budget)"),
    (_PEOPLE, "une liste de personnes (élèves ou personnel)"),
]

# Colonnes interdites dans chaque import : leur présence signale un mauvais fichier.
FORBIDDEN = {
    "students": _PERSONNEL | _TEACHER | _STAFF | _BUDGET,
    "teachers": _STUDENT | _PERSONNEL | _BUDGET,
    "personnel": _STUDENT | _TEACHER | _BUDGET,
    "budget": _STUDENT | _PERSONNEL | _TEACHER | _STAFF | _PEOPLE,
}

IMPORT_LABELS = {
    "students": "l'import des élèves",
    "teachers": "l'import des enseignants",
    "personnel": "l'import du personnel non enseignant",
    "budget": "l'import du budget",
}


def header_key(text):
    """« Prénom » → « prenom », « Tel Père » → « telpere »."""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii").lower()
    return "".join(c for c in text if c.isalnum())


def read_excel(uploaded):
    import pandas as pd

    name = getattr(uploaded, "name", "") or ""
    if name and not name.lower().endswith((".xlsx", ".xlsm", ".xls")):
        raise ImportFileError(f"« {name} » n'est pas un fichier Excel. Enregistrez votre tableau au format .xlsx puis réessayez.")
    try:
        df = pd.read_excel(uploaded)
    except Exception:
        raise ImportFileError(
            f"Le fichier « {name or 'choisi'} » n'a pas pu être lu comme un fichier Excel. "
            "Vérifiez qu'il n'est pas protégé par un mot de passe ni endommagé, et qu'il est au format .xlsx."
        )
    df = df.dropna(how="all")
    if df.empty:
        raise ImportFileError("Le fichier ne contient aucune ligne de données sous la ligne des titres.")
    return df


def prepare(df, expected, aliases, required):
    """Renomme les colonnes, vérifie le type de fichier et les colonnes obligatoires.

    ``aliases`` : {titre Excel : nom interne} ; ``required`` : noms internes obligatoires.
    """
    by_key = {header_key(title): internal for title, internal in aliases.items()}
    wrong = [c for c in df.columns if header_key(c) in FORBIDDEN[expected]]
    if wrong:
        keys = {header_key(c) for c in wrong}
        looks = next((label for markers, label in LOOKS_LIKE if keys & markers), "un autre type de fichier")
        raise ImportFileError(
            f"Ce fichier ressemble à {looks} (colonnes : {', '.join(str(c) for c in wrong)}). "
            f"Vous êtes dans {IMPORT_LABELS[expected]} : rien n'a été importé. "
            "Choisissez le bon fichier, ou utilisez le menu d'import correspondant."
        )
    df = df.rename(columns={c: by_key.get(header_key(c), c) for c in df.columns})
    missing = [title for title, internal in _titles(aliases, required) if internal not in df.columns]
    if missing:
        raise ImportFileError(
            "Colonnes obligatoires manquantes : " + ", ".join(missing)
            + ". Colonnes trouvées dans le fichier : " + (", ".join(str(c) for c in df.columns[:12]) or "aucune") + "."
        )
    return df


def _titles(aliases, required):
    seen = {}
    for title, internal in aliases.items():
        if internal in required and internal not in seen:
            seen[internal] = title
    return [(seen[r], r) for r in required if r in seen]


def summary(parts, errors, max_errors=5):
    """Message de fin d'import : « 3 créés, 2 déjà présents… » puis les premières erreurs."""
    text = ", ".join(p for p in parts if p) or "Aucune ligne importée"
    if errors:
        text += f". {len(errors)} ligne(s) ignorée(s) : " + " | ".join(errors[:max_errors]) + (" …" if len(errors) > max_errors else "")
    return text + "."


def check_matricules(df, column, expected):
    """Second contrôle quand les colonnes ne suffisent pas (Matricule, Prénom, Nom
    existent partout) : si la majorité des matricules du fichier appartiennent
    déjà à l'autre catégorie (élèves ↔ personnel), le fichier est refusé."""
    from administration.models import OtherPersonnel, Teacher
    from pedagogie.models import Student

    if column not in df.columns:
        return
    values = set()
    for v in df[column].tolist():
        if v is None or (isinstance(v, float) and v != v):
            continue
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        text = str(v).strip()
        if text and text.lower() != "nan":
            values.add(text)
    if not values:
        return
    if expected == "students":
        other = set(Teacher.objects.filter(employee_number__in=values).values_list("employee_number", flat=True))
        other |= set(OtherPersonnel.objects.filter(employee_number__in=values).values_list("employee_number", flat=True))
        own = set(Student.objects.filter(matricule__in=values).values_list("matricule", flat=True))
        looks = "une liste du personnel"
    else:
        other = set(Student.objects.filter(matricule__in=values).values_list("matricule", flat=True))
        model = Teacher if expected == "teachers" else OtherPersonnel
        own = set(model.objects.filter(employee_number__in=values).values_list("employee_number", flat=True))
        looks = "une liste d'élèves"
    if other and len(other) > len(own) and len(other) * 2 >= len(values):
        sample = ", ".join(sorted(other)[:5])
        raise ImportFileError(
            f"Ce fichier ressemble à {looks} : {len(other)} matricule(s) sur {len(values)} y sont déjà enregistrés "
            f"(ex. {sample}). Vous êtes dans {IMPORT_LABELS[expected]} : rien n'a été importé."
        )
