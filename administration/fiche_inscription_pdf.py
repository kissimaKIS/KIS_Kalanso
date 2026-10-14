"""Fiche d'inscription : vierge (à remplir à la main) ou pré-remplie pour un élève.

Même mise en page dans les deux cas ; ce que KIS Kalanso ne connaît pas reste en
pointillés. La version vierge liste les frais de l'année active (obligatoires
avec leur montant, options à cocher).
"""
from io import BytesIO
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from administration.documents_fondamental import INK, _d, _line, _p, _styles


def _money(value, currency):
    return f"{value:,.0f} {currency}".replace(",", " ")


def _header(school, width, s, year_name):
    left = [_p(f"<b>{escape(school.name)}</b>", s["head"])]
    details = " — ".join(x for x in [school.address, school.city, f"Tél. : {school.phone}" if school.phone else "", school.email] if x)
    if details:
        left.append(_p(escape(details), s["head"]))
    right = [_p("Année scolaire", s["head_c"]), _p(f"<b>{escape(year_name) if year_name else '……………………'}</b>", s["head_c"])]
    t = Table([[left, right]], colWidths=[width * 0.68, width * 0.32])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("BOX", (1, 0), (1, 0), 0.6, INK)]))
    return t


def _section(title, s):
    t = Table([[_p(f"<b>{title}</b>", s["head"])]], colWidths=[None])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.8, INK), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return [Spacer(1, 3 * mm), t, Spacer(1, 1 * mm)]


class CheckBox(Flowable):
    """Petit carré à cocher dessiné (indépendant des polices du lecteur PDF)."""

    def __init__(self, checked=False, size=3.4 * mm):
        super().__init__()
        self.checked, self.size = checked, size
        self.width = self.height = size

    def draw(self):
        c = self.canv
        c.setStrokeColor(INK)
        c.setLineWidth(0.7)
        c.rect(0, 0, self.size, self.size)
        if self.checked:
            c.setLineWidth(1)
            c.line(0.7, self.size * 0.5, self.size * 0.4, 0.7)
            c.line(self.size * 0.4, 0.7, self.size - 0.5, self.size - 0.5)


def _box_cell(checked):
    t = Table([[CheckBox(checked)]], colWidths=[None])
    t.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


