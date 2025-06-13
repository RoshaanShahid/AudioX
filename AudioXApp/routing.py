# AudioXApp/routing.py

from django.urls import re_path
from . import consumer

websocket_urlpatterns = [
    re_path(
        r'ws/chat/(?P<room_id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/$', 
        consumer.ChatConsumer.as_asgi()
    ),
]