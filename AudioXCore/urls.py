from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include  # Import 'include'
from django.shortcuts import redirect
from django.urls import path
from . import views
from AudioX import AudioXApp


from AudioXApp.views import fetch_audiobooks
from AudioXApp.views import fetch_audiobooks


urlpatterns = [
    path('admin/', admin.site.urls),  # Admin URL included once
    #path('Home/', views.home, name='home'),  # Your custom index view
    path('Home/', views.home, name='home'), 
    path('ourteam/', views.ourteam, name='ourteam'),
    path('paymentpolicy/', views.paymentpolicy, name='paymentpolicy'),
    path('privacypolicy/', views.privacypolicy, name='privacypolicy'),
    path('piracypolicy/', views.piracypolicy, name='piracypolicy'),
    path('termsandconditions/', views.termsandconditions, name='termsandconditions'),
    path('aboutus/', views.aboutus, name='aboutus'),
    path('contactus/', views.contactus, name='contactus'),
    path('logout/', views.logout_view, name='logout'), 
    path('myprofile/', views.myprofile, name='myprofile'),
    path('update_profile/', views.update_profile, name='update_profile'),
    path('change_password/', views.change_password, name='change_password'),
    path('send-otp/', views.send_otp, name='send_otp'),  
    path('adminlogin', views.adminlogin, name='adminlogin'),
    path('adminsignup', views.adminsignup, name='adminsignup'),
    path('admindashboard', views.admindashboard, name='admindashboard'),  
    path('scrape/', views.scrape_audiobooks, name='scrape_audiobooks'),
    #path("api/audiobooks/", fetch_audiobooks, name="fetch_audiobooks"),
    path("api/audiobooks/", fetch_audiobooks, name="fetch_audiobooks"),




  
    # Redirect from the root URL (/) to /Home
    path('', lambda request: redirect('/Home/'), name='home_redirect'),
    
    # Redirect from the root URL (/) to /signup
    path('/signup', lambda request: redirect('/signup/'), name='signup_redirect'),  # Redirect to signup page
    path('signup/', views.signup, name='signup'),  # Signup page

    path('/login', lambda request: redirect('/login/'), name='login_redirect'),  # Redirect to signin page
    path('login/', AudioXApp.views.login, name='login'),  # Signin page

] 

# Static files for media and audio
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.AUDIO_URL, document_root=settings.AUDIO_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.AUDIO_URL, document_root=settings.AUDIO_ROOT)