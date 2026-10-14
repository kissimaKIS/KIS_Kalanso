from .bulletin_appreciations import appreciation_for

def build_bulletin_context(bulletin):
    """Construit les données destinées au rendu/impression du bulletin."""
    mode = bulletin.display_mode()
    lines = bulletin.lignes()

    context = {
        "student": bulletin.enrollment.student,
        "classe": bulletin.enrollment.classe,
        "school_year": bulletin.enrollment.school_year,
        "period": bulletin.term,
        "mode": mode,
        "lines": lines,
        "moyenne_generale": bulletin.moyenne_generale(),
        "rang": bulletin.rang(),
        "observation_generale": bulletin.observation_generale,
    }

    if mode == "F1":
        context["columns"] = [
            ("subject", "Matière"),
            ("composition", "Note de composition /10"),
            ("moyenne", "Moyenne"),
            ("appreciation", "Appréciation"),
        ]
    else:
        context["columns"] = [
            ("subject", "Matière"),
            ("moyenne_de_classe", "Moyenne de classe"),
            ("note_de_composition", "Note de composition"),
            ("moyenne", "Moyenne"),
            ("coefficient", "Coefficient"),
            ("moyenne_coeff", "Moyenne coefficientée"),
            ("appreciation", "Appréciation"),
        ]
    return context
