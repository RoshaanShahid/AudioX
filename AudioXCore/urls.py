from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from AudioXApp import views  # Corrected import
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),  # Admin URL included once
    path('Home/', views.home, name='home'),  # Your custom index view
    path('team/', views.team, name='team'),

    # Redirect from the root URL (/) to /Home
    path('', lambda request: redirect('/Home/'), name='home_redirect'),
    
    # Redirect from the root URL (/) to /signup
    path('/signup', lambda request: redirect('/signup/'), name='signup_redirect'),  # Redirect to signup page
    path('signup/', views.signup, name='signup'),  # Signup page

    path('/login', lambda request: redirect('/login/'), name='login_redirect'),  # Redirect to signin page
    path('login/', views.login, name='login'),  # Signin page

] 

# Static files for media and audio
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.AUDIO_URL, document_root=settings.AUDIO_ROOT)

# This part is only necessary if you want to serve media files in DEBUG mode
if settings.DEBUG:
    # No need to add admin URL here again
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.AUDIO_URL, document_root=settings.AUDIO_ROOT)
