from django.conf import settings
from django.db import models
from django.utils import timezone

class Announcement(models.Model):
    AUDIENCE_CHOICES = [("ALL", "Toute l'école"), ("STUDENTS", "Élèves"), ("TEACHERS", "Enseignants"), ("SECRETARY", "Secrétariat"), ("PARENTS", "Parents"), ("EXTERNAL", "Communication externe")]
    title = models.CharField(max_length=200)
    message = models.TextField()
    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default="ALL")
    published_at = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="announcements")
    updated_at = models.DateTimeField(null=True, blank=True, verbose_name="Modifiée le")
    class Meta:
        ordering = ["-published_at", "-id"]
