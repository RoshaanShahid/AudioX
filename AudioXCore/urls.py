from django.conf import settings
from django.conf.urls.static import static as static_files  # Renamed for clarity
from django.contrib import admin
from django.urls import path, include  # Keep include!
from django.shortcuts import redirect
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('AudioXApp.urls')),  # Include the app's URLs
    path('', lambda request: redirect('home'), name='home_redirect'), # Redirect / to /Home
]

# Serve static files during development (Corrected function name)
urlpatterns += staticfiles_urlpatterns()

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static_files(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)