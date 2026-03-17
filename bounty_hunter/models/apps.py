from django.apps import AppConfig


class ModelsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bounty_hunter.models"
    label = "bounty_models"
    verbose_name = "Bounty Hunter Models"
