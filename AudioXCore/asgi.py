# AudioXCore/asgi.py

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import AudioXApp.routing # Import your app's routing configuration

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AudioXCore.settings')

django_asgi_app = get_asgi_application()

# Add a print statement here to see if this file is being executed
print("--- AudioXCore/asgi.py: Initializing ProtocolTypeRouter ---")
print(f"--- AudioXApp.routing.websocket_urlpatterns: {AudioXApp.routing.websocket_urlpatterns if hasattr(AudioXApp, 'routing') and hasattr(AudioXApp.routing, 'websocket_urlpatterns') else 'NOT FOUND or EMPTY'} ---")

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            AudioXApp.routing.websocket_urlpatterns
        )
    ),
})

print("--- AudioXCore/asgi.py: ProtocolTypeRouter configured ---")