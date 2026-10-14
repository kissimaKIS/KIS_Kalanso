from django import forms
from .models import Announcement
class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ["title", "message", "audience", "published_at", "is_active"]
        widgets = {"published_at": forms.DateTimeInput(attrs={"type":"datetime-local"})}
