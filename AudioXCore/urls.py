# AudioXCore/urls.py

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.views.generic import TemplateView

# --- URL Patterns ---

urlpatterns = [
    # Django's built-in admin site
    path('django-admin/', admin.site.urls),

    # Include AudioXApp URLs for the main site paths
    path('', include('AudioXApp.urls')),

    # django-allauth URLs for authentication
    path('accounts/', include('allauth.urls')),

    # URL for serving the service worker from the root
    path(
        "service_worker.js",
        TemplateView.as_view(
            template_name="pwafiles/service_worker.js",
            content_type="application/javascript",
        ),
        name="service_worker_js",
    ),
]

# --- Static and Media Files ---

# Serve static files during development
urlpatterns += staticfiles_urlpatterns()

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
