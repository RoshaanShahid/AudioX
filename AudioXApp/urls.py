from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include  # include is not really needed here
from AudioXApp import views

urlpatterns = [
    #  path('admin/', admin.site.urls),  <- Removed: Admin is handled in project urls.py
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
    path('adminlogin/', views.adminlogin, name='adminlogin'),  # Corrected adminlogin path
    path('adminsignup/', views.adminsignup, name='adminsignup'),
    path('admindashboard/', views.admindashboard, name='admindashboard'),
    path('buy-coins/', views.buy_coins, name='buy_coins'),
    path('buycoins/', views.buycoins, name='buycoins'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.login, name='login'),
    path('mywallet/', views.mywallet, name='mywallet'),
    path('gift_coins/', views.gift_coins, name='gift_coins'),
    path('subscribe/', views.subscribe, name='subscribe'),
    path('subscribe/now/', views.subscribe_now, name='subscribe_now'),
    path('managesubscription/', views.managesubscription, name='managesubscription'),
    path('cancelsubscription/', views.cancel_subscription, name='cancel_subscription'),
]

# Static files (same as before)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.AUDIO_URL, document_root=settings.AUDIO_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.AUDIO_URL, document_root=settings.AUDIO_ROOT)