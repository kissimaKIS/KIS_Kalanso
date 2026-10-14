"""Carte d'identité scolaire (FeedbacksV2, point 2).

Le visuel reproduit un modèle déjà en usage réel dans une école cliente
(en-tête République du Mali / Ministère / Académie / CAP / École / Année
scolaire, drapeau, logo de l'école, photo, identité, QR code, signature du
Directeur) — carte recto uniquement, comme le modèle fourni.

Deux usages :
- une carte individuelle, au format CR80 (85,6 x 53,98 mm — le format d'une
  carte bancaire), utilisable telle quelle sur une imprimante à cartes ;
- une impression en lot pour toute une classe, sur des feuilles A4 (8 cartes
  par page, 2 colonnes x 4 lignes), pensée pour être imprimée sur papier
  cartonné puis découpée.

Le QR code est généré par ReportLab lui-même (``reportlab.graphics.barcode.qr``)
— aucune dépendance supplémentaire à ajouter au projet ni au ``.spec``
PyInstaller. Il encode le matricule de l'élève.
"""
from io import BytesIO
from xml.sax.saxutils import escape

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

CARD_W = 85.6 * mm
CARD_H = 53.98 * mm

MALI_GREEN = colors.HexColor("#14A64B")
MALI_GOLD = colors.HexColor("#FCD116")
MALI_RED = colors.HexColor("#CE1126")
BORDER_BLUE = colors.HexColor("#1a8fc4")



def portrait_photo(path, ratio):
    """Photo redressée et recadrée au format du cadre (largeur/hauteur = ratio ; 1 = carré).

    - Les photos de téléphone portent leur orientation dans les données EXIF ;
      ReportLab l'ignore et les affichait couchées : on applique cette rotation.
    - La photo est ensuite recadrée (sans déformation) pour remplir le cadre
      vertical ; le recadrage garde le haut de l'image, où se trouve le visage.
    """
    from io import BytesIO
    from PIL import Image, ImageOps
    from reportlab.lib.utils import ImageReader

    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    w, h = image.size
    if w / h > ratio:  # trop large : on garde le centre
        new_w = int(h * ratio)
        left = (w - new_w) // 2
        image = image.crop((left, 0, left + new_w, h))
    else:  # trop haute : on garde surtout le haut (visage)
        new_h = int(w / ratio)
        top = int((h - new_h) * 0.25)
        image = image.crop((0, top, w, top + new_h))
    image.thumbnail((700, 700))
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=88)
    buffer.seek(0)
    return ImageReader(buffer)

def _full_name(student):
    return f"{student.first_name} {student.last_name}".strip()


def _draw_flag(c, x, y, w, h):
    stripe_w = w / 3
    c.setFillColor(MALI_GREEN)
    c.rect(x, y, stripe_w, h, stroke=0, fill=1)
    c.setFillColor(MALI_GOLD)
    c.rect(x + stripe_w, y, stripe_w, h, stroke=0, fill=1)
    c.setFillColor(MALI_RED)
    c.rect(x + 2 * stripe_w, y, stripe_w, h, stroke=0, fill=1)


def qr_payload(enrollment, school):
    """Contenu du QR code (retours du 08/10) : matricule, prénom et nom, classe, école, année.

    Une information par ligne, sans libellés, pour garder un code lisible au
    téléphone malgré sa petite taille sur la carte.
    """
    student = enrollment.student
    return "\n".join([
        student.matricule or f"KIS-ELV-{student.pk}",
        f"{student.first_name} {student.last_name}",
        enrollment.classe.display_name,
        school.name,
        enrollment.school_year.name,
    ])


def _draw_qr(c, value, x, y, size):
    widget = qr.QrCodeWidget(value or "N/A")
    b = widget.getBounds()
    w = b[2] - b[0]
    h = b[3] - b[1]
    d = Drawing(size, size, transform=[size / w, 0, 0, size / h, 0, 0])
    d.add(widget)
    renderPDF.draw(d, c, x, y)


