# AudioXCore/urls.py
from django.conf import settings
from django.conf.urls.static import static as static_files_settings # Renamed to avoid conflict
from django.contrib import admin # Import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

urlpatterns = [
    # Django's built-in admin.
    # Changed path to 'django-admin/' to avoid conflict with custom admin URLs.
    # You will now access the default Django admin at /django-admin/
    path('django-admin/', admin.site.urls),

    # Redirect the root URL ('/') to the home page.
    # Ensure 'AudioXApp:home' is a valid named URL in your AudioXApp/urls.py
    path('', lambda request: redirect('AudioXApp:home', permanent=False), name='root_redirect'),

    # Include your app's URLs (handles '/Home/', '/login/', '/admin/welcome/', etc.)
    # This should come AFTER more specific paths if there were any overlaps,
    # but in this case, changing the Django admin path is the cleaner solution.
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
