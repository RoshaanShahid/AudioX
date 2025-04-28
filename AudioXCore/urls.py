# AudioXCore/urls.py (Updated)

from django.conf import settings
# Renamed static import as requested by user
from django.conf.urls.static import static as static_files
from django.contrib import admin
from django.urls import path, include # Keep include!
from django.shortcuts import redirect # Ensure redirect is imported
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

urlpatterns = [
    path('admin/', admin.site.urls),

    # Include the app's URLs first. The namespace 'AudioXApp' is defined in AudioXApp/urls.py
    path('', include('AudioXApp.urls')),

    # Redirect the root path ('') AFTER checking app URLs.
    # This specific redirect might now be redundant if AudioXApp.urls defines a pattern for ''
    # or if the 'home' view is intended to be accessed only via '/Home/'.
    # Kept for now, but ensure it doesn't conflict with an empty path in AudioXApp.urls.
    # **NAMESPACE FIX APPLIED HERE**
    path('', lambda request: redirect('AudioXApp:home', permanent=False), name='root_redirect'),

]

# Serve static files using staticfiles_urlpatterns during development
# This is often sufficient with DEBUG=True and doesn't require WhiteNoise for dev server
urlpatterns += staticfiles_urlpatterns()

# Serve media files during development
if settings.DEBUG:
    # Use the renamed import 'static_files'
    urlpatterns += static_files(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
