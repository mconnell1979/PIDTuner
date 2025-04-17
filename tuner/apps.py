from django.apps import AppConfig

class TunerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tuner"

    def ready(self):
        from . import signals  # ✅ Use relative import

