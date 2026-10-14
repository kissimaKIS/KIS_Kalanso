from .license import LICENSE_END, LICENSE_LABEL, LICENSE_START, current_license_label, license_notice, license_status
from administration.models import School, SchoolYear


def school_context(request):
    from common.years import active_year
    school_year = active_year()
    school = school_year.school if school_year and school_year.school.is_active else School.objects.filter(is_active=True).first()
    if school_year and school and school_year.school_id != school.id:
        school_year = SchoolYear.objects.filter(school=school, is_active=True).first()
    return {
        "school": school,
        "school_year": school_year,
        "license_label": LICENSE_LABEL,
        "license_start": LICENSE_START,
        "license_end": LICENSE_END,
        "license_notice": license_notice(),
        "license_status": license_status(),
        "license_display_label": current_license_label(),
    }


def role_context(request):
    """Expose le rôle et les permissions de l'utilisateur aux gabarits.

    Usage : ``{% if "finance.manage" in kis_perms %}…{% endif %}``.
    """
    from administration.permissions import role_label, user_permissions

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"kis_perms": frozenset(), "kis_role_label": ""}
    return {"kis_perms": user_permissions(user), "kis_role_label": role_label(user)}
