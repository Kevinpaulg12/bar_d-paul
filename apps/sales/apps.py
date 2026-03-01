from django.apps import AppConfig

class SalesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.sales' # <--- ESTO ES VITAL: Debe incluir 'apps.'