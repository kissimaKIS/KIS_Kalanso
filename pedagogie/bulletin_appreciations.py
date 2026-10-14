from decimal import Decimal


APPRECIATION_THRESHOLDS_10 = (
    (Decimal("9"), "Excellent"),
    (Decimal("8"), "Très bien"),
    (Decimal("7"), "Bien"),
    (Decimal("6"), "Assez bien"),
    (Decimal("5"), "Passable"),
)

APPRECIATION_THRESHOLDS_20 = (
    (Decimal("18"), "Excellent"),
    (Decimal("16"), "Très bien"),
    (Decimal("14"), "Bien"),
    (Decimal("12"), "Assez bien"),
    (Decimal("10"), "Passable"),
)


def appreciation_for(note, scale):
    """Retourne l'appréciation automatique correspondant à une note."""
    if note is None:
        return ""

    note = Decimal(str(note))
    thresholds = (
        APPRECIATION_THRESHOLDS_10
        if scale == 10
        else APPRECIATION_THRESHOLDS_20
    )

    for minimum, label in thresholds:
        if note >= minimum:
            return label
    return "Insuffisant"