def render_fiche_inscription(school, year=None, enrollment=None):
    """``enrollment`` absent : fiche vierge pour l'année ``year``."""
    from finance.models import FeeType, Invoice

    s = _styles()
    student = enrollment.student if enrollment else None
    year = enrollment.school_year if enrollment else year
    cur = school.currency
    v = (lambda attr: getattr(student, attr) or "") if student else (lambda attr: "")

    def story(width):
        out = [_header(school, width, s, year.name if year else ""), Spacer(1, 4 * mm),
               _p("<u>FICHE D'INSCRIPTION</u>", s["title"]), Spacer(1, 2 * mm)]
        # Élève + cadre photo
        identity = [
            _line([("Nom :", v("last_name"), 5), ("Prénom(s) :", v("first_name"), 6)], width - 32 * mm, s, 6.6),
            _line([("Sexe :", {"M": "Garçon", "F": "Fille"}.get(v("sex"), "") if student else "", 3),
                   ("Né(e) le :", _d(student.date_of_birth) if student else "", 4), ("à :", v("place_of_birth"), 4)], width - 32 * mm, s, 6.6),
            _line([("Matricule :", v("matricule"), 4), ("Classe :", enrollment.classe.display_name if enrollment else "", 5)], width - 32 * mm, s, 6.6),
            _line([("Statut :", enrollment.get_student_type_display() if enrollment else "", 4),
                   ("Date d'inscription :", _d(enrollment.enrollment_date) if enrollment else "", 5)], width - 32 * mm, s, 6.6),
            _line([("École précédente :", "", 6), ("Dernière classe :", "", 4)], width - 32 * mm, s, 6.6),
        ]
        photo = Table([[_p("Photo", s["head_c"])]], colWidths=[28 * mm], rowHeights=[34 * mm])
        photo.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, INK), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        t = Table([[identity, photo]], colWidths=[width - 32 * mm, 32 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
        out += _section("ÉLÈVE", s) + [t]
        out += _section("PARENTS / TUTEUR", s) + [
            _line([("Père :", v("father_name"), 6), ("Tél. :", v("father_phone"), 3)], width, s, 6.6),
            _line([("Profession du père :", "", 1)], width, s, 6.6),
            _line([("Mère :", v("mother_name"), 6), ("Tél. :", v("mother_phone"), 3)], width, s, 6.6),
            _line([("Profession de la mère :", "", 1)], width, s, 6.6),
            _line([("Tuteur (si différent) :", "", 6), ("Tél. :", "", 3)], width, s, 6.6),
            _line([("Adresse / quartier :", "", 6), ("WhatsApp :", v("whatsapp_phone"), 3)], width, s, 6.6),
        ]
        # Frais
        rows = [[_p("<b>Frais</b>", s["cell"]), _p("<b>Montant</b>", s["cell_c"]), _p("<b>Choix</b>", s["cell_c"])]]
        if enrollment:
            for inv in Invoice.objects.filter(enrollment=enrollment).select_related("fee_type").order_by("fee_type__category", "fee_type__name"):
                rows.append([_p(escape(inv.fee_type.name), s["cell"]), _p(_money(inv.total_amount, cur), s["cell_c"]), _box_cell(True)])
        elif year:
            fees = FeeType.objects.filter(school_year=year, is_active=True).order_by("category", "name")
            seen = set()
            for fee in fees:
                optional = fee.category == FeeType.Category.OPTIONAL
                key = (fee.name, fee.amount, optional)
                if key in seen:
                    continue
                seen.add(key)
                scope = ""
                if fee.classe_id:
                    scope = f" ({fee.classe.display_name})"
                elif fee.education_level_id:
                    scope = f" ({fee.education_level.name})"
                elif fee.school_type:
                    scope = f" ({fee.get_school_type_display()})"
                rows.append([_p(escape(fee.name + scope), s["cell"]), _p(_money(fee.amount, cur), s["cell_c"]),
                             _box_cell(False) if optional else _p("Obligatoire", s["cell_c"])])
        for _ in range(2):
            rows.append(["", "", _box_cell(False)])
        fees = Table(rows, colWidths=[width * 0.6, width * 0.22, width * 0.18])
        fees.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, INK), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                  ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF1FB"))]))
        out += _section("FRAIS DE SCOLARITÉ", s) + [fees, Spacer(1, 1 * mm),
                                                     _line([("Remise accordée :", "", 5), ("Motif :", "", 5)], width, s, 6.6)]
        docs = ["Extrait d'acte de naissance", "Photos d'identité", "Certificat de transfert", "Bulletins / relevés de l'année précédente"]
        grid = Table([[CheckBox(), _p(escape(docs[0]), s["label"]), CheckBox(), _p(escape(docs[1]), s["label"])],
                      [CheckBox(), _p(escape(docs[2]), s["label"]), CheckBox(), _p(escape(docs[3]), s["label"])]],
                     colWidths=[6 * mm, width / 2 - 6 * mm, 6 * mm, width / 2 - 6 * mm])
        grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        out += _section("PIÈCES FOURNIES", s) + [grid]
        signatures = Table([[_p("Signature du parent / tuteur", s["head_c"]), _p("Visa de l'établissement", s["head_c"])]],
                           colWidths=[width / 2, width / 2], rowHeights=[22 * mm])
        signatures.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (0, 0), 0.5, INK), ("BOX", (1, 0), (1, 0), 0.5, INK)]))
        place = escape(school.city) if school.city else "……………………"
        date = _d(enrollment.enrollment_date) if enrollment else "……/……/…………"
        out += [Spacer(1, 4 * mm), _p(f"Fait à {place}, le {date}", s["right"]), Spacer(1, 2 * mm), signatures]
        return out

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=12 * mm, bottomMargin=10 * mm,
                            title="Fiche d'inscription")
    doc.build(story(doc.width))
    return buffer.getvalue()
