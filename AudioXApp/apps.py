from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class AudioxappConfig(AppConfig): # Ensure class name matches your app's name in INSTALLED_APPS
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'AudioXApp' # This should be the name of your Django app

    def ready(self):
        """
        Import signals when the app is ready.
        This is the recommended way to connect signal handlers.
        """
        try:
            import AudioXApp.signals # Import the signals module
            logger.info("AudioXApp signals imported successfully in ready().")
        except ImportError as e:
            logger.error(f"Error importing AudioXApp.signals in ready(): {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred during AudioXApp.ready() while importing signals: {e}")

