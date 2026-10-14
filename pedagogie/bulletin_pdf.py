# -*- coding: cp1252 -*-
from io import BytesIO
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    BaseDocTemplate,
    PageTemplate,
    Frame,
    FrameBreak,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    PageBreak,
    KeepTogether,
    KeepInFrame,
    Image,
)

from .bulletin_render import build_bulletin_context


def format_number(value):
    """Format scolaire lisible : virgule décimale, sans zéros inutiles."""
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".replace(".", ",")


def _p(text, style):
    return Paragraph(str(text if text is not None else ""), style)


def _school_header(ctx, width, styles, bulletin=None):
    """En-tête officiel : logo à gauche, chaîne institutionnelle centrée,
    informations du bulletin à droite.

    Fondamental : Ministère -> Académie -> CAP -> Établissement -> coordonnées.
    Secondaire : Ministère -> Académie -> Établissement -> coordonnées.
    La devise n'appartient pas à l'en-tête officiel.
    """
    school = getattr(ctx["school_year"], "school", None)

    school_name = getattr(school, "name", "") if school else ""
    school_code = getattr(school, "code", "") if school else ""
    address = getattr(school, "address", "") if school else ""
    city = getattr(school, "city", "") if school else ""
    ministry_name = getattr(school, "ministry_name", "") if school else ""
    academy_name = getattr(school, "academy_name", "") if school else ""
    cap_name = getattr(school, "cap_name", "") if school else ""

    ministry_name = ministry_name.strip() or "MINISTÈRE DE L'ÉDUCATION NATIONALE"
    academy_name = academy_name.strip()
    cap_name = cap_name.strip()
    school_label = school_name.strip()
    if school_code:
        school_label = f"{school_label} ({school_code.strip()})"
    contact_parts = [part.strip() for part in (address, city) if part and part.strip()]
    if getattr(school, "phone", ""):
        contact_parts.append(f"Tél. : {school.phone.strip()}")
    if getattr(school, "email", ""):
        contact_parts.append(school.email.strip())
    address_label = " — ".join(contact_parts)

    # Le helper est aussi utilisé directement par certains documents/tests
    # historiques avec une feuille de styles minimale. Garantir ici ses
    # styles évite une dépendance à l'appelant tout en conservant le rendu.
    if "SchoolHeaderLine" not in styles.byName:
        styles.add(ParagraphStyle(
            "SchoolHeaderLine",
            parent=styles["Normal"],
            fontSize=9.0,
            leading=10.4,
            alignment=1,
            spaceAfter=0,
        ))
    if "SchoolHeaderSchool" not in styles.byName:
        styles.add(ParagraphStyle(
            "SchoolHeaderSchool",
            parent=styles["SchoolHeaderLine"],
            fontName="Helvetica-Bold",
        ))
    if "SchoolHeaderMotto" not in styles.byName:
        styles.add(ParagraphStyle(
            "SchoolHeaderMotto",
            parent=styles["SchoolHeaderLine"],
            fontName="Helvetica-Oblique",
        ))

    line_style = styles["SchoolHeaderLine"]
    school_line_style = styles["SchoolHeaderSchool"]
    motto_style = styles["SchoolHeaderMotto"]

    logo_flowable = Spacer(1, 29 * mm)
    if school is not None and getattr(school, "logo", None):
        try:
            logo_path = school.logo.path
            if logo_path and os.path.exists(logo_path):
                logo_flowable = Image(
                    logo_path,
                    width=28 * mm,
                    height=28 * mm,
                    kind="proportional",
                )
        except (AttributeError, OSError, ValueError):
            pass

    # Le CAP appartient à l'en-tête officiel du fondamental uniquement.
    # Le type pédagogique réel du bulletin est déterminé par sa classe.
    classe = getattr(getattr(bulletin, "enrollment", None), "classe", None) if bulletin is not None else None
    education_level = getattr(classe, "education_level", None)
    school_type = getattr(education_level, "school_type", "")
    # Quand le helper est appelé sans bulletin (notamment par les tests et
    # certains documents), utiliser le type de l'établissement comme
    # contexte de secours. Le CAP reste réservé au fondamental.
    if not school_type:
        school_type = getattr(school, "school_type", "")
    is_fundamental = school_type in {"fundamental_1", "fundamental_2"}

    center_lines = [
        _p(ministry_name, line_style),
        _p(academy_name, line_style),
    ]
    if is_fundamental and cap_name:
        center_lines.append(_p(cap_name, line_style))
    center_lines.extend([
        _p(school_label, school_line_style),
        _p(address_label, line_style),
    ])

    year = ctx["school_year"]
    year_name = getattr(year, "name", str(year))
    bulletin_pk = getattr(bulletin, "pk", None) if bulletin is not None else None
    bulletin_number = f"{year_name}-{bulletin_pk:03d}" if bulletin_pk else "—"

    right_style = ParagraphStyle(
        "BulletinHeaderBox",
        parent=styles["SchoolHeaderLine"],
        fontSize=8.4,
        leading=10,
        alignment=1,
    )
    right_box = Table(
        [
            [_p("<b>Année scolaire</b>", right_style)],
            [_p(f"<b>{year_name}</b>", right_style)],
            [_p("<b>Bulletin N°</b>", right_style)],
            [_p(bulletin_number, right_style)],
        ],
        colWidths=[36 * mm],
        rowHeights=[7 * mm, 8 * mm, 7 * mm, 8 * mm],
    )
    right_box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#9db8d4")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eaf3fb")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LINEBELOW", (0, 1), (-1, 1), 0.3, colors.HexColor("#9db8d4")),
        ("LINEBELOW", (0, 2), (-1, 2), 0.3, colors.HexColor("#9db8d4")),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    header = Table(
        [[logo_flowable, center_lines, right_box]],
        colWidths=[32 * mm, max(width - 72 * mm, 70 * mm), 40 * mm],
        rowHeights=[32 * mm],
    )
    header.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#1f4e79")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("ALIGN", (2, 0), (2, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return header


