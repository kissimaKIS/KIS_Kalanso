from decimal import Decimal
from django.db import migrations


PROGRAMS = {
    "CAP-INDUSTRIE": {
        "CAP-1": [("Travaux Pratiques / Atelier (Spécialité)", 14, 5), ("Technologie / Schéma / Dessin Technique", 4, 3), ("Mathématiques Appliquées & Sciences", 3, 2), ("Français / Expression Rédactionnelle", 2, 2), ("Législation du travail / Civisme", 1, 1), ("Anglais Technique", 1, 1)],
        "CAP-2": [("Travaux Pratiques / Atelier (Soutenance/Stage)", 16, 6), ("Technologie et Dessin de Spécialité", 4, 3), ("Mathématiques Appliquées & Sciences", 2, 2), ("Français Professionnel", 2, 1), ("Hygiène et Sécurité au Travail", 1, 1), ("Anglais Technique", 1, 1)],
    },
    "CAP-TERTIAIRE": {
        "CAP-1": [("Techniques Professionnelles (Compta / Secrétariat)", 8, 4), ("Bureautique & Informatique", 4, 3), ("Mathématiques Commerciales / Statistiques", 3, 2), ("Français Administratif & Correspondance", 4, 3), ("Économie générale & Organisation des Entreprises", 2, 2), ("Anglais Commercial", 2, 1)],
        "CAP-2": [("Techniques Professionnelles & Pratiques", 10, 5), ("Bureautique / Traitement de texte avancé", 4, 3), ("Mathématiques Financières", 3, 2), ("Français Professionnel", 3, 2), ("Droit du travail & Fiscalité de base", 2, 2), ("Anglais Commercial", 2, 1)],
    },
    "BT-ELECTROMECANIQUE": {
        "BT-1": [("Technologie Électrique & Mécanique", 4, 4), ("Schémas, Automatismes & CAO", 3, 3), ("Travaux Pratiques en Atelier & Labos", 12, 6), ("Mathématiques Appliquées & Phys. Indus.", 4, 3), ("Français, Économie & Législation", 3, 2), ("Anglais Technique", 1, 1)],
        "BT-2": [("Technologie Électrique & Mécanique", 4, 4), ("Schémas, Automatismes & CAO", 3, 3), ("Travaux Pratiques en Atelier & Labos", 14, 6), ("Mathématiques Appliquées & Phys. Indus.", 4, 3), ("Français, Économie & Législation", 3, 2), ("Anglais Technique", 1, 1)],
        "BT-3": [("Technologie Électrique & Mécanique", 4, 4), ("Schémas, Automatismes & CAO", 4, 3), ("Travaux Pratiques en Atelier & Labos", 14, 6), ("Mathématiques Appliquées & Phys. Indus.", 3, 3), ("Français, Économie & Législation", 2, 2), ("Anglais Technique", 2, 1)],
        "BT-4": [("Technologie Électrique & Mécanique", 4, 4), ("Schémas, Automatismes & CAO", 4, 3), ("Travaux Pratiques en Atelier & Labos", 16, 6), ("Mathématiques Appliquées & Phys. Indus.", 3, 3), ("Français, Économie & Législation", 2, 2), ("Anglais Technique", 2, 1)],
    },
    "BT-GENIE-CIVIL": {
        "BT-1": [("Résistance des Matériaux & Statique", 2, 4), ("Technologie de Construction & Topo", 4, 3), ("Dessin d'Architecture & DAO (AutoCAD)", 6, 4), ("Pratiques professionnelles / Chantiers", 8, 5), ("Métré, Devis & Planification", 2, 3), ("Matières Générales (Maths, Fr, Anglais)", 6, 2)],
        "BT-2": [("Résistance des Matériaux & Statique", 3, 4), ("Technologie de Construction & Topo", 4, 3), ("Dessin d'Architecture & DAO (AutoCAD)", 6, 4), ("Pratiques professionnelles / Chantiers", 8, 5), ("Métré, Devis & Planification", 2, 3), ("Matières Générales (Maths, Fr, Anglais)", 5, 2)],
        "BT-3": [("Résistance des Matériaux & Statique", 4, 4), ("Technologie de Construction & Topo", 3, 3), ("Dessin d'Architecture & DAO (AutoCAD)", 8, 4), ("Pratiques professionnelles / Chantiers", 10, 5), ("Métré, Devis & Planification", 3, 3), ("Matières Générales (Maths, Fr, Anglais)", 4, 2)],
        "BT-4": [("Résistance des Matériaux & Statique", 4, 4), ("Technologie de Construction & Topo", 3, 3), ("Dessin d'Architecture & DAO (AutoCAD)", 8, 4), ("Pratiques professionnelles / Chantiers", 10, 5), ("Métré, Devis & Planification", 4, 3), ("Matières Générales (Maths, Fr, Anglais)", 4, 2)],
    },
    "BT-COMPTA-GESTION": {
        "BT-1": [("Comptabilité Générale / Analytique / Sociétés", 6, 5), ("Gestion Financière & Fiscalité", 2, 4), ("Mathématiques Financières & Statistiques", 3, 3), ("Informatique de Gestion & Logiciels", 3, 3), ("Économie Générale, Éco d'Entreprise & Droit", 4, 3), ("Français Professionnel & Correspondance", 4, 2), ("Anglais Commercial", 2, 2)],
        "BT-2": [("Comptabilité Générale / Analytique / Sociétés", 6, 5), ("Gestion Financière & Fiscalité", 3, 4), ("Mathématiques Financières & Statistiques", 3, 3), ("Informatique de Gestion & Logiciels", 4, 3), ("Économie Générale, Éco d'Entreprise & Droit", 4, 3), ("Français Professionnel & Correspondance", 3, 2), ("Anglais Commercial", 2, 2)],
        "BT-3": [("Comptabilité Générale / Analytique / Sociétés", 6, 5), ("Gestion Financière & Fiscalité", 4, 4), ("Mathématiques Financières & Statistiques", 3, 3), ("Informatique de Gestion & Logiciels", 4, 3), ("Économie Générale, Éco d'Entreprise & Droit", 4, 3), ("Français Professionnel & Correspondance", 3, 2), ("Anglais Commercial", 2, 2)],
        "BT-4": [("Comptabilité Générale / Analytique / Sociétés", 7, 5), ("Gestion Financière & Fiscalité", 4, 4), ("Mathématiques Financières & Statistiques", 3, 3), ("Informatique de Gestion & Logiciels", 4, 3), ("Économie Générale, Éco d'Entreprise & Droit", 4, 3), ("Français Professionnel & Correspondance", 2, 2), ("Anglais Commercial", 2, 2)],
    },
    "BT-SECRETARIAT": {
        "BT-1": [("Organisation & Techniques de Secrétariat", 4, 4), ("Bureautique avancée (Word, Excel, PPT, Web)", 6, 4), ("Expression Écrite, Administrative & Fr", 5, 3), ("Droit social, civil, commercial & Éco", 3, 2), ("Anglais Commercial & Pratique de l'Oral", 3, 3), ("Comptabilité Élémentaire & Statistique", 3, 2)],
        "BT-2": [("Organisation & Techniques de Secrétariat", 4, 4), ("Bureautique avancée (Word, Excel, PPT, Web)", 6, 4), ("Expression Écrite, Administrative & Fr", 5, 3), ("Droit social, civil, commercial & Éco", 3, 2), ("Anglais Commercial & Pratique de l'Oral", 3, 3), ("Comptabilité Élémentaire & Statistique", 3, 2)],
        "BT-3": [("Organisation & Techniques de Secrétariat", 5, 4), ("Bureautique avancée (Word, Excel, PPT, Web)", 6, 4), ("Expression Écrite, Administrative & Fr", 4, 3), ("Droit social, civil, commercial & Éco", 4, 2), ("Anglais Commercial & Pratique de l'Oral", 3, 3), ("Comptabilité Élémentaire & Statistique", 2, 2)],
        "BT-4": [("Organisation & Techniques de Secrétariat", 5, 4), ("Bureautique avancée (Word, Excel, PPT, Web)", 6, 4), ("Expression Écrite, Administrative & Fr", 4, 3), ("Droit social, civil, commercial & Éco", 4, 2), ("Anglais Commercial & Pratique de l'Oral", 4, 3), ("Comptabilité Élémentaire & Statistique", 2, 2)],
    },
}

