# AudioXApp/apps.py

from django.apps import AppConfig

class AudioxappConfig(AppConfig):
    """
    App configuration for AudioXApp.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'AudioXApp'

    def ready(self):
        """
        Import signals when the app is ready.
        """
        import AudioXApp.signals