def _bulletin_story(bulletin, page_width, page_height, is_duplicate=False):
    ctx = build_bulletin_context(bulletin)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "SchoolHeaderLine",
        parent=styles["Normal"],
        fontSize=9.0,
        leading=10.4,
        alignment=1,
        spaceAfter=0,
    ))
    styles.add(ParagraphStyle(
        "SchoolHeaderSchool",
        parent=styles["SchoolHeaderLine"],
        fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "SchoolHeaderMotto",
        parent=styles["SchoolHeaderLine"],
        fontName="Helvetica-Oblique",
    ))
    title = ParagraphStyle(
        "BulletinTitle",
        parent=styles["Title"],
        fontSize=12.5,
        leading=14,
        spaceBefore=2,
        spaceAfter=2,
        alignment=1,
    )
    small = ParagraphStyle(
        "BulletinSmall",
        parent=styles["Normal"],
        fontSize=8.3,
        leading=9.6,
    )
    normal = ParagraphStyle(
        "BulletinNormal",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=9.8,
    )
    center = ParagraphStyle(
        "BulletinCenter",
        parent=normal,
        alignment=1,
    )
    header_center = ParagraphStyle(
        "BulletinHeader",
        parent=center,
        fontSize=7.5,
        leading=8.5,
    )

    student = ctx["student"]
    classe = ctx["classe"]
    year = ctx["school_year"]
    period = ctx["period"]

    title_bar = Table(
        [[_p("BULLETIN DE NOTES" + (" — DUPLICATA" if is_duplicate else ""), title)]],
        colWidths=[page_width],
        rowHeights=[11 * mm],
    )
    title_bar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1f5a91")),
        ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#1f5a91")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    story = [
        _school_header(ctx, page_width, styles, bulletin),
        Spacer(1, 1.5 * mm),
        title_bar,
        Spacer(1, 1.5 * mm),
    ]

    education_level = getattr(classe, "education_level", None)
    school_type_labels = {
        "preschool": "Préscolaire",
        "fundamental_1": "Fondamentale 1",
        "fundamental_2": "Fondamentale 2",
        "high_school": "Lycée",
        "vocational": "Centre professionnel",
    }
    cycle_label = school_type_labels.get(getattr(education_level, "school_type", ""), "")
    level_label = getattr(education_level, "name", "")
    dob = getattr(student, "date_of_birth", None)
    birth_label = dob.strftime("%d/%m/%Y") if dob else ""
    place = getattr(student, "place_of_birth", "") or ""
    if place:
        birth_label = f"{birth_label} à {place}" if birth_label else place
    identity = [
        [_p("<b>Élève</b>", small), _p(f"{getattr(student, 'first_name', '')} {getattr(student, 'last_name', '')}", normal), _p("<b>Cycle</b>", small), _p(cycle_label, normal)],
        [_p("<b>Matricule</b>", small), _p(getattr(student, "matricule", ""), normal), _p("<b>Né(e) le</b>", small), _p(birth_label, normal)],
        [_p("<b>Classe</b>", small), _p(getattr(classe, "name", classe), normal), _p("<b>Période</b>", small), _p(getattr(period, "name", period), normal)],
    ]

    identity_table = Table(
        identity,
        colWidths=[
            page_width * 0.13,
            page_width * 0.37,
            page_width * 0.13,
            page_width * 0.37,
        ],
    )
    identity_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#7f9fbd")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eaf3fb")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#eaf3fb")),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1.5),
        ("TOPPADDING", (0, 0), (-1, -1), 2.1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.1),
    ]))
    story += [identity_table, Spacer(1, 2.5 * mm)]

    total_coeff = sum(
        (float(line.get("coefficient") or 0) for line in ctx["lines"]),
        0,
    ) if ctx["mode"] != "F1" else 0
    weighted_total = sum(
        (float(line.get("moyenne_coeff") or 0) for line in ctx["lines"]),
        0,
    ) if ctx["mode"] != "F1" else 0

    columns = ctx["columns"]
    rows = [[_p(label, header_center) for _, label in columns]]

    for line in ctx["lines"]:
        rendered = []
        for key, _ in columns:
            value = line.get(key, "")
            if key == "subject":
                value = line.get("display_name") or getattr(value, "name", value)
            if key in {
                "moyenne_de_classe",
                "note_de_composition",
                "moyenne",
                "coefficient",
                "moyenne_coeff",
                "composition",
            }:
                value = format_number(value)
            rendered.append(
                _p(value, center if key != "subject" else normal)
            )
        rows.append(rendered)

    if ctx["mode"] == "F1":
        widths = [
            page_width * 0.38,
            page_width * 0.20,
            page_width * 0.16,
            page_width * 0.26,
        ]
    else:
        widths = [
            page_width * 0.25,
            page_width * 0.13,
            page_width * 0.13,
            page_width * 0.09,
            page_width * 0.07,
            page_width * 0.14,
            page_width * 0.18,
        ]

    if ctx["mode"] != "F1":
        rows.append([
            _p("<b>TOTAL</b>", small),
            "",
            "",
            "",
            _p(f"<b>{format_number(total_coeff)}</b>", center),
            _p(f"<b>{format_number(weighted_total)}</b>", center),
            "",
        ])

    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#7f9fbd")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dcebf8")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1.3),
        ("TOPPADDING", (0, 0), (-1, -1), 1.8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8),
    ]))

    # Les totaux sont intégrés au tableau sous leurs colonnes respectives.
    class_size = classe.enrollments.filter(school_year=year).count()
    moyenne = ctx.get("moyenne_generale")
    mention = ""
    if moyenne is not None:
        from .bulletin_appreciations import appreciation_for
        mention = appreciation_for(moyenne, 10 if ctx["mode"] == "F1" else 20)

    summary_box = Table(
        [
            [_p("<b>Moyenne générale</b>", small), _p(format_number(moyenne), normal)],
            [_p("<b>Rang</b>", small), _p(ctx.get("rang") or "—", normal)],
            [_p("<b>Effectif de la classe</b>", small), _p(class_size, normal)],
            [_p("<b>Mention</b>", small), _p(mention, normal)],
        ],
        colWidths=[page_width * 0.34, page_width * 0.18],
        rowHeights=[8 * mm] * 4,
    )
    summary_box.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#7f9fbd")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eaf3fb")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    observation_box = Table(
        [
            [_p("<b>Appréciation générale du conseil de classe</b>", center)],
            [_p(ctx["observation_generale"], normal)],
        ],
        colWidths=[page_width * 0.48],
        rowHeights=[8 * mm, 24 * mm],
    )
    observation_box.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#7f9fbd")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf3fb")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    synthesis = Table(
        [[summary_box, observation_box]],
        colWidths=[page_width * 0.53, page_width * 0.47],
        rowHeights=[32 * mm],
    )
    synthesis.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    generated_at = getattr(bulletin, "date_generation", None)
    generated_date = generated_at.strftime("%d/%m/%Y") if generated_at else ""

    if ctx["mode"] == "F1":
        signature_labels = [
            _p("Le maître", center),
            _p("Le directeur", center),
            _p("Le parent / tuteur", center),
        ]
    else:
        signature_labels = [
            _p("Le directeur", center),
            _p("Le parent / tuteur", center),
        ]

    signature_table = Table(
        [[
            _p(
                f"Édité le {generated_date}" if generated_date else "",
                small,
            ),
            *signature_labels,
        ]] if ctx["mode"] == "F1" else [[
            _p(
                f"Édité le {generated_date}" if generated_date else "",
                small,
            ),
            *signature_labels,
        ]],
        colWidths=(
            [page_width * 0.20] + [page_width * 0.2666667] * 3
            if ctx["mode"] == "F1"
            else [page_width * 0.25, page_width * 0.375, page_width * 0.375]
        ),
        rowHeights=[18 * mm],
    )
    signature_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("ALIGN", (1, 0), (-1, 0), "CENTER"),
        ("LINEABOVE", (1, 0), (-1, 0), 0.45, colors.HexColor("#7f9fbd")),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    # Le tableau des résultats est le cœur du bulletin : il doit toujours
    # rester dans le flux avant la synthèse. Le total des coefficients est
    # déjà intégré à sa dernière ligne, sous la colonne « Coefficient ».
    story += [
        table,
        Spacer(1, 2.5 * mm),
        synthesis,
        Spacer(1, 5 * mm),
        signature_table,
    ]
    return story


