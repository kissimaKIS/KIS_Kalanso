"""Matrice des rôles de KIS Kalanso.

Une permission décrit une capacité métier, indépendamment de l'URL qui
l'utilise. Le lien URL → permission est défini dans ``url_rules.py`` et
appliqué à toutes les pages par ``RoleAccessMiddleware``. Les menus, les
onglets et les cartes du tableau de bord s'appuient sur les mêmes
permissions : ce qu'un rôle ne peut pas ouvrir ne lui est pas montré.

Rôles (recette V3) :
- Administrateur, Promoteur, Gérant : tout ;
- Directeur : tout sauf le budget (corrections comprises) ;
- Corrections (suppression, annulation, changement de classe) : direction seulement ;
- Comptable : finance hors budget ;
- Directeur des études : scolarité, pédagogie (et vie scolaire) ;
- Secrétaire : scolarité, encaissements, impression des bulletins, communication ;
- Professeur : saisie de ses notes et suivi de ses affectations, sans finances ;
- Élève, Parent : rien pour l'instant.
"""
from administration.models import Role

# Capacités disponibles.
DASHBOARD_VIEW = "dashboard.view"
STUDENTS_VIEW = "students.view"          # consulter élèves et classes
STUDENTS_MANAGE = "students.manage"      # inscriptions, fiches, imports, cartes
PERSONNEL_MANAGE = "personnel.manage"    # enseignants et autre personnel
SALARIES_MANAGE = "salaries.manage"      # salaires du personnel
PEDAGOGY_MANAGE = "pedagogy.manage"      # périodes, évaluations, bulletins, référentiel, affectations
GRADES_ENTER = "grades.enter"            # saisie des notes (limitée à ses classes pour un professeur)
TEACHINGS_VIEW = "teachings.view"        # consulter les affectations
BULLETINS_PRINT = "bulletins.print"
SCHOOL_LIFE_MANAGE = "school_life.manage"
FINANCE_COLLECT = "finance.collect"      # encaissements, reçus
FINANCE_MANAGE = "finance.manage"        # frais, facturation, impayés, ajustements
BUDGET_MANAGE = "budget.manage"
COMMUNICATION_MANAGE = "communication.manage"
USERS_MANAGE = "users.manage"
SCHOOL_CONFIGURE = "school.configure"    # établissement, années scolaires
DATA_CORRECT = "data.correct"            # corrections : annuler un paiement, supprimer une facture/inscription, changer de classe

ALL_PERMISSIONS = frozenset({
    DASHBOARD_VIEW, STUDENTS_VIEW, STUDENTS_MANAGE, PERSONNEL_MANAGE,
    SALARIES_MANAGE, PEDAGOGY_MANAGE, GRADES_ENTER, TEACHINGS_VIEW,
    BULLETINS_PRINT, SCHOOL_LIFE_MANAGE, FINANCE_COLLECT, FINANCE_MANAGE,
    BUDGET_MANAGE, COMMUNICATION_MANAGE, USERS_MANAGE, SCHOOL_CONFIGURE,
    DATA_CORRECT,
})

TEACHER_PERMISSIONS = frozenset({DASHBOARD_VIEW, TEACHINGS_VIEW, GRADES_ENTER})

ROLE_PERMISSIONS = {
    Role.ADMIN: ALL_PERMISSIONS,
    Role.PROMOTER: ALL_PERMISSIONS,
    Role.MANAGER: ALL_PERMISSIONS,
    Role.DIRECTOR: ALL_PERMISSIONS - {BUDGET_MANAGE},
    Role.ACCOUNTANT: frozenset({
        DASHBOARD_VIEW, STUDENTS_VIEW, FINANCE_COLLECT, FINANCE_MANAGE, SALARIES_MANAGE,
    }),
    Role.STUDIES_DIRECTOR: frozenset({
        DASHBOARD_VIEW, STUDENTS_VIEW, STUDENTS_MANAGE, PEDAGOGY_MANAGE, GRADES_ENTER,
        TEACHINGS_VIEW, BULLETINS_PRINT, SCHOOL_LIFE_MANAGE,
    }),
    Role.SECRETARY: frozenset({
        DASHBOARD_VIEW, STUDENTS_VIEW, STUDENTS_MANAGE, FINANCE_COLLECT,
        BULLETINS_PRINT, COMMUNICATION_MANAGE,
    }),
    Role.TEACHER: TEACHER_PERMISSIONS,
    Role.PROF: TEACHER_PERMISSIONS,
    Role.STUDENT: frozenset(),
    Role.PARENT: frozenset(),
}

# Ordre d'affichage du rôle principal sous le nom de l'utilisateur.
ROLE_PRIORITY = [
    Role.ADMIN, Role.PROMOTER, Role.DIRECTOR, Role.MANAGER, Role.ACCOUNTANT,
    Role.STUDIES_DIRECTOR, Role.SECRETARY, Role.TEACHER, Role.PROF,
    Role.STUDENT, Role.PARENT,
]

# Rôles proposés dans le formulaire utilisateur (PROF est un doublon
# historique de TEACHER, conservé seulement pour les anciennes données).
ASSIGNABLE_ROLES = [role for role in ROLE_PRIORITY if role != Role.PROF]


def user_roles(user):
    """Rôles effectifs d'un utilisateur (nouveaux rôles + anciens indicateurs)."""
    if not getattr(user, "is_authenticated", False):
        return set()
    cached = getattr(user, "_kis_roles_cache", None)
    if cached is not None:
        return cached
    roles = set(user.assigned_roles()) if user.pk else set()
    if not roles:
        # Compatibilité : comptes antérieurs aux rôles multiples.
        if user.is_admin:
            roles.add(Role.ADMIN)
        if user.is_secretary:
            roles.add(Role.SECRETARY)
        if user.is_prof:
            roles.add(Role.TEACHER)
        if user.is_student:
            roles.add(Role.STUDENT)
    user._kis_roles_cache = roles
    return roles


def user_permissions(user):
    if not getattr(user, "is_authenticated", False):
        return frozenset()
    if user.is_superuser:
        return ALL_PERMISSIONS
    permissions = set()
    for role in user_roles(user):
        permissions |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(permissions)


def user_has_permission(user, permission):
    return permission in user_permissions(user)


def role_permissions(roles):
    permissions = set()
    for role in roles:
        permissions |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(permissions)


def role_label(user):
    """Libellé affiché sous le nom de l'utilisateur connecté."""
    roles = set(user_roles(user))
    if Role.PROF in roles:
        roles.discard(Role.PROF)
        roles.add(Role.TEACHER)
    labels = [Role(role).label for role in ROLE_PRIORITY if role in roles]
    if not labels and getattr(user, "is_superuser", False):
        return str(Role.ADMIN.label)
    if not labels:
        return "Aucun rôle"
    return " · ".join(str(label) for label in labels)


def teacher_scope(user):
    """Périmètre pédagogique d'un utilisateur.

    - ``None`` : aucune restriction (direction, directeur des études…) ;
    - une fiche ``Teacher`` : l'utilisateur ne voit que ses affectations ;
    - ``False`` : professeur dont le compte n'est rattaché à aucune fiche.
    """
    if user_has_permission(user, PEDAGOGY_MANAGE):
        return None
    from django.core.exceptions import ObjectDoesNotExist

    try:
        teacher = user.teacher_profile
    except (ObjectDoesNotExist, AttributeError):
        teacher = None
    return teacher or False
