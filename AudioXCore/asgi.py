# AudioXCore/asgi.py

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import AudioXApp.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AudioXCore.settings')

# Initialize Django ASGI application early to ensure AppRegistry is ready
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            AudioXApp.routing.websocket_urlpatterns
        )
    ),
})