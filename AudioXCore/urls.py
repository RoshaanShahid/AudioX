# AudioXCore/urls.py
from django.conf import settings
from django.conf.urls.static import static as static_files
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

urlpatterns = [
    # Redirect the root URL ('/') to the home page ('/Home/')
    path('', lambda request: redirect('AudioXApp:home', permanent=False), name='root_redirect'),

    # Include your app's URLs. Requests like '/Home/', '/login/', etc., will be handled here.
    path('', include('AudioXApp.urls')),

    # Note: The default Django admin interface path ('admin/') is not included.
    # Your custom admin paths like 'admin/login/', 'admin/dashboard/' are handled by AudioXApp.urls
]

urlpatterns += staticfiles_urlpatterns()
if settings.DEBUG:
    urlpatterns += static_files(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

