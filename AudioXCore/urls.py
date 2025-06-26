from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView

# =============================================================================
#  CORE URL PATTERNS
# =============================================================================
# This is the primary URL configuration for the AudioX project.

urlpatterns = [
    # -------------------------------------------------------------------------
    #  Custom Application URLs (MOVED BEFORE DJANGO ADMIN)
    # -------------------------------------------------------------------------
    # Includes all URL patterns from the main AudioXApp application.
    # This must come BEFORE the Django admin URLs to prevent conflicts
    path('', include('AudioXApp.urls', namespace='AudioXApp')),

    # -------------------------------------------------------------------------
    #  Admin Site URL (MOVED AFTER CUSTOM URLS)
    # -------------------------------------------------------------------------
    # Changed to 'django-admin/' to avoid conflicts with custom admin
    path('django-admin/', admin.site.urls),

    # -------------------------------------------------------------------------
    #  Third-Party App URLs
    # -------------------------------------------------------------------------
    # URLs for django-allauth for handling user authentication, registration, etc.
    path('accounts/', include('allauth.urls')),

    # -------------------------------------------------------------------------
    #  PWA (Progressive Web App) Service Worker
    # -------------------------------------------------------------------------
    # Serves the service_worker.js file from the root URL.
    path(
        "service_worker.js",
        TemplateView.as_view(
            template_name="pwafiles/service_worker.js",
            content_type="application/javascript",
        ),
        name="service_worker_js",
    ),
]

# =============================================================================
#  DEVELOPMENT-ONLY URLS
# =============================================================================
# These patterns are only added when DEBUG is True in settings.
# In production, your web server (e.g., Nginx) should be configured to serve
# static and media files.

if settings.DEBUG:
    # Serve static files (CSS, JavaScript, images)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    # Serve user-uploaded media files (e.g., audiobook covers)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
