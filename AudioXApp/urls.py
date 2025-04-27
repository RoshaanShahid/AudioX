from django.urls import path
from . import views  # Import views from the *current* app (VERY IMPORTANT)
from django.conf import settings  # Import settings
from django.conf.urls.static import static  # Import static for media files
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

urlpatterns = [
    # All your app-specific URL patterns go here:
    path('Home/', views.home, name='home'),  # This is the correct place for your home view
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
    path("api/audiobooks/", views.fetch_audiobooks, name="fetch_audiobooks"),
    path('subscribe/', views.subscribe, name='subscribe'),
    path('subscribe_now/', views.subscribe_now, name='subscribe_now'),
    path('managesubscription/', views.managesubscription, name='managesubscription'),
    path('cancel_subscription/', views.cancel_subscription, name='cancel_subscription'),
    path('mywallet/', views.mywallet, name='mywallet'),
    path('buycoins/', views.buycoins, name='buycoins'),
    path('buy_coins/', views.buy_coins, name='buy_coins'),
    path('gift_coins/', views.gift_coins, name='gift_coins'),
    path("stream_audio/", views.stream_audio, name="stream_audio"),
    path("fetch_cover_image/", views.fetch_cover_image, name="fetch_cover_image"),
    path('audiobook/<slug:audiobook_slug>/', views.audiobook_detail, name='audiobook_detail'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.login, name='login'),
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('handle-forgot-password/', views.handle_forgot_password, name='handle_forgot_password'),
    path('verify-otp/', views.verify_otp_view, name='verify_otp'),
    path('reset-password/', views.reset_password_view, name='reset_password'),
    path('Urdu/', views.urdu_page, name='urdu_page'),
    path('Punjabi/', views.punjabi_page, name='punjabi_page'),
    path('Sindhi/', views.sindhi_page, name='sindhi_page'),
    path('genrefiction/', views.genre_fiction, name='genre_fiction'),
    path('genremystery/', views.genre_mystery, name='genre_mystery'),
    path('genrethriller/', views.genre_thriller, name='genre_thriller'),
    path('genrescifi/', views.genre_scifi, name='genre_scifi'),
    path('genrefantasy/', views.genre_fantasy, name='genre_fantasy'),
    path('genrebiography/', views.genre_biography, name='genre_biography'),
    path('genreromance/', views.genre_romance, name='genre_romance'),
    path('genrehistory/', views.genre_history, name='genre_history'),
    path('genreselfhelp/', views.genre_selfhelp, name='genre_selfhelp'),
    path('genrebusiness/', views.genre_business, name='genre_business'),
     ]

urlpatterns += staticfiles_urlpatterns()
if settings.DEBUG:
     urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)