# AudioXApp/urls.py
from django.urls import path
# Make sure all necessary view modules are imported
from .views import auth_views, user_views, creator_views, admin_views, content_views
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

app_name = 'AudioXApp'

urlpatterns = [
    # --- Content Views ---
    path('Home/', content_views.home, name='home'),
    path('ourteam/', content_views.ourteam, name='ourteam'),
    path('paymentpolicy/', content_views.paymentpolicy, name='paymentpolicy'),
    path('privacypolicy/', content_views.privacypolicy, name='privacypolicy'),
    path('piracypolicy/', content_views.piracypolicy, name='piracypolicy'),
    path('termsandconditions/', content_views.termsandconditions, name='termsandconditions'),
    path('aboutus/', content_views.aboutus, name='aboutus'),
    path('contactus/', content_views.contactus, name='contactus'),
    path("stream_audio/", content_views.stream_audio, name="stream_audio"),
    path("fetch_cover_image/", content_views.fetch_cover_image, name="fetch_cover_image"),
    path('audiobook/<slug:audiobook_slug>/', content_views.audiobook_detail, name='audiobook_detail'),
    path('audiobook/<slug:audiobook_slug>/add_review/', content_views.add_review, name='add_review'),

    # --- Auth Views ---
    path('logout/', auth_views.logout_view, name='logout'),
    path('signup/', auth_views.signup, name='signup'),
    path('login/', auth_views.login, name='login'),
    path('send-otp/', auth_views.send_otp, name='send_otp'),
    path('verify-login-otp/', auth_views.verify_login_otp, name='verify_login_otp'),
    path('forgot-password/', auth_views.forgot_password_view, name='forgot_password'),
    path('handle-forgot-password/', auth_views.handle_forgot_password, name='handle_forgot_password'),
    path('verify-otp/', auth_views.verify_otp_view, name='verify_otp'),
    path('reset-password/', auth_views.reset_password_view, name='reset_password'),

    # --- User Profile & Settings Views ---
    path('myprofile/', user_views.myprofile, name='myprofile'),
    path('update_profile/', user_views.update_profile, name='update_profile'),
    path('change_password/', user_views.change_password, name='change_password'),

    # --- Wallet & Subscription Views ---
    path('subscribe/', user_views.subscribe, name='subscribe'),
    path('managesubscription/', user_views.managesubscription, name='managesubscription'),
    path('cancel_subscription/', user_views.cancel_subscription, name='cancel_subscription'),
    path('mywallet/', user_views.mywallet, name='mywallet'),
    path('buycoins/', user_views.buycoins, name='buycoins'),
    path('gift_coins/', user_views.gift_coins, name='gift_coins'),

    # --- Stripe Payment URLs ---
    path('payment/create-checkout-session/', user_views.create_checkout_session, name='create_checkout_session'),
    path('payment/webhook/stripe/', user_views.stripe_webhook, name='stripe_webhook'),

    # --- Creator Portal Views ---
    path('creator/welcome/', creator_views.creator_welcome_view, name='creator_welcome'),
    path('creator/dashboard/', creator_views.creator_dashboard_view, name='creator_dashboard'),
    path('creator/apply/', creator_views.creator_apply_view, name='creator_apply'),
    path('creator/profile/update/', creator_views.update_creator_profile, name='update_creator_profile'),
    path('creator/withdrawal-accounts/', creator_views.creator_manage_withdrawal_accounts_view, name='creator_manage_withdrawal_accounts'),
    
    # --- Updated URL for Withdrawal Requests (List and Create) ---
    path('creator/withdrawals/request/', creator_views.creator_request_withdrawal_list_view, name='creator_request_withdrawal_list'),
    
    path('creator/upload/', creator_views.creator_upload_audiobook, name='creator_upload_audiobook'),
    path('creator/my-audiobooks/', creator_views.creator_my_audiobooks_view, name='creator_my_audiobooks'),
    path('creator/manage-upload/<slug:audiobook_slug>/', creator_views.creator_manage_upload_detail_view, name='creator_manage_upload_detail'),
    path('creator/my-earnings/', creator_views.creator_my_earnings_view, name='creator_my_earnings'),


    # --- API Endpoints ---
    path('api/creator/mark-welcome-popup/', creator_views.mark_welcome_popup_shown, name='api_mark_welcome_popup'),
    path('api/creator/mark-rejection-popup/', creator_views.mark_rejection_popup_shown, name='api_mark_rejection_popup'),
    path('api/audiobook/<slug:audiobook_slug>/chapters/', creator_views.get_audiobook_chapters_json, name='get_audiobook_chapters'),
    # NEW URL for logging audiobook views
    path('api/audiobook/log-view/', creator_views.log_audiobook_view, name='log_audiobook_view'),

    # --- Admin Area Views ---
    path('admin/welcome/', admin_views.admin_welcome_view, name='admin_welcome'),
    path('admin/register/', admin_views.adminsignup, name='adminsignup'),
    path('admin/login/', admin_views.adminlogin, name='adminlogin'),
    path('admin/dashboard/', admin_views.admindashboard, name='admindashboard'),
    path('admin/logout/', admin_views.admin_logout_view, name='admin_logout'),

    # --- Admin Creator Management URLs ---
    path('admin/manage-creators/', admin_views.admin_manage_creators, name='admin_manage_creators'),
    path('admin/manage-creators/pending/', admin_views.admin_pending_creator_applications, name='admin_pending_creator_applications'),
    path('admin/manage-creators/approved/', admin_views.admin_approved_creator_applications, name='admin_approved_creator_applications'),
    path('admin/manage-creators/rejected/', admin_views.admin_rejected_creator_applications, name='admin_rejected_creator_applications'),
    path('admin/manage-creators/history/', admin_views.admin_creator_application_history, name='admin_creator_application_history'),
    path('admin/manage-creators/all/', admin_views.admin_all_creators_list, name='admin_all_creators_list'),
    path('admin/manage-creators/banned/', admin_views.admin_banned_creators_list, name='admin_banned_creators_list'),
    path('admin/manage-creators/detail/<int:user_id>/', admin_views.admin_view_creator_detail, name='admin_view_creator_detail'),
    path('admin/creators/<int:user_id>/approve/', creator_views.admin_approve_creator, name='admin_approve_creator'),
    path('admin/creators/<int:user_id>/reject/', creator_views.admin_reject_creator, name='admin_reject_creator'),
    path('admin/creators/<int:user_id>/ban/', creator_views.admin_ban_creator, name='admin_ban_creator'),
    path('admin/creators/<int:user_id>/unban/', creator_views.admin_unban_creator, name='admin_unban_creator'),

]

# Static and Media file serving
urlpatterns += staticfiles_urlpatterns()
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