TRACK_META = {
    "CAP-INDUSTRIE": ("CAP Industrie", "training", 40),
    "CAP-TERTIAIRE": ("CAP Tertiaire", "training", 41),
    "BT-ELECTROMECANIQUE": ("BT Électromécanique / Électricité Industrielle", "training", 50),
    "BT-GENIE-CIVIL": ("BT Génie Civil / Dessinateur-Projeteur Bâtiment", "training", 51),
    "BT-COMPTA-GESTION": ("BT Comptabilité-Gestion", "training", 52),
    "BT-SECRETARIAT": ("BT Secrétariat de Direction", "training", 53),
}


def seed(apps, schema_editor):
    EducationLevel = apps.get_model("pedagogie", "EducationLevel")
    Subject = apps.get_model("pedagogie", "Subject")
    PedagogicalTrack = apps.get_model("pedagogie", "PedagogicalTrack")
    TrackLevel = apps.get_model("pedagogie", "TrackLevel")
    TrackLevelSubject = apps.get_model("pedagogie", "TrackLevelSubject")

    for code, name, order in [("BT-3", "BT 3", 5), ("BT-4", "BT 4", 6)]:
        EducationLevel.objects.get_or_create(
            code=code,
            defaults={
                "name": name, "school_type": "vocational", "order": order,
                "is_exam_level": True, "exam_name": code.replace("-", ""),
                "allows_free_candidate": True, "teaching_organization": "subject_based", "is_active": True,
            },
        )

    subjects = {}
    names = []
    for programs in PROGRAMS.values():
        for items in programs.values():
            names.extend(name for name, _hours, _coef in items)
    for name in dict.fromkeys(names):
        subject = Subject.objects.filter(name__iexact=name).first()
        if subject is None:
            code = "PRO-" + str(len(subjects) + 1).zfill(3)
            while Subject.objects.filter(code=code).exists():
                code = "PRO-" + str(int(code.split("-")[-1]) + 1).zfill(3)
            subject = Subject.objects.create(code=code, name=name, coefficient=1, is_active=True)
        subjects[name] = subject

    for code, (name, kind, order) in TRACK_META.items():
        track, _ = PedagogicalTrack.objects.get_or_create(
            code=code,
            defaults={"name": name, "school_type": "vocational", "kind": kind, "order": order, "is_active": True},
        )
        for level_code in PROGRAMS[code]:
            level = EducationLevel.objects.get(code=level_code)
            track_level, _ = TrackLevel.objects.get_or_create(
                track=track, education_level=level,
                defaults={"order": level.order, "is_active": True},
            )
            for order_idx, (subject_name, hours, coefficient) in enumerate(PROGRAMS[code][level_code], 1):
                TrackLevelSubject.objects.update_or_create(
                    track_level=track_level, subject=subjects[subject_name],
                    defaults={
                        "weekly_hours": Decimal(str(hours)),
                        "coefficient": Decimal(str(coefficient)),
                        "role": "secondary",
                        "is_required": True, "order": order_idx, "is_active": True,
                    },
                )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("pedagogie", "0024_referentiel_fondamental_terrain")]
    operations = [migrations.RunPython(seed, noop)]
