from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include  # include is not really needed here
from AudioXApp import views
from .views import scrape_audiobooks
from .views import fetch_audiobooks

urlpatterns = [
    #  path('admin/', admin.site.urls),  <- Removed: Admin is handled in project urls.py
    #path('Home/', views.home, name='home'),
    path('Home/', views.home, name='home'), 
    path('', views.home, name='home_redirect'), # Redirect empty path to Home
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
    path('mywallet/', views.my_wallet, name='my_wallet'),
    path('buy_coins/', views.buy_coins, name='buy_coins'),



    ] 

# Static files for media and audio
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.AUDIO_URL, document_root=settings.AUDIO_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.AUDIO_URL, document_root=settings.AUDIO_ROOT)