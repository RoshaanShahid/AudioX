# AudioXCore/urls.py
from django.conf import settings
from django.conf.urls.static import static as static_files_settings # Renamed to avoid conflict
from django.contrib import admin # Import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

urlpatterns = [
    # Django's built-in admin.
    # This is useful for managing django-allauth's SocialApp model if you ever need to,
    # and for other Django admin functionalities.
    path('admin/', admin.site.urls),

    # Redirect the root URL ('/') to the home page.
    # Ensure 'AudioXApp:home' is a valid named URL in your AudioXApp/urls.py
    path('', lambda request: redirect('AudioXApp:home', permanent=False), name='root_redirect'),

    # Include your app's URLs (handles '/Home/', '/login/', etc.)
    path('', include('AudioXApp.urls')),

    # django-allauth URLs for social login, account management etc.
    path('accounts/', include('allauth.urls')),
]

# Serve static files using staticfiles_urlpatterns
# This is generally preferred over manually adding static to urlpatterns for development.
urlpatterns += staticfiles_urlpatterns()

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static_files_settings(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
