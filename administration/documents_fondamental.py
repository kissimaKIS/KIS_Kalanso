"""Documents officiels de l'école fondamentale (modèles fournis par l'école).

- Fiche scolaire : parcours complet de l'élève de la 1re à la 9e année ;
- Relevé de notes : moyennes de chaque période d'une année scolaire ;
- Certificat de transfert : départ de l'élève vers un autre établissement.

Règle commune : toute donnée que l'application ne connaît pas (pièce d'état
civil, profession des parents, préfecture, motif du transfert…) est laissée
en pointillés pour être complétée à la main. Chaque document est produit pour
n'importe quelle année, y compris une année clôturée.
"""
from dataclasses import dataclass, field
from io import BytesIO
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FUNDAMENTAL_TYPES = {"fundamental_1", "fundamental_2"}
FIRST_CYCLE = ["F1-1", "F1-2", "F1-3", "F1-4", "F1-5", "F1-6"]
SECOND_CYCLE = ["F2-7", "F2-8", "F2-9"]
CYCLE_LABELS = {
    "F1-1": "1<super>ère</super> Année", "F1-2": "2<super>ème</super> Année", "F1-3": "3<super>ème</super> Année",
    "F1-4": "4<super>ème</super> Année", "F1-5": "5<super>ème</super> Année", "F1-6": "6<super>ème</super> Année",
    "F2-7": "7<super>ème</super> Année", "F2-8": "8<super>ème</super> Année", "F2-9": "9<super>ème</super> Année",
}
DECISION_WORDING = {"PASSANT": "Passe en classe supérieure", "REDOUBLANT": "Redouble", "EXCLU": "Exclu(e)"}
INK = colors.HexColor("#1f2a44")


def is_fundamental(enrollment):
    level = enrollment.classe.education_level
    return bool(level and level.school_type in FUNDAMENTAL_TYPES)


# ---------------------------------------------------------------------------
# Données (calculées séparément du rendu pour être testées)
# ---------------------------------------------------------------------------

def school_enrollments(student, school):
    return list(
        student.enrollments.filter(school_year__school=school)
        .select_related("classe__education_level", "school_year")
        .order_by("school_year__start_date", "id")
    )


def doubled_levels(enrollments):
    """Niveaux suivis plus d'une fois dans l'établissement (d'après l'application)."""
    seen, doubled = set(), []
    for e in enrollments:
        level = e.classe.education_level
        if level.id in seen and level.name not in doubled:
            doubled.append(level.name)
        seen.add(level.id)
    return doubled


def _level_scale(enrollment):
    return 10 if enrollment.classe.education_level.school_type == "fundamental_1" else 20


def term_results(enrollment):
    """[(période, moyenne ou None, appréciation)] pour chaque période de l'année."""
    from pedagogie.bulletin_appreciations import appreciation_for
    from pedagogie.models import BulletinItemResult, Grade, Term
    from pedagogie.utils import moyenne_generale

    scale = _level_scale(enrollment)
    rows = []
    for term in Term.objects.filter(school_year=enrollment.school_year).order_by("order", "id"):
        has_data = (
            Grade.objects.filter(enrollment=enrollment, term=term, evaluation__isnull=True, composition__isnull=False).exists()
            or BulletinItemResult.objects.filter(enrollment=enrollment, term=term).exists()
        )
        if not has_data:
            rows.append((term, None, ""))
            continue
        value = round(float(moyenne_generale(enrollment, term)), 2)
        rows.append((term, value, appreciation_for(value, scale)))
    return rows


def council_decision(enrollment):
    """Décision de passage connue pour cette inscription (la plus avancée), sinon None."""
    line = getattr(enrollment, "passage_decision_line", None)
    if line is None:
        from pedagogie.models import PassageDecisionLine
        line = PassageDecisionLine.objects.filter(enrollment=enrollment).first()
    if not line:
        return None
    for decision in (line.director_decision, line.cap_decision, line.proposal_decision):
        if decision and decision != "PENDING":
            return decision
    return None


def decision_text(enrollment):
    decision = council_decision(enrollment)
    if not decision:
        return ""
    text = DECISION_WORDING.get(decision, decision)
    if decision == "REDOUBLANT":
        text = f"Redouble la {enrollment.classe.display_name}"
    return text


