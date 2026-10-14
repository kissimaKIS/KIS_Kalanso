from django import forms

from administration.models import Role, Teacher, User, UserRoleAssignment
from administration.permissions.access import ASSIGNABLE_ROLES, role_permissions, user_permissions

TEACHER_ROLES = {Role.TEACHER, Role.PROF}


class _UserRolesMixin:
    """Rôles proposés selon les droits de l'utilisateur qui crée le compte.

    Un utilisateur ne peut attribuer que des rôles dont les permissions sont
    comprises dans les siennes : un Directeur (tout sauf budget) ne peut donc
    pas créer un Promoteur ni s'octroyer l'accès au budget.
    """

    def _setup_roles(self, request_user):
        allowed = []
        granted = user_permissions(request_user) if request_user is not None else None
        for role in ASSIGNABLE_ROLES:
            if granted is None or role_permissions([role]) <= granted:
                allowed.append((role.value, role.label))
        self.fields["roles"].choices = allowed

        # Fiche enseignant rattachée au compte (rôle Professeur).
        current = getattr(self.instance, "teacher_profile", None) if self.instance.pk else None
        queryset = Teacher.objects.filter(is_active=True, user__isnull=True)
        if current is not None:
            queryset = Teacher.objects.filter(pk=current.pk) | queryset
        self.fields["teacher"].queryset = queryset.order_by("last_name", "first_name")
        if current is not None:
            self.fields["teacher"].initial = current.pk

    def clean(self):
        cleaned = super().clean()
        roles = set(cleaned.get("roles") or [])
        teacher = cleaned.get("teacher")
        if roles & TEACHER_ROLES and teacher is None:
            self.add_error("teacher", "Un compte Professeur doit être rattaché à sa fiche enseignant.")
        if teacher is not None and not roles & TEACHER_ROLES:
            self.add_error("teacher", "Seul un compte avec le rôle Professeur peut être rattaché à une fiche enseignant.")
        return cleaned

    def _link_teacher(self, user):
        teacher = self.cleaned_data.get("teacher")
        Teacher.objects.filter(user=user).exclude(pk=getattr(teacher, "pk", None)).update(user=None)
        if teacher is not None and teacher.user_id != user.pk:
            teacher.user = user
            teacher.save(update_fields=["user"])


def _roles_field():
    return forms.MultipleChoiceField(
        choices=[(role.value, role.label) for role in ASSIGNABLE_ROLES],
        widget=forms.CheckboxSelectMultiple,
        required=True,
        label="Rôles",
        help_text="Un utilisateur peut cumuler plusieurs rôles.",
    )


def _teacher_field():
    return forms.ModelChoiceField(
        queryset=Teacher.objects.none(),
        required=False,
        label="Fiche enseignant",
        help_text="Obligatoire pour le rôle Professeur : le compte ne verra que les affectations et les notes de cet enseignant.",
    )


class UserCreateForm(_UserRolesMixin, forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, min_length=8, label="Mot de passe")
    roles = _roles_field()
    teacher = _teacher_field()

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "roles", "teacher", "is_active"]

    def __init__(self, *args, request_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_roles(request_user)

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.set_password(self.cleaned_data["password"])
        roles = set(self.cleaned_data["roles"])
        _sync_user_roles(obj, roles, commit=commit)
        if commit:
            self._link_teacher(obj)
        return obj


class UserUpdateForm(_UserRolesMixin, forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput,
        min_length=8,
        required=False,
        label="Nouveau mot de passe",
        help_text="Laisser vide pour conserver le mot de passe actuel.",
    )
    roles = _roles_field()
    teacher = _teacher_field()

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "roles", "teacher", "is_active"]

    def __init__(self, *args, request_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_roles(request_user)
        if self.instance and self.instance.pk:
            roles = set(self.instance.assigned_roles())
            if Role.PROF in roles:
                roles.discard(Role.PROF)
                roles.add(Role.TEACHER)
            self.fields["roles"].initial = sorted(roles)

    def save(self, commit=True):
        # Le champ password du formulaire porte le même nom que le champ
        # modèle. Avec ModelForm, un champ vide pourrait donc écraser le
        # hash existant avant que nous ayons la possibilité de le préserver.
        original_password = self.instance.password if self.instance and self.instance.pk else None
        obj = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            obj.set_password(password)
        elif original_password:
            obj.password = original_password
        roles = set(self.cleaned_data["roles"])
        _sync_user_roles(obj, roles, commit=commit)
        if commit:
            self._link_teacher(obj)
        return obj


def _sync_user_roles(obj, roles, commit=True):
    # Les rôles multiples sont la source de vérité pour les nouveaux comptes.
    # Les anciens indicateurs restent synchronisés pour compatibilité.
    obj.is_admin = Role.ADMIN in roles
    obj.is_secretary = Role.SECRETARY in roles
    obj.is_prof = bool(roles & TEACHER_ROLES)
    obj.is_student = Role.STUDENT in roles
    # Accès à l'administration technique de Django réservé aux administrateurs.
    obj.is_staff = Role.ADMIN in roles or obj.is_superuser
    obj._kis_roles_cache = None

    if commit:
        obj.save()
        UserRoleAssignment.objects.filter(user=obj).exclude(role__in=roles).delete()
        UserRoleAssignment.objects.bulk_create(
            [UserRoleAssignment(user=obj, role=role) for role in roles],
            ignore_conflicts=True,
        )
