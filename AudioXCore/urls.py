from django.conf import settings
from django.conf.urls.static import static as static_files
from django.contrib import admin
from django.urls import path, include  # Keep include, it's good practice for larger projects
from django.shortcuts import redirect
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from AudioXApp import views
from AudioXApp.views import *  # It's generally better to import specific views, but this works for now.

urlpatterns = [
    path('admin/', admin.site.urls),
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
    path('adminlogin/', views.adminlogin, name='adminlogin'),
    path('adminsignup/', views.adminsignup, name='adminsignup'),
    path('admindashboard/', views.admindashboard, name='admindashboard'),
    path('scrape/', views.scrape_audiobooks, name='scrape_audiobooks'),
    path("api/audiobooks/", fetch_audiobooks, name="fetch_audiobooks"),
    path('subscribe/', views.subscribe, name='subscribe'),
    path('subscribe_now/', views.subscribe_now, name='subscribe_now'),
    path('managesubscription/', views.managesubscription, name='managesubscription'),
    path('cancel_subscription/', views.cancel_subscription, name='cancel_subscription'),
    path('mywallet/', views.mywallet, name='mywallet'),
    path('buycoins/', views.buycoins, name='buycoins'),
    path('buy_coins/', views.buy_coins, name='buy_coins'),  # URL for the AJAX POST request
    path('gift_coins/', views.gift_coins, name='gift_coins'),
    path("stream_audio/", stream_audio, name="stream_audio"),
    path("fetch_cover_image/", fetch_cover_image, name="fetch_cover_image"),


    # Redirects
    path('', lambda request: redirect('home'), name='home_redirect'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.login, name='login'),
]

# Serve static files during development
urlpatterns += staticfiles_urlpatterns()

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static_files(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)