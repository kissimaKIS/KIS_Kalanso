"""Périmètre pédagogique d'un professeur.

Un utilisateur sans la permission « pedagogy.manage » mais avec la saisie des
notes est un professeur : il ne voit que les classes et matières de ses
affectations (Teaching). Une affectation sans matière (enseignant généraliste
ou titulaire de classe) donne accès à toutes les matières de la classe.
"""
from administration.permissions import teacher_scope


class TeacherScope:
    def __init__(self, user):
        self.teacher = teacher_scope(user)

    @property
    def unrestricted(self):
        return self.teacher is None

    def _teachings(self):
        from pedagogie.models import Teaching

        if not self.teacher:
            return Teaching.objects.none()
        return Teaching.objects.filter(teacher=self.teacher)

    def class_ids(self):
        """Ensemble des classes accessibles, ou None si aucune restriction."""
        if self.unrestricted:
            return None
        return set(self._teachings().values_list("classe_id", flat=True))

    def can_access_class(self, classe_id):
        ids = self.class_ids()
        return ids is None or classe_id in ids

    def subject_ids(self, classe_id):
        """Matières autorisées dans une classe : None = toutes."""
        if self.unrestricted:
            return None
        teachings = self._teachings().filter(classe_id=classe_id)
        if teachings.filter(subject__isnull=True).exists():
            return None
        return set(teachings.values_list("subject_id", flat=True))

    def can_access_subject(self, classe_id, subject_id):
        if not self.can_access_class(classe_id):
            return False
        allowed = self.subject_ids(classe_id)
        return allowed is None or subject_id in allowed
