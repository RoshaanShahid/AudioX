# AudioXCore/urls.py
from django.conf import settings
from django.conf.urls.static import static as static_files_settings # Renamed to avoid conflict
from django.contrib import admin
from django.urls import path, include
# from django.shortcuts import redirect # No longer needed for the root_redirect, can be commented out or removed
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

urlpatterns = [
    # Django's built-in admin.
    # Changed path to 'django-admin/' to avoid conflict with custom admin URLs.
    # You will now access the default Django admin at /django-admin/
    path('django-admin/', admin.site.urls),

    # REMOVED: The explicit redirect for the root URL was causing a loop.
    # path('', lambda request: redirect('AudioXApp:home', permanent=False), name='root_redirect'),

    # Include your app's URLs (handles '/', '/login/', '/admin/welcome/', etc.)
    # Since AudioXApp.urls defines path('', ... name='home'), this will now correctly
    # route the root URL '/' to the AudioXApp:home view directly.
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