def class_teacher_name(enrollment):
    from pedagogie.models import ClassTeacher
    ct = ClassTeacher.objects.filter(classe=enrollment.classe).select_related("teacher").first()
    return ct.teacher.full_name if ct else ""


@dataclass
class ReleveData:
    rows: list
    scale: int
    total: float = None
    moyenne: float = None
    total_max: int = 0
    decision: str = ""
    teacher: str = ""


def releve_data(enrollment):
    rows = term_results(enrollment)
    scale = _level_scale(enrollment)
    data = ReleveData(rows=rows, scale=scale, total_max=scale * len(rows),
                      decision=decision_text(enrollment), teacher=class_teacher_name(enrollment))
    values = [value for _, value, _ in rows]
    if values and all(v is not None for v in values):
        data.total = round(sum(values), 2)
        data.moyenne = round(data.total / len(values), 2)
    return data


@dataclass
class FicheData:
    first_cycle: dict = field(default_factory=dict)
    second_cycle: dict = field(default_factory=dict)
    recruitment_date: object = None
    doubled: list = field(default_factory=list)
    def_classe: str = ""


def fiche_data(student, school):
    enrollments = school_enrollments(student, school)
    data = FicheData(doubled=doubled_levels(enrollments))
    if enrollments:
        data.recruitment_date = enrollments[0].enrollment_date
    for e in enrollments:
        code = e.classe.education_level.code
        if code in FIRST_CYCLE:
            data.first_cycle[code] = e  # la dernière inscription du niveau l'emporte
        elif code in SECOND_CYCLE:
            data.second_cycle[code] = e
            if code == "F2-9":
                data.def_classe = e.classe.display_name
    return data


@dataclass
class TransfertData:
    since: object = None
    until: object = None
    years: int = 0
    doubled: list = field(default_factory=list)
    work: str = ""
    decision: str = ""


def transfert_data(enrollment):
    from pedagogie.bulletin_appreciations import appreciation_for

    school = enrollment.school_year.school
    enrollments = [e for e in school_enrollments(enrollment.student, school)
                   if e.school_year.start_date <= enrollment.school_year.start_date]
    data = TransfertData(doubled=doubled_levels(enrollments))
    data.since = enrollments[0].enrollment_date if enrollments else enrollment.enrollment_date
    data.years = len({e.school_year_id for e in enrollments})
    if enrollment.school_year.is_closed:
        data.until = enrollment.school_year.end_date
    releve = releve_data(enrollment)
    if releve.moyenne is not None:
        data.work = appreciation_for(releve.moyenne, releve.scale)
    data.decision = decision_text(enrollment)
    return data


# ---------------------------------------------------------------------------
# Rendu
# ---------------------------------------------------------------------------

def _styles():
    base = getSampleStyleSheet()["Normal"]
    return {
        "head": ParagraphStyle("DFHead", parent=base, fontName="Helvetica", fontSize=9, leading=11, textColor=INK),
        "head_c": ParagraphStyle("DFHeadC", parent=base, fontName="Helvetica", fontSize=9, leading=11, alignment=TA_CENTER, textColor=INK),
        "stars": ParagraphStyle("DFStars", parent=base, fontSize=7, leading=8, textColor=INK),
        "title": ParagraphStyle("DFTitle", parent=base, fontName="Helvetica-Bold", fontSize=16, leading=20, alignment=TA_CENTER, textColor=INK),
        "section": ParagraphStyle("DFSection", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=14, alignment=TA_CENTER, textColor=INK),
        "label": ParagraphStyle("DFLabel", parent=base, fontName="Helvetica", fontSize=10, leading=12, textColor=INK),
        "value": ParagraphStyle("DFValue", parent=base, fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=colors.black),
        "cell": ParagraphStyle("DFCell", parent=base, fontName="Helvetica", fontSize=8.5, leading=10, textColor=INK),
        "cell_b": ParagraphStyle("DFCellB", parent=base, fontName="Helvetica-Bold", fontSize=8.5, leading=10, textColor=INK),
        "cell_c": ParagraphStyle("DFCellC", parent=base, fontName="Helvetica", fontSize=8.5, leading=10, alignment=TA_CENTER, textColor=INK),
        "small": ParagraphStyle("DFSmall", parent=base, fontName="Helvetica-Oblique", fontSize=8, leading=10, textColor=INK),
        "right": ParagraphStyle("DFRight", parent=base, fontName="Helvetica", fontSize=10, leading=12, alignment=2, textColor=INK),
    }


