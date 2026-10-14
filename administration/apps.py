from django.apps import AppConfig

class AdministrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "administration"

    def ready(self):
        from .signals import budget  # noqa: F401