def _draw_page_border(canvas, doc):
    """Cadre discret bleu sur chaque page, comme sur le modèle visuel."""
    canvas.saveState()
    width, height = doc.pagesize
    canvas.setStrokeColor(colors.HexColor("#1f4e79"))
    canvas.setLineWidth(0.8)
    canvas.rect(5 * mm, 5 * mm, width - 10 * mm, height - 10 * mm)
    canvas.restoreState()


def render_bulletin_pdf(bulletin, output=None, copies_per_page=1, is_duplicate=False):
    """
    Génère un bulletin PDF.

    copies_per_page:
      1 = un bulletin par page portrait
      2 = deux bulletins par page paysage, côte à côte.

    En mode 2/page, ce bulletin est rendu comme un lot de deux exemplaires
    identiques. Pour imprimer plusieurs élèves différents, utiliser
    render_bulletins_pdf().
    """
    if copies_per_page not in (1, 2):
        raise ValueError("copies_per_page doit être 1 ou 2.")

    if copies_per_page == 2:
        return render_bulletins_pdf(
            [bulletin, bulletin],
            output=output,
            copies_per_page=2,
            is_duplicate=is_duplicate,
        )

    buffer = BytesIO() if output is None else output
    page_size = A4
    page_width, page_height = page_size
    margin = 8 * mm

    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        rightMargin=margin,
        leftMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title="Bulletin scolaire",
        onFirstPage=_draw_page_border,
        onLaterPages=_draw_page_border,
    )
    story = _bulletin_story(
        bulletin,
        page_width - 2 * margin,
        page_height - 2 * margin,
        is_duplicate=is_duplicate,
    )
    doc.build(story)

    if output is None:
        return buffer.getvalue()
    return output


