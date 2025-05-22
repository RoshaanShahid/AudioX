# AudioXApp/urls.py
from django.urls import path, include
from .views import (
    content_views, 
    audio_views
)
# Import the admin view modules from the admin_views subdirectory
from .views.admin_views import (
    admin_auth_views,
    admin_dashboard_views,
    admin_creator_manage_views
)
# Import the new creator view modules from the creator_views subdirectory
from .views.creator_views import (
    dashboard_views as creator_dashboard_views,
    profile_views as creator_profile_views,
    creator_audiobook_views,
    earning_views as creator_earning_views,
    creator_tts_views,
    admin_actions_views as creator_admin_actions_views
)
# Import the new user and auth view modules from the user_views subdirectory
from .views.user_views import (
    authentication_views,
    profile_views as user_profile_views, # Alias to distinguish from creator_profile_views if needed
    wallet_views,
    subscription_views,
    payment_processing_views,
    account_activity_views
)
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

app_name = 'AudioXApp'

urlpatterns = [
    # --- Content Views ---
    path('', content_views.home, name='home'),
    path('search/', content_views.search_results_view, name='search_results'),
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
    path('urdu/', content_views.urdu_page, name='urdu_page'),
    path('punjabi/', content_views.punjabi_page, name='punjabi_page'),
    path('sindhi/', content_views.sindhi_page, name='sindhi_page'),
    path('genre/fiction/', content_views.genre_fiction, name='genre_fiction'),
    path('genre/mystery/', content_views.genre_mystery, name='genre_mystery'),
    path('genre/thriller/', content_views.genre_thriller, name='genre_thriller'),
    path('genre/scifi/', content_views.genre_scifi, name='genre_scifi'),
    path('genre/fantasy/', content_views.genre_fantasy, name='genre_fantasy'),
    path('genre/biography/', content_views.genre_biography, name='genre_biography'),
    path('genre/romance/', content_views.genre_romance, name='genre_romance'),
    path('genre/history/', content_views.genre_history, name='genre_history'),
    path('genre/selfhelp/', content_views.genre_selfhelp, name='genre_selfhelp'),
    path('genre/business/', content_views.genre_business, name='genre_business'),
    path('generate-audio/', audio_views.generate_audio_from_document,  name='generate_audio_from_document' ),

    # --- Auth Views (now from user_views.authentication_views) ---
    path('logout/', authentication_views.logout_view, name='logout'),
    path('signup/', authentication_views.signup, name='signup'),
    path('login/', authentication_views.login, name='login'),
    path('send-otp/', authentication_views.send_otp, name='send_otp'),
    path('verify-login-otp/', authentication_views.verify_login_otp, name='verify_login_otp'),
    path('forgot-password/', authentication_views.forgot_password_request, name='forgot_password'),
    path('verify-password-reset-otp/', authentication_views.verify_password_reset_otp, name='verify_password_reset_otp'),
    path('reset-password/', authentication_views.reset_password_form, name='reset_password'),
    path('reset-password/confirm/', authentication_views.reset_password_confirm, name='reset_password_confirm'),

    # --- User Profile & Settings Views (now from user_views.profile_views) ---
    path('myprofile/', user_profile_views.myprofile, name='myprofile'),
    path('update_profile/', user_profile_views.update_profile, name='update_profile'),
    path('change_password/', user_profile_views.change_password, name='change_password'),
    path('complete-profile/', user_profile_views.complete_profile, name='complete_profile'),

    # --- Wallet & Subscription Views (now from user_views.wallet_views and user_views.subscription_views) ---
    path('subscribe/', subscription_views.subscribe, name='subscribe'),
    path('managesubscription/', subscription_views.managesubscription, name='managesubscription'),
    path('cancel_subscription/', subscription_views.cancel_subscription, name='cancel_subscription'),
    path('mywallet/', wallet_views.mywallet, name='mywallet'),
    path('buycoins/', wallet_views.buycoins, name='buycoins'),
    path('gift_coins/', wallet_views.gift_coins, name='gift_coins'),
    
    # --- User Account Activity Views (now from user_views.account_activity_views) ---
    path('billing-history/', account_activity_views.billing_history, name='billing_history'),
    path('my-downloads/', account_activity_views.my_downloads, name='my_downloads'),
    path('my-library/', account_activity_views.my_library, name='my_library'),

    # --- Stripe Payment URLs (now from user_views.payment_processing_views) ---
    path('payment/create-checkout-session/', payment_processing_views.create_checkout_session, name='create_checkout_session'),
    path('payment/webhook/stripe/', payment_processing_views.stripe_webhook, name='stripe_webhook'),

    # --- Creator Portal Views ---
    path('creator/welcome/', creator_profile_views.creator_welcome_view, name='creator_welcome'),
    path('creator/dashboard/', creator_dashboard_views.creator_dashboard_view, name='creator_dashboard'),
    path('creator/apply/', creator_profile_views.creator_apply_view, name='creator_apply'),
    path('creator/profile/update/', creator_profile_views.update_creator_profile, name='update_creator_profile'),
    path('creator/withdrawal-accounts/', creator_earning_views.creator_manage_withdrawal_accounts_view, name='creator_manage_withdrawal_accounts'),
    path('creator/withdrawals/request/', creator_earning_views.creator_request_withdrawal_list_view, name='creator_request_withdrawal_list'),
    path('creator/upload/', creator_audiobook_views.creator_upload_audiobook, name='creator_upload_audiobook'),
    path('creator/my-audiobooks/', creator_audiobook_views.creator_my_audiobooks_view, name='creator_my_audiobooks'),
    path('creator/manage-upload/<slug:audiobook_slug>/', creator_audiobook_views.creator_manage_upload_detail_view, name='creator_manage_upload_detail'),
    path('creator/my-earnings/', creator_earning_views.creator_my_earnings_view, name='creator_my_earnings'),

    # --- API Endpoints (Creator related) ---
    path('api/creator/mark-welcome-popup/', creator_profile_views.mark_welcome_popup_shown, name='api_mark_welcome_popup'),
    path('api/creator/mark-rejection-popup/', creator_profile_views.mark_rejection_popup_shown, name='api_mark_rejection_popup'),
    path('api/audiobook/<slug:audiobook_slug>/chapters/', creator_audiobook_views.get_audiobook_chapters_json, name='get_audiobook_chapters'),
    path('api/audiobook/log-view/', creator_audiobook_views.log_audiobook_view, name='log_audiobook_view'),
    path('api/creator/generate-tts-preview/', creator_tts_views.generate_tts_preview_audio, name='generate_tts_preview_audio'),
    path('api/creator/generate-document-tts-preview/', creator_tts_views.generate_document_tts_preview_audio, name='generate_document_tts_preview_audio'),

    # --- Admin Area Views ---
    path('admin/welcome/', admin_auth_views.admin_welcome_view, name='admin_welcome'),
    path('admin/register/', admin_auth_views.adminsignup, name='adminsignup'),
    path('admin/login/', admin_auth_views.adminlogin, name='adminlogin'),
    path('admin/logout/', admin_auth_views.admin_logout_view, name='admin_logout'),
    path('admin/dashboard/', admin_dashboard_views.admindashboard, name='admindashboard'),

    # --- Admin Creator Management URLs ---
    path('admin/manage-creators/', admin_creator_manage_views.admin_manage_creators, name='admin_manage_creators'),
    path('admin/manage-creators/pending/', admin_creator_manage_views.admin_pending_creator_applications, name='admin_pending_creator_applications'),
    path('admin/manage-creators/approved/', admin_creator_manage_views.admin_approved_creator_applications, name='admin_approved_creator_applications'),
    path('admin/manage-creators/rejected/', admin_creator_manage_views.admin_rejected_creator_applications, name='admin_rejected_creator_applications'),
    path('admin/manage-creators/history/', admin_creator_manage_views.admin_creator_application_history, name='admin_creator_application_history'),
    path('admin/manage-creators/all/', admin_creator_manage_views.admin_all_creators_list, name='admin_all_creators_list'),
    path('admin/manage-creators/banned/', admin_creator_manage_views.admin_banned_creators_list, name='admin_banned_creators_list'),
    path('admin/manage-creators/detail/<int:user_id>/', admin_creator_manage_views.admin_view_creator_detail, name='admin_view_creator_detail'),
    
    path('admin/creators/<int:user_id>/approve/', creator_admin_actions_views.admin_approve_creator, name='admin_approve_creator'),
    path('admin/creators/<int:user_id>/reject/', creator_admin_actions_views.admin_reject_creator, name='admin_reject_creator'),
    path('admin/creators/<int:user_id>/ban/', creator_admin_actions_views.admin_ban_creator, name='admin_ban_creator'),
    path('admin/creators/<int:user_id>/unban/', creator_admin_actions_views.admin_unban_creator, name='admin_unban_creator'),
]

# Static and Media file serving (for development)
urlpatterns += staticfiles_urlpatterns()
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
