"""Badges du personnel (retours V8-8) : enseignants et autre personnel.

Format carte bancaire (CR80), 8 badges par feuille A4 à découper, comme les
cartes d'identité des élèves. Le QR code contient le code de pointage
(``KIS-ENS-<matricule>`` ou ``KIS-PER-<matricule>``), lu par le téléphone de
pointage pour enregistrer les entrées et les sorties.
"""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from administration.carte_identite_pdf import BORDER_BLUE, CARD_H, CARD_W, _draw_flag, _draw_qr, portrait_photo

STAFF_BLUE = colors.HexColor("#0F2D5C")


def badge_items(teachers=(), personnel=()):
    from vie_scolaire.services.pointage import personnel_code, teacher_code
    items = [{"name": f"{t.last_name} {t.first_name}".strip(), "role": t.specialty or "Enseignant(e)",
              "number": t.employee_number, "code": teacher_code(t), "photo": t.photo} for t in teachers]
    items += [{"name": f"{p.last_name} {p.first_name}".strip(), "role": p.function or "Personnel",
               "number": p.employee_number, "code": personnel_code(p), "photo": p.photo} for p in personnel]
    return items


def _draw_badge(c, x, y, item, school, year_name):
    c.saveState()
    c.translate(x, y)
    c.setStrokeColor(BORDER_BLUE)
    c.setLineWidth(0.9)
    c.setFillColor(colors.white)
    c.roundRect(0, 0, CARD_W, CARD_H, 2 * mm, stroke=1, fill=1)
    # Bandeau
    c.setFillColor(STAFF_BLUE)
    c.roundRect(0, CARD_H - 11 * mm, CARD_W, 11 * mm, 2 * mm, stroke=0, fill=1)
    c.rect(0, CARD_H - 11 * mm, CARD_W, 3 * mm, stroke=0, fill=1)
    _draw_flag(c, 2.5 * mm, CARD_H - 7.5 * mm, 5.5 * mm, 3.8 * mm)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 7.2)
    c.drawCentredString(CARD_W / 2, CARD_H - 5 * mm, (school.name if school else "")[:44])
    c.setFont("Helvetica", 5.6)
    c.drawCentredString(CARD_W / 2, CARD_H - 8.6 * mm, f"BADGE DU PERSONNEL · {year_name}")
    # Photo
    photo_w = photo_h = 22 * mm
    px, py = 3 * mm, CARD_H - 13 * mm - photo_h
    c.setStrokeColor(colors.HexColor("#c7d2e0"))
    c.setFillColor(colors.HexColor("#f0f3f8"))
    c.rect(px, py, photo_w, photo_h, stroke=1, fill=1)
    drawn = False
    photo = item.get("photo")
    if photo and hasattr(photo, "path"):
        try:
            c.drawImage(portrait_photo(photo.path, 1), px, py, width=photo_w, height=photo_h)
            drawn = True
        except Exception:
            drawn = False
    if not drawn:
        c.setFillColor(colors.HexColor("#8ea0bd"))
        c.setFont("Helvetica", 5.5)
        c.drawCentredString(px + photo_w / 2, py + photo_h / 2, "PHOTO")
    # Identité
    tx = px + photo_w + 3 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 8)
    words = item["name"].split()
    first_line, second_line = item["name"], ""
    if len(item["name"]) > 22 and len(words) > 1:
        first_line, second_line = words[0], " ".join(words[1:])
    ty = CARD_H - 17 * mm
    c.drawString(tx, ty, first_line[:24])
    if second_line:
        ty -= 3.8 * mm
        c.drawString(tx, ty, second_line[:24])
    ty -= 4.2 * mm
    c.setFont("Helvetica", 6.2)
    c.drawString(tx, ty, item["role"][:30])
    ty -= 3.4 * mm
    c.drawString(tx, ty, f"Matricule : {item['number']}"[:32])
    # QR (grand, pour une lecture rapide au portail)
    qr_size = 17 * mm
    _draw_qr(c, item["code"], CARD_W - qr_size - 2.5 * mm, 2.5 * mm, qr_size)
    c.setFont("Helvetica", 4.6)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawString(3 * mm, 3 * mm, "À présenter à l'entrée et à la sortie")
    c.restoreState()


def render_badges_pdf(items, school, year_name):
    """Feuilles A4 de 8 badges (2 x 4), ou un badge au format carte s'il n'y en a qu'un."""
    buffer = BytesIO()
    if len(items) == 1:
        c = canvas.Canvas(buffer, pagesize=(CARD_W, CARD_H))
        c.setTitle("Badge du personnel")
        _draw_badge(c, 0, 0, items[0], school, year_name)
        c.showPage()
        c.save()
        return buffer.getvalue()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle("Badges du personnel")
    cols, rows = 2, 4
    margin_x = (A4[0] - cols * CARD_W) / (cols + 1)
    margin_y = (A4[1] - rows * CARD_H) / (rows + 1)
    if not items:
        c.setFont("Helvetica", 12)
        c.drawCentredString(A4[0] / 2, A4[1] / 2, "Aucun membre du personnel actif.")
    for start in range(0, len(items), cols * rows):
        for i, item in enumerate(items[start:start + cols * rows]):
            col, row = i % cols, i // cols
            x = margin_x + col * (CARD_W + margin_x)
            y = A4[1] - margin_y - (row + 1) * CARD_H - row * margin_y
            _draw_badge(c, x, y, item, school, year_name)
        c.showPage()
    c.save()
    return buffer.getvalue()
