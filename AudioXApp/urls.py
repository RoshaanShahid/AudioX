# AudioXApp/urls.py
from django.urls import path, include # Ensure include is imported if not already
from .views import (
    content_views,
    library_views,
    history_views
)
# Import the admin view modules
from .views.admin_views import (
    admin_auth_views,
    admin_dashboard_views,
    admin_creator_manage_views,
    admin_users_manage_views,
    admin_manage_financials_views,
    admin_ticket_management_views,
    admin_management_views
)
# Import creator view modules
from .views.creator_views import (
    dashboard_views as creator_dashboard_views,
    profile_views as creator_profile_views,
    creator_audiobook_views,
    earning_views as creator_earning_views,
    creator_tts_views,
    admin_actions_views as creator_admin_actions_views
)
# Import user and auth view modules
from .views.user_views import (
    authentication_views,
    profile_views as user_profile_views,
    wallet_views,
    subscription_views,
    payment_processing_views,
    account_activity_views,
    contactsupport_views
)
# Import views for static/legal pages and features
from .views.legal_views import static_pages_views
# Updated import for features_views
from .views.features_views import (
    community_chatrooms_feature_views, # This is our alias for chat views
    document_to_audio_feature_views
)

from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

app_name = 'AudioXApp'

urlpatterns = [
    # --- Content Views ---
    path('', content_views.home, name='home'),
    path('search/', content_views.search_results_view, name='search_results'),
    path("stream_audio/", content_views.stream_audio, name="stream_audio"),
    path("fetch_cover_image/", content_views.fetch_cover_image, name="fetch_cover_image"),
    path('audiobook/<slug:audiobook_slug>/', content_views.audiobook_detail, name='audiobook_detail'),
    path('audiobook/<slug:audiobook_slug>/add_review/', content_views.add_review, name='add_review'),
    path('urdu/', content_views.urdu_page, name='urdu_page'),
    path('punjabi/', content_views.punjabi_page, name='punjabi_page'),
    path('sindhi/', content_views.sindhi_page, name='sindhi_page'),

    # Genre pages
    path('genre/fiction/', content_views.genre_fiction, name='genre_fiction'),
    path('genre/mystery/', content_views.genre_mystery, name='genre_mystery'),
    path('genre/thriller/', content_views.genre_thriller, name='genre_thriller'),
    path('genre/science-fiction/', content_views.genre_scifi, name='genre_scifi'),
    path('genre/fantasy/', content_views.genre_fantasy, name='genre_fantasy'),
    path('genre/romance/', content_views.genre_romance, name='genre_romance'),
    path('genre/biography/', content_views.genre_biography, name='genre_biography'),
    path('genre/history/', content_views.genre_history, name='genre_history'),
    path('genre/self-help/', content_views.genre_selfhelp, name='genre_selfhelp'),
    path('genre/business/', content_views.genre_business, name='genre_business'),

    path('creator/generate-audio-from-document/', creator_tts_views.generate_document_tts_preview_audio, name='creator_generate_audio_from_document'),
    path('trending/', content_views.trending_audiobooks_view, name='trending_audiobooks'),
    path('generate-audio/', document_to_audio_feature_views.generate_audio_from_document, name='general_generate_audio_from_document' ),

    # --- Legal, Company, and Contact Pages ---
    path('ourteam/', static_pages_views.ourteam_view, name='ourteam'),
    path('paymentpolicy/', static_pages_views.paymentpolicy_view, name='paymentpolicy'),
    path('privacypolicy/', static_pages_views.privacypolicy_view, name='privacypolicy'),
    path('piracypolicy/', static_pages_views.piracypolicy_view, name='piracypolicy'),
    path('termsandconditions/', static_pages_views.termsandconditions_view, name='termsandconditions'),
    path('aboutus/', static_pages_views.aboutus_view, name='aboutus'),

    # --- Contact Support & Ticketing URLs ---
    path('contactus/', contactsupport_views.create_ticket_view, name='contact_us'),
    path('support/api/generate-ticket-details/', contactsupport_views.ajax_ai_generate_ticket_details_view, name='ajax_ai_generate_ticket_details'),
    path('support/my-tickets/', contactsupport_views.user_ticket_list_view, name='user_ticket_list'),
    path('support/ticket/<uuid:ticket_uuid>/', contactsupport_views.user_ticket_detail_view, name='user_ticket_detail'),

    # --- Auth Views ---
    path('logout/', authentication_views.logout_view, name='logout'),
    path('signup/', authentication_views.signup, name='signup'),
    path('login/', authentication_views.login, name='login'),
    path('send-otp/', authentication_views.send_otp, name='send_otp'),
    path('verify-login-otp/', authentication_views.verify_login_otp, name='verify_login_otp'),
    path('forgot-password/', authentication_views.forgot_password_request, name='forgot_password'),
    path('verify-password-reset-otp/', authentication_views.verify_password_reset_otp, name='verify_password_reset_otp'),
    path('reset-password/', authentication_views.reset_password_form, name='reset_password'),
    path('reset-password/confirm/', authentication_views.reset_password_confirm, name='reset_password_confirm'),

    # --- User Profile & Settings Views ---
    path('myprofile/', user_profile_views.myprofile, name='myprofile'),
    path('update_profile/', user_profile_views.update_profile, name='update_profile'),
    path('change_password/', user_profile_views.change_password, name='change_password'),
    path('complete-profile/', user_profile_views.complete_profile, name='complete_profile'),

    # --- Wallet & Subscription Views ---
    path('subscribe/', subscription_views.subscribe, name='subscribe'),
    path('managesubscription/', subscription_views.managesubscription, name='managesubscription'),
    path('cancel_subscription/', subscription_views.cancel_subscription, name='cancel_subscription'),
    path('mywallet/', wallet_views.mywallet, name='mywallet'),
    path('buycoins/', wallet_views.buycoins, name='buycoins'),
    path('gift_coins/', wallet_views.gift_coins, name='gift_coins'),

    # --- User Account Activity Views ---
    path('billing-history/', account_activity_views.billing_history, name='billing_history'),
    path('my-downloads/', account_activity_views.my_downloads, name='my_downloads'),
    path('my-account-library/', account_activity_views.my_library, name='my_account_library'),

    path('my-listening-history/', history_views.listening_history_page, name='listening_history_page'),
    path('ajax/update-audio-progress/', history_views.update_listening_progress, name='update_listening_progress'),

    path('my-library/', library_views.my_library_page, name='my_library_page'),
    path('ajax/toggle-library-item/', library_views.toggle_library_item, name='toggle_library_item'),

    # --- Stripe Payment URLs ---
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
    # ... (all your admin URLs remain unchanged) ...
    path('admin/welcome/', admin_auth_views.admin_welcome_view, name='admin_welcome'),
    path('admin/register/', admin_auth_views.adminsignup, name='adminsignup'),
    path('admin/login/', admin_auth_views.adminlogin, name='adminlogin'),
    path('admin/logout/', admin_auth_views.admin_logout_view, name='admin_logout'),
    path('admin/dashboard/', admin_dashboard_views.admindashboard, name='admindashboard'),
    path('admin/manage-users/', admin_users_manage_views.admin_manage_users, name='admin_manage_users'),
    path('admin/manage-users/all/', admin_users_manage_views.admin_all_users_list, name='admin_all_users_list'),
    path('admin/manage-users/active/', admin_users_manage_views.admin_active_users_list, name='admin_active_users_list'),
    path('admin/manage-users/new/', admin_users_manage_views.admin_new_users_list, name='admin_new_users_list'),
    path('admin/manage-users/subscribed/', admin_users_manage_views.admin_subscribed_users_list, name='admin_subscribed_users_list'),
    path('admin/manage-users/wallet-balances/', admin_users_manage_views.admin_wallet_balances_list, name='admin_wallet_balances_list'),
    path('admin/manage-users/banned/', admin_users_manage_views.admin_banned_users_platform_list, name='admin_banned_users_platform_list'),
    path('admin/users/<int:user_id>/ban/', admin_users_manage_views.admin_ban_user, name='admin_ban_user'),
    path('admin/users/<int:user_id>/unban/', admin_users_manage_views.admin_unban_user, name='admin_unban_user'),
    path('admin/manage-users/detail/<int:user_id>/', admin_users_manage_views.admin_view_user_detail, name='admin_view_user_detail'),
    path('admin/manage-users/payment-details/', admin_users_manage_views.admin_user_payment_details_view, name='admin_user_payment_details'),
    path('admin/manage-users/activity-log/', admin_users_manage_views.admin_user_activity_log_view, name='admin_user_activity_dashboard'),
    path('admin/manage-users/activity-log/<int:user_id>/', admin_users_manage_views.admin_user_activity_log_view, name='admin_user_activity_log_specific'),
    path('admin/manage-creators/', admin_creator_manage_views.admin_manage_creators, name='admin_manage_creators'),
    path('admin/manage-creators/pending/', admin_creator_manage_views.admin_pending_creator_applications, name='admin_pending_creator_applications'),
    path('admin/manage-creators/approved/', admin_creator_manage_views.admin_approved_creator_applications, name='admin_approved_creator_applications'),
    path('admin/manage-creators/rejected/', admin_creator_manage_views.admin_rejected_creator_applications, name='admin_rejected_creator_applications'),
    path('admin/manage-creators/history/', admin_creator_manage_views.admin_creator_application_history, name='admin_creator_application_history'),
    path('admin/manage-creators/all/', admin_creator_manage_views.admin_all_creators_list, name='admin_all_creators_list'),
    path('admin/manage-creators/banned/', admin_creator_manage_views.admin_banned_creators_list, name='admin_banned_creators_list'),
    path('admin/manage-creators/detail/<int:user_id>/', admin_creator_manage_views.admin_view_creator_detail, name='admin_view_creator_detail'),
    path('admin/manage-creators/uploads/', admin_creator_manage_views.admin_creator_uploads_view, name='admin_creator_uploads'),
    path('admin/creators/<int:user_id>/approve/', creator_admin_actions_views.admin_approve_creator, name='admin_approve_creator'),
    path('admin/creators/<int:user_id>/reject/', creator_admin_actions_views.admin_reject_creator, name='admin_reject_creator'),
    path('admin/creators/<int:user_id>/ban/', creator_admin_actions_views.admin_ban_creator, name='admin_ban_creator'),
    path('admin/creators/<int:user_id>/unban/', creator_admin_actions_views.admin_unban_creator, name='admin_unban_creator'),
    path('admin/manage-creators/withdrawal-requests/', admin_creator_manage_views.admin_manage_withdrawal_requests, name='admin_manage_withdrawal_requests'),
    path('admin/financials/', admin_manage_financials_views.admin_financials_overview, name='admin_financials_overview'),
    path('admin/financials/report/pdf/', admin_manage_financials_views.admin_generate_financials_report_pdf, name='admin_generate_financials_report_pdf'),
    path('admin/manage-support/overview/', admin_ticket_management_views.admin_manage_tickets_overview_view, name='admin_manage_tickets_overview'),
    path('admin/manage-support/tickets/all/', admin_ticket_management_views.admin_all_tickets_list_view, name='admin_all_tickets_list'),
    path('admin/manage-support/tickets/open/', admin_ticket_management_views.admin_open_tickets_list_view, name='admin_open_tickets_list'),
    path('admin/manage-support/tickets/closed/', admin_ticket_management_views.admin_closed_tickets_list_view, name='admin_closed_tickets_list'),
    path('admin/manage-support/ticket/<uuid:ticket_uuid>/detail/', admin_ticket_management_views.admin_ticket_detail_view, name='admin_ticket_detail'),
    path('admin/admins/manage/', admin_management_views.manage_admins_list_view, name='admin_manage_admins'),
    path('admin/admins/edit/<int:admin_id>/', admin_management_views.edit_admin_view, name='admin_edit_user'),

    # --- Community Chatroom Feature ---
    path('features/community-chatrooms/welcome/', community_chatrooms_feature_views.ChatroomWelcomeView.as_view(), name='chatroom_welcome'),
    path('features/community-chatrooms/home/', community_chatrooms_feature_views.CommunityChatroomHomeView.as_view(), name='chatroom_home'),
    path('features/community-chatrooms/create/', community_chatrooms_feature_views.CreateChatRoomView.as_view(), name='chatroom_create'),
    path('features/community-chatrooms/<uuid:room_id>/', community_chatrooms_feature_views.ChatRoomDetailView.as_view(), name='chatroom_detail'),
    path('features/community-chatrooms/<uuid:room_id>/leave/', community_chatrooms_feature_views.LeaveChatRoomView.as_view(), name='chatroom_leave'),
    path('features/community-chatrooms/<uuid:room_id>/invite/', community_chatrooms_feature_views.InviteUserToChatRoomView.as_view(), name='chatroom_invite_user'),

    # --- Chatroom Invitation URLs ---
    path('features/community-chatrooms/invitations/', community_chatrooms_feature_views.ChatInvitationsListView.as_view(), name='chat_invitations'),
    path('features/community-chatrooms/invitations/<uuid:invitation_id>/respond/', community_chatrooms_feature_views.RespondToChatInvitationView.as_view(), name='chatroom_invitation_respond'),

    # --- Updated URLs for Other Chat Features ---
    path('features/community-chatrooms/my-rooms/', community_chatrooms_feature_views.MyChatRoomsView.as_view(), name='my_chatrooms'), 
    path('features/community-chatrooms/joined-rooms/', community_chatrooms_feature_views.JoinedChatRoomsView.as_view(), name='joined_chatrooms'), 
    path('features/community-chatrooms/past-rooms/', community_chatrooms_feature_views.PastChatRoomsView.as_view(), name='past_chatrooms'), # MODIFIED
]

urlpatterns += staticfiles_urlpatterns()
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
