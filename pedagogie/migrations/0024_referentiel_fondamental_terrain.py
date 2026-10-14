from decimal import Decimal
from django.db import migrations


F1 = {
    "F1-1": [("Chant", 1), ("Dessin", 1), ("Ecriture", 2), ("Education physique", 1), ("Exercices sensoriels", 1), ("Initiation orthographe", 1), ("Langage", 6), ("Lecture", 6), ("Mathématiques", 6), ("Récitation", 1)],
    "F1-2": [("Chant", 1), ("Dessin", 1), ("Ecriture", 2), ("Education physique", 1), ("Exercices sensoriels", 1), ("Initiation orthographe", 1), ("Langage", 6), ("Lecture", 6), ("Mathématiques", 6), ("Récitation", 1)],
    "F1-3": [("Chant", 1), ("Conjugaison", 2), ("Dessin", 1), ("Dictée de contrôle", 1), ("Dictée préparée", 1), ("Economie Familiale", 1), ("Ecriture", 3), ("Education Civique et Morale", 1), ("Education Physique", 1), ("Elocution", 2), ("Géométrie", 1), ("Grammaire", 2), ("Lecture", 3), ("Mesure", 1), ("Numération", 1), ("Opération", 1), ("Problèmes Pratiques", 1), ("Récitation", 1), ("Vocabulaire", 1)],
    "F1-4": [("Chant", .5), ("Conjugaison", 1), ("Dessin", .5), ("Dictée de contrôle", .5), ("Dictée préparée", 1), ("Economie Familiale", .5), ("Ecriture", 1), ("Education Civique et Morale", 1), ("Education Physique", 1), ("Elocution", 1), ("Expression écrite", .5), ("Géographie", .5), ("Géométrie", 1), ("Grammaire", 1), ("Histoire", .5), ("Lecture", 4), ("Mesure", 2), ("Numération", 2), ("Opération", 1), ("Problèmes Pratiques", 2), ("Récitation", 1), ("Sciences d'observation", .5), ("Technologie", 1), ("Vocabulaire", 1)],
    "F1-5": [("Chant", .5), ("Conjugaison", .5), ("Dessin", .5), ("Dictée de contrôle", .5), ("Dictée préparée", 1), ("Economie Familiale", .5), ("Ecriture", .5), ("Education Civique et Morale", 1), ("Education Physique", 1), ("Elocution", 1), ("Expression écrite", .5), ("Géographie", .5), ("Géométrie", 1), ("Grammaire", 1), ("Histoire", .5), ("Lecture", 4), ("Mesure", 2), ("Numération", 2), ("Opération", 1), ("Problèmes Pratiques", 1), ("Récitation", 1), ("Sciences", 1), ("Technologie", 1), ("Vocabulaire", 2), ("Rédaction", .5)],
    "F1-6": [("Chant", .5), ("Conjugaison", .5), ("Dessin", .5), ("Dictée de contrôle", .5), ("Dictée préparée", 1), ("Economie Familiale", .5), ("Ecriture", .5), ("Education Civique et Morale", 1), ("Education Physique", 1), ("Elocution", 1), ("Expression écrite", .5), ("Géographie", .5), ("Géométrie", 1), ("Grammaire", 1), ("Histoire", .5), ("Lecture", 4), ("Mesure", 2), ("Numération", 2), ("Opération", 1), ("Problèmes Pratiques", 1), ("Récitation", 1), ("Sciences", 1), ("Technologie", 1), ("Vocabulaire", 2), ("Rédaction", .5)],
}

F2 = {
    "F2-7": [("Rédaction", 2), ("Dictée et question", 2), ("Lecture", 1), ("Récitation", 1), ("Mathématiques", 5), ("Physique", 1.5), ("Biologie", 2), ("Chimie", 1.5), ("Histoire et Géographie", 2), ("Education Civique et Morale", 1), ("Anglais", 2), ("Dessin", 1), ("Education Physique et Sportive", 1), ("Français", 3)],
    "F2-8": [("Rédaction", 2), ("Dictée et question", 2), ("Lecture", 1), ("Récitation", 1), ("Mathématiques", 5), ("Physique", 1.5), ("Biologie", 2), ("Chimie", 1.5), ("Histoire et Géographie", 2), ("Education Civique et Morale", 1), ("Anglais", 2), ("Dessin", 1), ("Education Physique et Sportive", 1), ("Français", 3)],
    "F2-9": [("Rédaction", 2), ("Dictée et question", 2), ("Lecture", 1), ("Récitation", 1), ("Mathématiques", 6), ("Physique", 1.5), ("Biologie", 2), ("Chimie", 1.5), ("Histoire et Géographie", 2), ("Education Civique et Morale", 1), ("Anglais", 2), ("Dessin", 1), ("Education Physique et Sportive", 1), ("Français", 3)],
}


def seed(apps, schema_editor):
    EducationLevel = apps.get_model("pedagogie", "EducationLevel")
    Subject = apps.get_model("pedagogie", "Subject")
    EducationLevelSubject = apps.get_model("pedagogie", "EducationLevelSubject")

    # Le référentiel terrain remplace les anciennes associations F1/F2.
    EducationLevelSubject.objects.filter(
        education_level__school_type__in=["fundamental_1", "fundamental_2"]
    ).update(is_active=False)

    subject_by_name = {}
    counter = 1
    all_names = []
    for program in list(F1.values()) + list(F2.values()):
        all_names.extend(name for name, _ in program)
    for name in dict.fromkeys(all_names):
        subject = Subject.objects.filter(name__iexact=name).first()
        if subject is None:
            code = "REF-" + str(counter).zfill(3)
            counter += 1
            while Subject.objects.filter(code=code).exists():
                counter += 1
                code = "REF-" + str(counter).zfill(3)
            subject = Subject.objects.create(code=code, name=name, coefficient=1, is_active=True)
        subject_by_name[name] = subject

    for level_code, program in {**F1, **F2}.items():
        level = EducationLevel.objects.get(code=level_code)
        for order, (name, hours) in enumerate(program, 1):
            EducationLevelSubject.objects.update_or_create(
                education_level=level,
                subject=subject_by_name[name],
                defaults={
                    "weekly_hours": Decimal(str(hours)),
                    "coefficient": Decimal(str({
                        "Rédaction": 3, "Dictée et question": 2, "Lecture": 1, "Récitation": 1,
                        "Mathématiques": 3 if level_code != "F2-9" else 3, "Physique": 1.5, "Biologie": 2,
                        "Chimie": 1.5, "Histoire et Géographie": 2, "Education Civique et Morale": 1,
                        "Anglais": 2, "Dessin": 1, "Education Physique et Sportive": 1, "Français": 1,
                    }.get(name, 1) if level_code.startswith("F2-") else 1)),
                    "role": "secondary",
                    "is_required": True,
                    "order": order,
                    "is_active": True,
                },
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("pedagogie", "0023_decimal_coefficients")]
    operations = [migrations.RunPython(seed, noop)]