def _p(text, style):
    return Paragraph(text, style)


def _v(value):
    """Valeur échappée, ou chaîne vide (la ligne pointillée reste visible)."""
    if value in (None, ""):
        return ""
    return escape(str(value))


def _d(date):
    return date.strftime("%d/%m/%Y") if date else ""


def _line(parts, width, s, height=7.2):
    """Ligne de formulaire : [(libellé, valeur, part de largeur), …].

    La valeur est posée sur une ligne pointillée, laissée vide si inconnue.
    """
    cells, widths = [], []
    total = sum(p[2] for p in parts)
    for label, value, share in parts:
        w = width * share / total
        label_w = min(w * 0.7, stringWidth(label, "Helvetica", 10) + 4) if label else 0
        cells += [_p(escape(label), s["label"]) if label else "", _p(_v(value), s["value"])]
        widths += [label_w, w - label_w]
    table = Table([cells], colWidths=widths, rowHeights=[height * mm], hAlign="LEFT")
    style = [("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 1),
             ("RIGHTPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]
    for i in range(1, len(cells), 2):
        style.append(("LINEBELOW", (i, 0), (i, 0), 0.6, INK, None, (0.6, 2)))
    table.setStyle(TableStyle(style))
    return table


def _official_header(school, width, s, with_cap=True):
    left = [_p(escape(school.ministry_name or "Ministère de l'Éducation Nationale"), s["head"]),
            _p("*" * 30, s["stars"])]
    if school.academy_name:
        left += [_p(escape(school.academy_name), s["head"]), _p("*" * 30, s["stars"])]
    if with_cap and school.cap_name:
        left += [_p(escape(school.cap_name), s["head"]), _p("*" * 30, s["stars"])]
    right = [_p("République du Mali", s["head_c"]), _p("Un Peuple – Un But – Une Foi", s["head_c"])]
    table = Table([[left, right]], colWidths=[width * 0.6, width * 0.4])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return table


def _school_place(school):
    return escape(school.city) if school.city else ""


def _build(story, pagesize, title, margins=(16, 16, 14, 14)):
    buffer = BytesIO()
    left, right, top, bottom = (m * mm for m in margins)
    doc = SimpleDocTemplate(buffer, pagesize=pagesize, leftMargin=left, rightMargin=right,
                            topMargin=top, bottomMargin=bottom, title=title)
    doc.build(story(doc.width))
    return buffer.getvalue()


def _grid(data, widths, row_heights=None):
    table = Table(data, colWidths=widths, rowHeights=row_heights)
    style = [("GRID", (0, 0), (-1, -1), 0.6, INK), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("FONTSIZE", (0, 0), (-1, -1), 8.5)]
    table.setStyle(TableStyle(style))
    return table


def render_fiche_scolaire(student, school):
    s = _styles()
    data = fiche_data(student, school)

    def story(width):
        out = [_official_header(school, width, s), Spacer(1, 3 * mm),
               Table([[""]], colWidths=[width], rowHeights=[1], style=[("LINEBELOW", (0, 0), (-1, -1), 1, INK)]),
               Spacer(1, 2 * mm), _p("<u>FICHE SCOLAIRE</u>", s["title"])]
        box = lambda checked: Table([["X" if checked else ""]], colWidths=[22 * mm], rowHeights=[5.5 * mm],
                                    style=[("BOX", (0, 0), (-1, -1), 0.8, INK), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold")])
        sex = Table([[_p("Garçon", s["right"]), box(student.sex == "M")], [_p("Fille", s["right"]), box(student.sex == "F")]],
                    colWidths=[20 * mm, 24 * mm], hAlign="RIGHT")
        out += [sex, Spacer(1, 1 * mm)]
        out += [
            _line([("Prénoms :", student.first_name, 5), ("Nom :", student.last_name, 4)], width, s, 6.4),
            _line([("Né (e) le :", _d(student.date_of_birth), 5), ("à :", student.place_of_birth, 4)], width, s, 6.4),
            _line([("Pièce d'État Civil :", "", 4), ("N° :", "", 2.5), ("du :", "", 2.5)], width, s, 6.4),
            _line([("Délivrée par :", "", 1)], width, s, 6.4),
            _line([("Fils (Fille) de :", student.father_name, 5), ("Profession :", "", 4)], width, s, 6.4),
            _line([("Et de :", student.mother_name, 5), ("Profession :", "", 4)], width, s, 6.4),
            _line([("Demeurant à :", "", 1)], width, s, 6.4),
            _line([("Tuteur : Prénom et nom :", "", 1)], width, s, 6.4),
            _line([("Lien de parenté :", "", 1)], width, s, 6.4),
            _line([("Adresse complète :", "", 1)], width, s, 6.4),
            Spacer(1, 2 * mm), _p("<u>RECRUTEMENT</u>", s["section"]),
            _line([("École de :", school.name, 5), ("Préfecture de :", "", 4)], width, s, 6.4),
            _line([("Date de recrutement :", _d(data.recruitment_date), 5), ("N° Matricule :", student.matricule, 4)], width, s, 6.4),
            Spacer(1, 3 * mm),
        ]

        def cycle_table(codes, chosen):
            first = 22 * mm
            col = (width - first) / len(codes)
            head = [_p("<b>Classes</b>", s["cell"])] + [_p(f"<b>{CYCLE_LABELS[c]}</b>", s["cell"]) for c in codes]
            def cells(fn):
                return [_p(escape(fn(chosen[c])) if c in chosen else "", s["cell"]) for c in codes]
            rows = [
                head,
                [_p("<b>Date du</b>", s["cell"])] + cells(lambda e: str(e.school_year.start_date.year)),
                [_p("<b>au</b>", s["cell"])] + cells(lambda e: str(e.school_year.end_date.year)),
                [""] * (len(codes) + 1),
                [_p("<b>École</b>", s["cell"])] + cells(lambda e: e.school_year.school.name),
                [_p("<b>Préfecture</b>", s["cell"])] + [""] * len(codes),
                [_p("<b>Cercle</b>", s["cell"])] + [""] * len(codes),
            ]
            heights = [5 * mm, 4.6 * mm, 4.6 * mm, 2 * mm, 4.6 * mm, 4.6 * mm, 4.6 * mm]
            return _grid(rows, [first] + [col] * len(codes), heights)

        out += [_p("A. <u>1<super>er</super> CYCLE</u>", s["section"]), Spacer(1, 1.5 * mm),
                cycle_table(FIRST_CYCLE, data.first_cycle), Spacer(1, 1 * mm),
                _line([("CFEPCEF : Date :", "", 4), ("Résultat :", "", 5)], width, s, 6.4),
                _line([("Classes doublées :", ", ".join(data.doubled), 4), ("Orientation :", "", 5)], width, s, 6.4),
                Spacer(1, 3 * mm),
                _p("B. <u>2<super>ème</super> CYCLE</u>", s["section"]), Spacer(1, 1.5 * mm),
                cycle_table(SECOND_CYCLE, data.second_cycle), Spacer(1, 3 * mm),
                _p("<b>DIPLÔME D'ÉTUDES FONDAMENTALES</b>", s["section"]),
                _line([("Date :", "", 3), ("Résultat :", "", 4), ("Classe :", data.def_classe, 2)], width, s, 6.4),
                _line([("Orientation :", "", 1)], width, s)]
        return out

    return _build(story, A4, "Fiche scolaire", margins=(16, 16, 10, 8))


def render_releve_notes(enrollment):
    s = _styles()
    school = enrollment.school_year.school
    student = enrollment.student
    data = releve_data(enrollment)
    fmt = lambda v: f"{v:.2f}".replace(".", ",") if v is not None else ""

    def story(width):
        out = [_official_header(school, width, s), Spacer(1, 4 * mm),
               _line([("École Fondamentale de :", school.name, 1)], width, s), Spacer(1, 5 * mm),
               _p("<u>RELEVÉ DE NOTES</u>", s["section"]), Spacer(1, 4 * mm),
               _line([("Année Scolaire :", enrollment.school_year.name, 1)], width * 0.85, s),
               _line([("Prénoms :", student.first_name, 5), ("Nom :", student.last_name, 4)], width, s),
               _line([("Classe :", enrollment.classe.display_name, 1)], width * 0.5, s), Spacer(1, 5 * mm)]
        rows = [[_p("<b>Compositions</b>", s["cell_c"]), _p(f"<b>Moyenne/{data.scale}</b>", s["cell_c"]),
                 _p("<b>Appréciation</b>", s["cell_c"])]]
        for term, value, appreciation in data.rows:
            rows.append([_p(escape(term.name), s["cell"]), _p(fmt(value), s["cell_c"]), _p(escape(appreciation), s["cell_c"])])
        if not data.rows:
            for n in range(1, 6):
                rows.append([_p(f"{n}<super>{'ère' if n == 1 else 'ème'}</super> Période", s["cell"]), "", ""])
        table = Table(rows, colWidths=[width * 0.3, width * 0.3, width * 0.4], rowHeights=7 * mm)
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, INK), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        out += [table, Spacer(1, 8 * mm)]
        total_max = data.total_max or 30
        out += [
            _line([("Total des moyennes :", fmt(data.total) + (f" / {total_max}" if data.total is not None else ""), 1)], width, s),
            _line([("Moyenne générale :", fmt(data.moyenne) + (f" / {data.scale}" if data.moyenne is not None else ""), 1)], width, s),
            _line([("Proposition du conseil des maîtres :", data.decision, 1)], width, s),
            _line([("Le maître chargé de cours :", data.teacher, 1)], width, s),
            _line([("Le Directeur d'école :", "", 1)], width, s),
            Spacer(1, 14 * mm),
            _p(f"Fait à {_school_place(school) or '……………………'}, le {timezone.localdate():%d/%m/%Y}", s["right"]),
            Spacer(1, 14 * mm),
            _p("Vu par le Directeur du Centre d'Animation Pédagogique", s["right"]),
        ]
        return out

    return _build(story, A4, "Relevé de notes", margins=(20, 18, 16, 16))


def render_certificat_transfert(enrollment):
    s = _styles()
    school = enrollment.school_year.school
    student = enrollment.student
    data = transfert_data(enrollment)
    pronoun = "il" if student.sex == "M" else "elle" if student.sex == "F" else "il (elle)"

    def story(width):
        out = [_official_header(school, width, s), Spacer(1, 2 * mm),
               _p("<u>CERTIFICAT DE TRANSFERT</u>", s["title"]), Spacer(1, 3 * mm),
               _line([("Le (La) Directeur (trice) de l'école fondamentale", school.name, 1)], width, s),
               _line([("Soussigné(e), certifie que le (la) nommé(e)", f"{student.first_name} {student.last_name}", 1)], width, s),
               _line([("Né(e) le", _d(student.date_of_birth), 4), ("à", student.place_of_birth, 6)], width, s),
               _line([("Fils (fille) de", student.father_name, 5), ("et de", student.mother_name, 5)], width, s),
               _line([("A fréquenté ledit établissement du", _d(data.since), 6), ("au", _d(data.until), 4)], width, s),
               _line([("Sous le N° Mle", student.matricule, 3), (f"où {pronoun} était en classe de", enrollment.classe.education_level.name, 7)], width, s),
               Spacer(1, 4 * mm)]
        head = ["Travail", "Conduite", "Nombre d'années de scolarité", "Classes doublées",
                "Décision du Conseil des Maîtres", "Motif du Transfert", "École de Destination"]
        values = [data.work, "", f"{data.years} an{'s' if data.years > 1 else ''}" if data.years else "",
                  ", ".join(data.doubled), data.decision, "", ""]
        table = Table([[_p(f"<b>{escape(h)}</b>", s["cell_c"]) for h in head],
                       [_p(escape(v), s["cell_c"]) for v in values]],
                      colWidths=[width / 7] * 7, rowHeights=[12 * mm, 16 * mm])
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, INK), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        out += [table, Spacer(1, 5 * mm)]
        sign = Table([
            [_p("Avis du directeur du CAP (s'agissant d'un élève du second cycle)", s["label"]),
             _p(f"Fait à {_school_place(school) or '……………………'}, le {timezone.localdate():%d/%m/%Y}", s["label"])],
            ["", _p("Le Directeur de l'école", s["head_c"])],
        ], colWidths=[width * 0.55, width * 0.45], rowHeights=[10 * mm, 34 * mm])
        sign.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        out += [sign,
                _p("<u>NB</u> : Ce certificat sert uniquement pour l'admission provisoire de l'élève. "
                   "L'inscription définitive n'intervient qu'après la réception du dossier scolaire.", s["small"])]
        return out

    return _build(story, landscape(A4), "Certificat de transfert", margins=(16, 16, 12, 10))