def render_bulletins_pdf(bulletins, output=None, copies_per_page=1, is_duplicate=False):
    """Génère un lot : 1 bulletin/page portrait ou 2/page paysage côte à côte."""
    if copies_per_page not in (1, 2):
        raise ValueError("copies_per_page doit être 1 ou 2.")

    bulletins = list(bulletins)
    if not bulletins:
        raise ValueError("Aucun bulletin à générer.")

    buffer = BytesIO() if output is None else output

    if copies_per_page == 1:
        page_size = A4
        page_width, page_height = page_size
        margin = 10 * mm
        doc = SimpleDocTemplate(
            buffer,
            pagesize=page_size,
            rightMargin=margin,
            leftMargin=margin,
            topMargin=margin,
            bottomMargin=margin,
            title="Bulletins scolaires",
            onFirstPage=_draw_page_border,
            onLaterPages=_draw_page_border,
        )
        story = []
        for index, bulletin in enumerate(bulletins):
            story.extend(
                _bulletin_story(
                    bulletin,
                    page_width - 2 * margin,
                    page_height - 2 * margin,
                    is_duplicate=is_duplicate,
                )
            )
            if index < len(bulletins) - 1:
                story.append(PageBreak())
        doc.build(story)
    else:
        page_size = landscape(A4)
        page_width, page_height = page_size
        outer_margin = 7 * mm
        gutter = 5 * mm
        frame_width = (page_width - 2 * outer_margin - gutter) / 2
        frame_height = page_height - 2 * outer_margin

        left = Frame(
            outer_margin,
            outer_margin,
            frame_width,
            frame_height,
            id="bulletin_left",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        right = Frame(
            outer_margin + frame_width + gutter,
            outer_margin,
            frame_width,
            frame_height,
            id="bulletin_right",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )

        def draw_separator(canvas, doc):
            _draw_page_border(canvas, doc)
            canvas.saveState()
            x = outer_margin + frame_width + gutter / 2
            canvas.setStrokeColor(colors.lightgrey)
            canvas.setLineWidth(0.4)
            canvas.line(x, outer_margin, x, page_height - outer_margin)
            canvas.restoreState()

        doc = BaseDocTemplate(
            buffer,
            pagesize=page_size,
            leftMargin=outer_margin,
            rightMargin=outer_margin,
            topMargin=outer_margin,
            bottomMargin=outer_margin,
            title="Bulletins scolaires",
        )
        doc.addPageTemplates([
            PageTemplate(
                id="two_up",
                frames=[left, right],
                onPage=draw_separator,
            )
        ])

        story = []
        for index in range(0, len(bulletins), 2):
            left_story = _bulletin_story(
                bulletins[index],
                frame_width,
                frame_height,
                is_duplicate=is_duplicate,
            )
            story.append(
                KeepInFrame(
                    frame_width,
                    frame_height,
                    left_story,
                    mode="shrink",
                )
            )
            story.append(FrameBreak())

            if index + 1 < len(bulletins):
                right_story = _bulletin_story(
                    bulletins[index + 1],
                    frame_width,
                    frame_height,
                    is_duplicate=is_duplicate,
                )
                story.append(
                    KeepInFrame(
                        frame_width,
                        frame_height,
                        right_story,
                        mode="shrink",
                    )
                )

            if index + 2 < len(bulletins):
                story.append(PageBreak())

        doc.build(story)

    if output is None:
        return buffer.getvalue()
    return output

def save_bulletins_pdf(bulletins, path, copies_per_page=1, is_duplicate=False):
    with open(path, "wb") as f:
        render_bulletins_pdf(
            bulletins,
            output=f,
            copies_per_page=copies_per_page,
            is_duplicate=is_duplicate,
        )



def save_bulletin_pdf(bulletin, path, copies_per_page=1, is_duplicate=False):
    with open(path, "wb") as f:
        render_bulletin_pdf(
            bulletin,
            output=f,
            copies_per_page=copies_per_page,
            is_duplicate=is_duplicate,
        )
