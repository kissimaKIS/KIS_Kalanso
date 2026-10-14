from decimal import Decimal
from django.db import migrations, models


# Référentiel secondaire fourni par le terrain. Les niveaux LYC-10/11/12 et
# BT-1..4 restent des niveaux techniques historiques ; ils ne sont plus
# présentés comme des classes génériques dans l'interface. Les parcours
# ci-dessous sont les contextes réels utilisables pour créer les classes.
TRACKS = {
    "LY-10-GEN": {
        "name": "10ème Général", "kind": "series", "order": 1, "domain": "Enseignement secondaire général",
        "level": "LYC-10",
        "program": [
            ("FR", "Lettres (Français : Expression, Grammaire, Littérature)", 5, 3, "principal"),
            ("MATH", "Mathématiques (Algèbre, Géométrie)", 4, 3, "principal"),
            ("PHCH", "Physique - Chimie", 3, 2, "principal"),
            ("SVT", "Sciences de la Vie et de la Terre (SVT)", 2, 2, "secondary"),
            ("HG", "Histoire - Géographie", 3, 2, "secondary"),
            ("LV1", "Langue Vivante 1 (Anglais)", 3, 2, "secondary"),
            ("LV2", "Langue Vivante 2 (Arabe, Allemand ou Russe)", 2, 1, "secondary"),
            ("EPS", "Éducation Physique et Sportive (EPS)", 2, 1, "common"),
        ],
    },
    "LY-10-TECH": {
        "name": "10ème Technique", "kind": "series", "order": 2, "domain": "Enseignement secondaire technique",
        "level": "LYC-10",
        "program": [
            ("FR", "Français", 4, 2, "principal"),
            ("MATH", "Mathématiques (Algèbre renforcée, Trigonométrie)", 5, 4, "principal"),
            ("PHCH", "Physique - Chimie", 4, 3, "principal"),
            ("INITTECH", "Initiation à la Technologie & Dessin Technique", 4, 3, "principal"),
            ("HG", "Histoire - Géographie", 2, 1, "secondary"),
            ("LV1", "Langue Vivante 1 (Anglais)", 3, 2, "secondary"),
            ("ECO_DROIT", "Économie générale ou initiation à la gestion", 2, 2, "secondary"),
            ("EPS", "Éducation Physique et Sportive (EPS)", 2, 1, "common"),
        ],
    },
    "LY-11-L": {
        "name": "11ème Langues et Littératures (11ème LL)", "kind": "series", "order": 10, "domain": "Enseignement secondaire général", "level": "LYC-11",
        "program": [("FR", "Français / Lettres", 5, 4, "principal"), ("LV1", "Langue Vivante 1 (Anglais)", 4, 3, "principal"), ("LV2", "Langue Vivante 2 (Arabe, Allemand, Russe...)", 4, 3, "principal"), ("HG", "Histoire-Géographie", 3, 2, "secondary"), ("MATH", "Mathématiques", 2, 1, "secondary"), ("SVT", "Sciences de la Vie et de la Terre (SVT)", 2, 1, "secondary"), ("PHCH", "Physique-Chimie", 2, 1, "secondary"), ("EPS", "Éducation Physique et Sportive (EPS)", 2, 1, "common")],
    },
    "LY-11-SCI": {
        "name": "11ème Sciences Exactes (11ème SE)", "kind": "series", "order": 11, "domain": "Enseignement secondaire général", "level": "LYC-11",
        "program": [("MATH", "Mathématiques", 6, 5, "principal"), ("PHCH", "Physique-Chimie", 5, 4, "principal"), ("FR", "Français", 3, 2, "secondary"), ("LV1", "Langue Vivante 1 (Anglais)", 3, 2, "secondary"), ("HG", "Histoire-Géographie", 2, 1, "secondary"), ("SVT", "Sciences de la Vie et de la Terre (SVT)", 2, 1, "secondary"), ("EPS", "Éducation Physique et Sportive (EPS)", 2, 1, "common")],
    },
    "LY-11-SECO": {
        "name": "11ème Sciences Économiques (11ème SEco)", "kind": "series", "order": 12, "domain": "Enseignement secondaire général", "level": "LYC-11",
        "program": [("EOE", "Économie & Organisation des Entreprises", 4, 4, "principal"), ("MATH", "Mathématiques / Statistique", 4, 3, "principal"), ("COMPTA", "Comptabilité", 4, 3, "principal"), ("FR", "Français", 3, 2, "secondary"), ("HG", "Histoire-Géographie", 3, 2, "secondary"), ("LV1", "Langue Vivante 1 (Anglais)", 3, 2, "secondary"), ("EPS", "Éducation Physique et Sportive (EPS)", 2, 1, "common")],
    },
    "LY-11-STI": {
        "name": "11ème Sciences et Technologies Industrielles (11ème STI)", "kind": "series", "order": 20, "domain": "Enseignement secondaire technique", "level": "LYC-11",
        "program": [("GENIE", "Analyse Technique / Dessin Industriel / TP", 8, 5, "principal"), ("MATH", "Mathématiques", 5, 4, "principal"), ("PHCH", "Sciences Physiques", 4, 4, "principal"), ("FR", "Français", 3, 2, "secondary"), ("LV1", "Anglais Technique", 2, 2, "secondary"), ("HG", "Histoire-Géo / Instruction Civique", 2, 1, "secondary"), ("EPS", "Éducation Physique et Sportive (EPS)", 2, 1, "common")],
    },
    "LY-11-STG": {
        "name": "11ème Sciences et Technologies de la Gestion (11ème STG)", "kind": "series", "order": 21, "domain": "Enseignement secondaire technique", "level": "LYC-11",
        "program": [("COMPTA", "Sciences de Gestion & Informatique", 6, 4, "principal"), ("ECO_DROIT", "Économie et Droit", 4, 3, "principal"), ("MATHAPP", "Mathématiques Financières & Générales", 4, 3, "principal"), ("FR", "Français", 3, 2, "secondary"), ("LV1", "Langue Vivante 1 (Anglais)", 3, 2, "secondary"), ("HG", "Histoire-Géographie", 2, 1, "secondary"), ("EPS", "Éducation Physique et Sportive (EPS)", 2, 1, "common")],
    },
    "LY-TSE": {"name": "TSE", "kind": "series", "order": 30, "domain": "Enseignement secondaire général", "level": "LYC-12", "program": [("MATH", "Mathématiques", 6, 5, "principal"), ("PHCH", "Physique-Chimie", 6, 5, "principal"), ("FR", "Français / Littérature", 2, 2, "secondary"), ("PHILO", "Philosophie", 3, 2, "secondary"), ("HG", "Histoire-Géographie", 2, 1, "secondary"), ("LV1", "Langue Vivante 1", 3, 2, "secondary"), ("ARTDM", "Arts (Dessin/Musique)", 1, 1, "secondary"), ("EPS", "Éducation Physique et Sportive (EPS)", 2, 1, "common")]},
    "LY-TSEXP": {"name": "TSExp", "kind": "series", "order": 31, "domain": "Enseignement secondaire général", "level": "LYC-12", "program": [("MATH", "Mathématiques", 4, 3, "principal"), ("PHCH", "Physique-Chimie", 4, 4, "principal"), ("SVT", "SVT (Biologie)", 4, 4, "principal"), ("FR", "Français / Littérature", 2, 2, "secondary"), ("PHILO", "Philosophie", 3, 2, "secondary"), ("HG", "Histoire-Géographie", 2, 1, "secondary"), ("LV1", "Langue Vivante 1", 3, 2, "secondary"), ("ARTDM", "Arts (Dessin/Musique)", 1, 1, "secondary"), ("EPS", "Éducation Physique et Sportive (EPS)", 2, 1, "common")]},
    "LY-TSECO": {"name": "TSEco", "kind": "series", "order": 32, "domain": "Enseignement secondaire général", "level": "LYC-12", "program": [("MATH", "Mathématiques", 4, 4, "principal"), ("ECOGESTSOC", "Économie / Gestion / Comptabilité", 6, 5, "principal"), ("HG", "Histoire-Géographie", 3, 3, "principal"), ("PHILO", "Philosophie", 2, 2, "secondary"), ("FR", "Français", 3, 2, "secondary"), ("LV1", "Langue Vivante 1", 3, 2, "secondary"), ("EPS", "Éducation Physique (EPS)", 2, 1, "common")]},
    "LY-TSS": {"name": "TSS", "kind": "series", "order": 33, "domain": "Enseignement secondaire général", "level": "LYC-12", "program": [("MATH", "Mathématiques", 3, 2, "secondary"), ("HG", "Histoire-Géographie", 5, 4, "principal"), ("PHILO", "Philosophie", 4, 3, "principal"), ("ECOGESTSOC", "Sociologie / Éducation Civique", 2, 2, "secondary"), ("FR", "Français", 4, 3, "secondary"), ("LV1", "Langue Vivante 1", 3, 2, "secondary"), ("SVT", "Sciences de la Vie et de la Terre (SVT)", 2, 1, "secondary"), ("EPS", "Éducation Physique (EPS)", 2, 1, "common")]},
    "LY-TLL": {"name": "TLL", "kind": "series", "order": 34, "domain": "Enseignement secondaire général", "level": "LYC-12", "program": [("LITFR", "Lettres / Littérature", 5, 4, "principal"), ("PHILO", "Philosophie", 4, 4, "principal"), ("LV1", "Langue Vivante 1", 4, 3, "principal"), ("LV2", "Langue Vivante 2", 4, 3, "principal"), ("HG", "Histoire-Géographie", 2, 2, "secondary"), ("MATH", "Mathématiques", 2, 1, "secondary"), ("EPS", "Éducation Physique (EPS)", 2, 1, "common")]},
    "LY-TAL": {"name": "TAL", "kind": "series", "order": 35, "domain": "Enseignement secondaire général", "level": "LYC-12", "program": [("LITFR", "Lettres / Littérature", 4, 3, "principal"), ("PHILO", "Philosophie", 4, 3, "principal"), ("LV1", "Langue Vivante 1", 4, 3, "principal"), ("ARTDM", "Discipline Artistique Spécialisée", 6, 4, "principal"), ("HG", "Histoire-Géographie", 2, 1, "secondary"), ("MATH", "Mathématiques", 2, 1, "secondary"), ("EPS", "Éducation Physique (EPS)", 2, 1, "common")]},
    "LY-T-STI": {"name": "Terminale STI", "kind": "series", "order": 40, "domain": "Enseignement secondaire technique", "level": "LYC-12", "program": [("GENIE", "Analyse Technique (Construction / Mécanique / Électrique)", 8, 5, "principal"), ("MATH", "Mathématiques Spécifiques", 6, 4, "principal"), ("PHCH", "Sciences Physiques / Physique Appliquée", 5, 4, "principal"), ("FR", "Français / Philosophie", 3, 2, "secondary"), ("LV1", "Anglais Technique", 2, 2, "secondary"), ("HG", "Histoire-Géographie", 2, 1, "secondary"), ("EPS", "Éducation Physique et Sportive (EPS)", 2, 1, "common")]},
    "LY-T-STG": {"name": "Terminale STG", "kind": "series", "order": 41, "domain": "Enseignement secondaire technique", "level": "LYC-12", "program": [("COMPTA", "Comptabilité et Sciences de Gestion", 6, 5, "principal"), ("ECO_DROIT", "Économie & Droit", 5, 4, "principal"), ("MATHAPP", "Mathématiques Financières & Générales", 5, 4, "principal"), ("FR", "Français / Philosophie", 3, 2, "secondary"), ("ANGCOMM", "Anglais Commercial / Langue", 3, 2, "secondary"), ("HG", "Histoire-Géographie", 2, 2, "secondary"), ("EPS", "Éducation Physique et Sportive (EPS)", 2, 1, "common")]},
}

