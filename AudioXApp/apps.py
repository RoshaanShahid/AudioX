# AudioXApp/apps.py

from django.apps import AppConfig

# --- App Configuration ---

class AudioxappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'AudioXApp'

    def ready(self):
        import AudioXApp.signals