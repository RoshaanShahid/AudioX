# AudioXApp/routing.py

from django.urls import re_path
from . import consumer # USE SINGULAR 'consumer' to match your likely filename

# Updated print statement to use singular 'consumer'
print(f"--- AudioXApp/routing.py: Defining websocket_urlpatterns...")
if hasattr(consumer, 'ChatConsumer'):
    print(f"--- AudioXApp/routing.py: consumer.ChatConsumer found ---")
else:
    print(f"--- AudioXApp/routing.py: ERROR - consumer.ChatConsumer NOT found ---")


websocket_urlpatterns = [
    re_path(
        r'ws/chat/(?P<room_id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/$', 
        consumer.ChatConsumer.as_asgi() # USE SINGULAR 'consumer' here
    ),
]

print(f"--- AudioXApp/routing.py: websocket_urlpatterns = {websocket_urlpatterns} ---")