# Spécialités BT réellement présentes dans le document terrain.
BT_TRACKS = {
    "BT-ELECTROMECANIQUE": ("BT Électromécanique / Électricité Industrielle", "Industriel et technique"),
    "BT-GENIE-CIVIL": ("BT Génie Civil / Dessinateur-Projeteur Bâtiment", "Industriel et technique"),
    "BT-COMPTA-GESTION": ("BT Comptabilité-Gestion", "Tertiaire"),
    "BT-SECRETARIAT": ("BT Secrétariat de Direction", "Tertiaire"),
}
BT_PROGRAMS = {
"BT-ELECTROMECANIQUE": [("Technologie Électrique & Mécanique",4,4), ("Schémas, Automatismes & CAO",3,3), ("Travaux Pratiques en Atelier & Labos",12,6), ("Mathématiques Appliquées & Phys. Indus.",4,3), ("Français, Économie & Législation",3,2), ("Anglais Technique",1,1)],
"BT-GENIE-CIVIL": [("Résistance des Matériaux & Statique",2,4), ("Technologie de Construction & Topo",4,3), ("Dessin d’Architecture & DAO (AutoCAD)",6,4), ("Pratiques professionnelles / Chantiers",8,5), ("Métré, Devis & Planification",2,3), ("Matières Générales (Maths, Fr, Anglais)",6,2)],
"BT-COMPTA-GESTION": [("Comptabilité Générale / Analytique / Sociétés",6,5), ("Gestion Financière & Fiscalité",2,4), ("Mathématiques Financières & Statistiques",3,3), ("Informatique de Gestion & Logiciels",3,3), ("Économie Générale, Éco d'Entreprise & Droit",4,3), ("Français Professionnel & Correspondance",4,2), ("Anglais Commercial",2,2)],
"BT-SECRETARIAT": [("Organisation & Techniques de Secrétariat",4,4), ("Bureautique avancée (Word, Excel, PPT, Web)",6,4), ("Expression Écrite, Administrative & Fr",5,3), ("Droit social, civil, commercial & Éco",3,2), ("Anglais Commercial & Pratique de l'Oral",3,3), ("Comptabilité Élémentaire & Statistique",3,2)],
}
BT_HOURS = {
"BT-ELECTROMECANIQUE": [[4,3,12,4,3,1],[4,3,14,4,3,1],[4,4,14,3,2,2],[4,4,16,3,2,2]],
"BT-GENIE-CIVIL": [[2,4,6,8,2,6],[3,4,6,8,2,5],[4,3,8,10,3,4],[4,3,8,10,4,4]],
"BT-COMPTA-GESTION": [[6,2,3,3,4,4,2],[6,3,3,4,4,3,2],[6,4,3,4,4,3,2],[7,4,3,4,4,2,2]],
"BT-SECRETARIAT": [[4,6,5,3,3,3],[4,6,5,3,3,3],[5,6,4,4,3,2],[5,6,4,4,4,2]],
}


