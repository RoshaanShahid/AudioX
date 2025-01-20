# URL configuration for AudioXCore project.

# The `urlpatterns` list routes URLs to views. For more information please see:
#     https://docs.djangoproject.com/en/4.2/topics/http/urls/

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from AudioXApp import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('Home/', views.Index, name='Home'),
    path('ourteam/', views.ourteam, name='ourteam'),
    path('paymentpolicy/', views.paymentpolicy, name='paymentpolicy'),
    path('privacypolicy/', views.privacypolicy, name='privacypolicy'),
    path('piracypolicy/', views.piracypolicy, name='piracypolicy'),
    path('termsandconditions/', views.termsandconditions, name='termsandconditions'),
    path('aboutus/', views.aboutus, name='aboutus'),
    path('contactus/', views.contactus, name='contactus'),
    path('logout/', views.logout_view, name='logout'), 
    ] 

# Static files for media and audio
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.AUDIO_URL, document_root=settings.AUDIO_ROOT)

# This part is only necessary if you want to serve media files in DEBUG mode
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.AUDIO_URL, document_root=settings.AUDIO_ROOT)