def _draw_card(c, x, y, enrollment, school, year):
    student = enrollment.student
    classe = enrollment.classe

    c.saveState()
    c.translate(x, y)

    c.setStrokeColor(BORDER_BLUE)
    c.setLineWidth(0.9)
    c.setFillColor(colors.white)
    c.roundRect(0, 0, CARD_W, CARD_H, 2 * mm, stroke=1, fill=1)

    # Drapeau du Mali (haut gauche)
    _draw_flag(c, 2.2 * mm, CARD_H - 6.5 * mm, 5.5 * mm, 3.8 * mm)

    # Logo de l'école (haut droit), si disponible
    if school.logo and hasattr(school.logo, "path"):
        try:
            c.drawImage(school.logo.path, CARD_W - 10 * mm, CARD_H - 8.5 * mm, width=7.5 * mm, height=7.5 * mm, preserveAspectRatio=True, anchor="c", mask="auto")
        except Exception:
            pass

    # En-tête institutionnel, centré
    c.setFillColor(colors.black)
    header_lines = [
        ("REPUBLIQUE DU MALI", "Helvetica-Bold", 5.6),
        (school.ministry_name or "MINISTERE DE L'EDUCATION NATIONALE", "Helvetica", 5.0),
    ]
    if school.academy_name:
        header_lines.append((f"ACADEMIE DE : {school.academy_name}", "Helvetica", 5.0))
    is_fundamental = classe.education_level and classe.education_level.school_type in {"fundamental_1", "fundamental_2"}
    if is_fundamental and school.cap_name:
        header_lines.append((f"CAP DE : {school.cap_name}", "Helvetica", 5.0))
    header_lines.append((f"ECOLE : {school.name}", "Helvetica", 5.0))
    header_lines.append((f"ANNEE SCOLAIRE : {year.name}", "Helvetica", 5.0))

    ty = CARD_H - 3.6 * mm
    for text, font, size in header_lines:
        c.setFont(font, size)
        c.drawCentredString(CARD_W / 2, ty, text[:60])
        ty -= size * 1.05

    ty -= 0.3 * mm
    c.setFont("Helvetica-Bold", 6.3)
    c.drawCentredString(CARD_W / 2, ty, "CARTE D'IDENTITE SCOLAIRE")
    body_top = ty - 2.3 * mm

    # Photo
    # Cadre carré, aligné en haut de la zone d'identité ; la photo est
    # redressée (EXIF) puis recadrée au carré sans déformation.
    photo_w = photo_h = min(21 * mm, body_top - 3 * mm)
    photo_x, photo_y = 2.5 * mm, body_top - photo_h
    c.setStrokeColor(colors.HexColor("#c7d2e0"))
    c.setFillColor(colors.HexColor("#f0f3f8"))
    c.rect(photo_x, photo_y, photo_w, photo_h, stroke=1, fill=1)
    drawn = False
    if student.photo and hasattr(student.photo, "path"):
        try:
            c.drawImage(portrait_photo(student.photo.path, photo_w / photo_h), photo_x, photo_y, width=photo_w, height=photo_h)
            drawn = True
        except Exception:
            drawn = False
    if not drawn:
        c.setFillColor(colors.HexColor("#8ea0bd"))
        c.setFont("Helvetica", 5.5)
        c.drawCentredString(photo_x + photo_w / 2, photo_y + photo_h / 2, "PHOTO")

    # Identité
    text_x = photo_x + photo_w + 2.8 * mm
    c.setFillColor(colors.black)
    iy = body_top - 3.2 * mm
    c.setFont("Helvetica-Bold", 8)
    c.drawString(text_x, iy, escape(student.last_name)[:24])
    iy -= 4 * mm
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(text_x, iy, escape(student.first_name)[:24])
    iy -= 4.3 * mm
    c.setFont("Helvetica", 6)
    c.drawString(text_x, iy, f"Classe : {escape(classe.display_name)}")
    iy -= 3.3 * mm
    c.drawString(text_x, iy, f"Matricule : {escape(student.matricule) if student.matricule else '—'}")
    iy -= 3.3 * mm
    dob = student.date_of_birth.strftime("%d/%m/%Y") if student.date_of_birth else "……………"
    pob = escape(student.place_of_birth) if student.place_of_birth else "……………"
    c.drawString(text_x, iy, f"Né(e) le {dob} à {pob}"[:44])

    # QR code + signature (bas droit)
    qr_size = 12 * mm
    qr_x = CARD_W - qr_size - 2.5 * mm
    qr_y = 3 * mm
    _draw_qr(c, qr_payload(enrollment, school), qr_x, qr_y, qr_size)

    c.setStrokeColor(colors.black)
    c.setLineWidth(0.4)
    sign_x2 = qr_x - 2.5 * mm
    sign_x1 = sign_x2 - 20 * mm
    sign_y = 5.5 * mm
    c.line(sign_x1, sign_y, sign_x2, sign_y)
    c.setFont("Helvetica", 5.3)
    c.drawCentredString((sign_x1 + sign_x2) / 2, sign_y + 1 * mm, "Le Directeur")

    c.restoreState()


def render_carte_identite_pdf(enrollment):
    """Carte individuelle au format CR80 exact."""
    school = enrollment.school_year.school
    year = enrollment.school_year
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(CARD_W, CARD_H))
    c.setTitle("Carte d'identité scolaire")
    _draw_card(c, 0, 0, enrollment, school, year)
    c.showPage()
    c.save()
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    safe_name = _full_name(enrollment.student).replace(" ", "_")
    response["Content-Disposition"] = f'inline; filename="carte-identite-{safe_name}.pdf"'
    return response


def render_cartes_identite_classe_pdf(enrollments):
    """Impression en lot pour une classe : feuilles A4, 8 cartes par page (2 x 4)."""
    if not enrollments:
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        c.setFont("Helvetica", 12)
        c.drawCentredString(A4[0] / 2, A4[1] / 2, "Aucun élève inscrit dans cette classe.")
        c.save()
        response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = 'inline; filename="cartes-identite-classe.pdf"'
        return response

    cols, rows = 2, 4
    per_page = cols * rows
    margin_x = (A4[0] - cols * CARD_W) / (cols + 1)
    margin_y = (A4[1] - rows * CARD_H) / (rows + 1)

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle("Cartes d'identité — classe")

    pages = [enrollments[i:i + per_page] for i in range(0, len(enrollments), per_page)]
    for page_items in pages:
        for i, enrollment in enumerate(page_items):
            col = i % cols
            row = i // cols
            x = margin_x + col * (CARD_W + margin_x)
            y = A4[1] - margin_y - (row + 1) * CARD_H - row * margin_y
            school = enrollment.school_year.school
            year = enrollment.school_year
            _draw_card(c, x, y, enrollment, school, year)
        c.showPage()

    c.save()
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    classe = enrollments[0].classe
    safe_name = classe.display_name.replace(" ", "_").replace("/", "-")
    response["Content-Disposition"] = f'inline; filename="cartes-identite-{safe_name}.pdf"'
    return response
