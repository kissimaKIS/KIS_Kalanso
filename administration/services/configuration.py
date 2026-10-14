from administration.models import School, SchoolYear


def school_configuration_checklist(school):
    """Return the minimal configuration checklist for an establishment.

    The checklist informs the administrator without imposing optional values
    (such as logo or official labels) as mandatory business rules.
    """
    active_types = set(school.enabled_school_types())
    requires_cap = bool(active_types & {
        School.SchoolType.FUNDAMENTAL_1,
        School.SchoolType.FUNDAMENTAL_2,
    })
    active_year = SchoolYear.objects.filter(
        school=school, is_active=True, is_closed=False
    ).first()

    items = [
        {
            "key": "identity",
            "label": "Identité de l'établissement",
            "complete": bool(school.name.strip() and school.code.strip()),
        },
        {
            "key": "sectors",
            "label": "Types d'enseignement",
            "complete": bool(active_types),
        },
        {
            "key": "school_year",
            "label": "Année scolaire active",
            "complete": active_year is not None,
        },
        {
            "key": "catalog",
            "label": "Référentiel pédagogique de l'année",
            "complete": bool(active_year and active_year.catalog_is_validated),
        },
    ]
    if requires_cap:
        items.append({
            "key": "cap",
            "label": "CAP",
            "complete": bool(school.cap_name.strip()),
            "optional": True,
            "help": "Renseignez le CAP si votre établissement relève de la Fondamentale 1 ou 2.",
        })

    return {
        "items": items,
        "complete_required": all(item["complete"] for item in items if not item.get("optional")),
        "active_year": active_year,
    }