def get_subject(Subject, code, name):
    obj = Subject.objects.filter(code=code).first()
    if not obj:
        # Keep one internal reference where an existing code already exists;
        # names shown to users are always stored on the contextual link.
        obj = Subject.objects.create(code=code, name=name, coefficient=1, is_active=True)
    return obj


def upsert_program(TrackLevelSubject, Subject, tl, rows, app_names=False):
    for idx, row in enumerate(rows, 1):
        if app_names:
            name, hours, coeff = row
            code = "PRO-" + str(abs(hash(name)) % 900000 + 100000)
            subj = Subject.objects.filter(name__iexact=name).first() or Subject.objects.filter(code=code).first()
            if not subj:
                subj = Subject.objects.create(code=code, name=name, coefficient=1, is_active=True)
        else:
            code, name, hours, coeff, role = row
            subj = get_subject(Subject, code, name)
        TrackLevelSubject.objects.update_or_create(
            track_level=tl, subject=subj,
            defaults={"name": name, "weekly_hours": Decimal(str(hours)), "coefficient": Decimal(str(coeff)), "role": (row[4] if not app_names else "secondary"), "is_required": True, "order": idx, "is_active": True},
        )


def seed(apps, schema_editor):
    EducationLevel = apps.get_model("pedagogie", "EducationLevel")
    Subject = apps.get_model("pedagogie", "Subject")
    PedagogicalTrack = apps.get_model("pedagogie", "PedagogicalTrack")
    TrackLevel = apps.get_model("pedagogie", "TrackLevel")
    TrackLevelSubject = apps.get_model("pedagogie", "TrackLevelSubject")
    SchoolYear = apps.get_model("administration", "SchoolYear")
    SchoolYearTrack = apps.get_model("pedagogie", "SchoolYearTrack")

    # The generic secondary/professional level names are retained only as
    # technical compatibility anchors. They are no longer shown as choices.
    generic_codes = ["LYC-10", "LYC-11", "LYC-12", "CAP-1", "CAP-2", "BT-1", "BT-2", "BT-3", "BT-4"]
    EducationLevel.objects.filter(code__in=generic_codes).update(is_active=True)

    # Remove old generic/unsupported secondary tracks from the active catalogue.
    PedagogicalTrack.objects.filter(school_type__in=["high_school", "vocational"]).update(is_active=False)

    # Secondary tracks from the terrain documents.
    for code, meta in TRACKS.items():
        track, _ = PedagogicalTrack.objects.get_or_create(
            code=code,
            defaults={"name": meta["name"], "school_type": "high_school", "kind": meta["kind"], "order": meta["order"], "is_active": True, "domain": meta["domain"]},
        )
        track.name, track.kind, track.order, track.is_active, track.domain = meta["name"], meta["kind"], meta["order"], True, meta["domain"]
        track.save(update_fields=["name","kind","order","is_active","domain"])
        levels = meta["level"] if isinstance(meta["level"], list) else [meta["level"]]
        for level_code in levels:
            level = EducationLevel.objects.get(code=level_code)
            tl, _ = TrackLevel.objects.get_or_create(track=track, education_level=level, defaults={"order": level.order, "is_active": True})
            tl.is_active = True; tl.save(update_fields=["is_active"])
            # For STI/STG 11th programs, source and terminal programs differ;
            # the shared 11th track uses the 11th programme, while terminal
            # tracks below use their terminal programme.
            upsert_program(TrackLevelSubject, Subject, tl, meta["program"])

    # Dedicated terminal technical tracks: separate real terminal contexts.
    for code, source_code in [("LY-T-STI", "LY-T-STI"), ("LY-T-STG", "LY-T-STG")]:
        meta = TRACKS[code]
        track = PedagogicalTrack.objects.get(code=code)
        tl = TrackLevel.objects.get(track=track, education_level__code="LYC-12")
        upsert_program(TrackLevelSubject, Subject, tl, meta["program"])


    # Correct BT specialties, four years each, with exact hours from terrain.
    for bt_order, (code, (name, domain)) in enumerate(BT_TRACKS.items(), start=1):
        track = PedagogicalTrack.objects.get(code=code)
        track.name, track.domain, track.is_active, track.kind, track.order = name, domain, True, "training", bt_order
        track.save(update_fields=["name","domain","is_active","kind","order"])
        for i, level_code in enumerate(["BT-1","BT-2","BT-3","BT-4"]):
            level = EducationLevel.objects.get(code=level_code)
            tl, _ = TrackLevel.objects.get_or_create(track=track, education_level=level, defaults={"order": level.order, "is_active": True})
            tl.is_active=True; tl.save(update_fields=["is_active"])
            rows = BT_PROGRAMS[code]
            hours = BT_HOURS[code][i]
            prepared = []
            for j, (name_s, _h, coeff) in enumerate(rows):
                # Reuse/create an internal reference; contextual display name is on link.
                subj = Subject.objects.filter(name__iexact=name_s).first()
                if not subj:
                    safe = "BT-" + code.replace("BT-", "")[:12] + "-" + str(j+1)
                    while Subject.objects.filter(code=safe).exists(): safe += "X"
                    subj = Subject.objects.create(code=safe, name=name_s, coefficient=1, is_active=True)
                prepared.append((subj, name_s, hours[j], coeff))
            for idx, (subj, name_s, h, coeff) in enumerate(prepared, 1):
                TrackLevelSubject.objects.update_or_create(track_level=tl, subject=subj, defaults={"name": name_s, "weekly_hours": Decimal(str(h)), "coefficient": Decimal(str(coeff)), "role": "secondary", "is_required": True, "order": idx, "is_active": True})

    # CAP: only the two branches explicitly present in the supplied document.
    cap_programs = {
        "CAP-INDUSTRIE": [("Travaux Pratiques / Atelier (Spécialité)",14,5),("Technologie / Schéma / Dessin Technique",4,3),("Mathématiques Appliquées & Sciences",3,2),("Français / Expression Rédactionnelle",2,2),("Législation du travail / Civisme",1,1),("Anglais Technique",1,1)],
        "CAP-TERTIAIRE": [("Techniques Professionnelles (Compta / Secrétariat)",8,4),("Bureautique & Informatique",4,3),("Mathématiques Commerciales / Statistiques",3,2),("Français Administratif & Correspondance",4,3),("Économie générale & Organisation des Entreprises",2,2),("Anglais Commercial",2,1)],
    }
    for code, program in cap_programs.items():
        track = PedagogicalTrack.objects.get(code=code)
        track.is_active=True; track.kind="training"; track.domain="Industrie" if code.endswith("INDUSTRIE") else "Tertiaire"; track.save(update_fields=["is_active","kind","domain"])
        for level_code in ["CAP-1","CAP-2"]:
            tl=TrackLevel.objects.get(track=track, education_level__code=level_code)
            for idx,(name_s,h,coeff) in enumerate(program,1):
                subj=Subject.objects.filter(name__iexact=name_s).first()
                if not subj:
                    safe="CAP-"+code[-8:]+"-"+str(idx)
                    while Subject.objects.filter(code=safe).exists(): safe+="X"
                    subj=Subject.objects.create(code=safe,name=name_s,coefficient=1,is_active=True)
                TrackLevelSubject.objects.update_or_create(track_level=tl,subject=subj,defaults={"name":name_s,"weekly_hours":Decimal(str(h)),"coefficient":Decimal(str(coeff)),"role":"secondary","is_required":True,"order":idx,"is_active":True})

    # Les anciens parcours génériques restent uniquement comme ancres techniques
    # pour la compatibilité des données historiques. Ils ne doivent jamais être
    # ouverts dans une année scolaire ni apparaître dans le catalogue.
    generic_track_codes = [
        "BT-TERTIAIRE", "BT-INDUSTRIEL",
        "LYC-10-GEN", "LYC-10-TECH",
        "LYC-11-GEN", "LYC-11-TECH",
        "LYC-12-GEN", "LYC-12-TECH",
    ]
    SchoolYearTrack.objects.filter(track__code__in=generic_track_codes).update(is_active=False)

    # Synchroniser les années déjà présentes avec les contextes réels actifs.
    active_tracks = PedagogicalTrack.objects.filter(is_active=True, school_type__in=["high_school", "vocational"])
    for year in SchoolYear.objects.all():
        for track in active_tracks.filter(school_type=year.school.school_type):
            SchoolYearTrack.objects.update_or_create(school_year=year, track=track, defaults={"is_active": True})
        SchoolYearTrack.objects.filter(school_year=year, track__school_type=year.school.school_type).exclude(track__in=active_tracks.filter(school_type=year.school.school_type)).update(is_active=False)


def reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("pedagogie", "0028_contextual_subjects")]
    operations = [
        migrations.RemoveConstraint(model_name="educationlevel", name="unique_level_order_per_school_type"),
        migrations.AddField(model_name="pedagogicaltrack", name="domain", field=models.CharField(blank=True, default="", max_length=120, verbose_name="Domaine")),
        migrations.RunPython(seed, reverse),
    ]
