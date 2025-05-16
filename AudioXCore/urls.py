# AudioXCore/urls.py
from django.conf import settings
from django.conf.urls.static import static as static_files_settings # Renamed to avoid conflict
from django.contrib import admin
from django.urls import path, include
# from django.shortcuts import redirect # No longer needed for the root_redirect
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

urlpatterns = [
    # Django's built-in admin.
    path('django-admin/', admin.site.urls),

    # Include your app's URLs (handles '/', '/login/', '/admin/welcome/', etc.)
    # The path '' in AudioXApp.urls (named 'home') will now correctly serve as the root.
    path('', include('AudioXApp.urls')),

    # django-allauth URLs for social login, account management etc.
    # Make sure this is correctly configured if you are using it.
    path('accounts/', include('allauth.urls')),
]

# Serve static files using staticfiles_urlpatterns
urlpatterns += staticfiles_urlpatterns()

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static_files_settings(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
