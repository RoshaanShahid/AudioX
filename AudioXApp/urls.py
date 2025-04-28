# AudioXApp/urls.py
from django.urls import path
from . import views  # Import views from the *current* app (VERY IMPORTANT)
from django.conf import settings  # Import settings
from django.conf.urls.static import static  # Import static for media files
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

app_name = 'AudioXApp' # Define the namespace

urlpatterns = [
    # All your app-specific URL patterns go here:
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
    path('send-otp/', views.send_otp, name='send_otp'), # For signup
    path('adminlogin/', views.adminlogin, name='adminlogin'),
    path('adminsignup/', views.adminsignup, name='adminsignup'),
    path('admindashboard/', views.admindashboard, name='admindashboard'),
    # path('scrape/', views.scrape_audiobooks, name='scrape_audiobooks'), # Removed/Commented out this line
    # path("api/audiobooks/", views.fetch_audiobooks, name="fetch_audiobooks"), # This was likely replaced by the caching logic in home view
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
    path('verify-otp/', views.verify_otp_view, name='verify_otp'), # OTP for password reset
    path('reset-password/', views.reset_password_view, name='reset_password'),

    # --- ADDED URL Pattern for Login OTP Verification ---
    path('verify-login-otp/', views.verify_login_otp, name='verify_login_otp'),
    # --- End Added URL Pattern ---
]

# These lines are generally better placed in the project's main urls.py,
# but keep them here if they were working for you.
urlpatterns += staticfiles_urlpatterns()
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
