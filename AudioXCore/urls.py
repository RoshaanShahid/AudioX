from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from AudioXApp import views  # Corrected import

urlpatterns = [
    path('admin/', admin.site.urls),  # Admin URL included once
    path('Home/', views.home, name='home'),  # Your custom index view
] 

# Static files for media and audio
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.AUDIO_URL, document_root=settings.AUDIO_ROOT)

# This part is only necessary if you want to serve media files in DEBUG mode
if settings.DEBUG:
    # No need to add admin URL here again
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.AUDIO_URL, document_root=settings.AUDIO_ROOT)
