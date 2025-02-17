from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', lambda request: redirect('home'), name='home_redirect'), # Keep this redirect
    path('', include('AudioXApp.urls')), # Include app urls
]

urlpatterns += staticfiles_urlpatterns()

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)