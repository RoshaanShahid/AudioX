# AudioXApp/apps.py
from django.apps import AppConfig

class AudioxappConfig(AppConfig): # Ensure this class name matches what's in your __init__.py or settings.py if specified
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'AudioXApp'

    def ready(self):
        """
        Import signals when the app is ready.
        This is the recommended way to connect signal handlers.
        """
        import AudioXApp.signals # noqa: F401 (suppress unused import warning if linters complain)
