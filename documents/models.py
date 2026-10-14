from django.conf import settings
from django.db import models
from pedagogie.models import Student, Classe

# Pièces habituelles du dossier d'un élève (retours V8-2).
STUDENT_PIECES = [
    "Acte de naissance", "Certificat de vaccination", "Carnet de santé", "Certificat de transfert",
    "Bulletin de l'année précédente", "Photo d'identité", "Pièce d'identité du parent",
]


class Document(models.Model):
    CATEGORY_CHOICES = [("ADMIN", "Administration"), ("STUDENT", "Élève"), ("PEDAGOGY", "Pédagogie"), ("FINANCE", "Finance"), ("OTHER", "Autre")]
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="OTHER")
    file = models.FileField(upload_to="documents/%Y/%m/")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, null=True, blank=True, related_name="documents")
    classe = models.ForeignKey(Classe, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploaded_documents")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-uploaded_at", "-id"]

    def delete(self, *args, **kwargs):
        # Le fichier importé par erreur disparaît aussi du disque.
        storage, name = self.file.storage, self.file.name
        super().delete(*args, **kwargs)
        if name:
            try:
                storage.delete(name)
            except OSError:
                pass
