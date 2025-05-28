# AudioXApp/admin.py

from django.contrib import admin
from .models import (
    User, Admin, CoinTransaction, AudiobookPurchase, CreatorEarning,
    Creator, CreatorApplicationLog, WithdrawalAccount, WithdrawalRequest,
    Audiobook, Chapter, Review, Subscription, AudiobookViewLog,
    TicketCategory, Ticket, TicketMessage,
    ListeningHistory, UserLibraryItem,
    UserDownloadedAudiobook # <<< --- IMPORT THE NEW MODEL
)
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html # For custom display methods
from django.urls import reverse # For linking to related objects

# Existing admin registrations (assuming you have them, example below)
# If you already have an admin.py, these would be present.
# Keep your existing ModelAdmin classes and registrations.

# Example of how your existing UserAdmin might look (keep yours if different)
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'username', 'full_name', 'subscription_type', 'is_active', 'is_staff', 'is_creator')
    search_fields = ('email', 'username', 'full_name')
    list_filter = ('is_active', 'is_staff', 'subscription_type', 'date_joined')
    ordering = ('-date_joined',)
    # Add other configurations as needed for your User model

@admin.register(Admin)
class CustomAdminAdmin(admin.ModelAdmin): # Renamed to avoid conflict with django.contrib.admin
    list_display = ('username', 'email', 'get_display_roles_list_admin', 'is_active', 'last_login')
    search_fields = ('username', 'email')
    list_filter = ('is_active', 'roles')
    ordering = ('username',)

    def get_display_roles_list_admin(self, obj):
        return ", ".join(obj.get_display_roles_list())
    get_display_roles_list_admin.short_description = 'Roles'


@admin.register(Audiobook)
class AudiobookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'creator_link', 'status', 'is_paid', 'price', 'total_views', 'total_sales', 'created_at', 'updated_at')
    search_fields = ('title', 'author', 'slug', 'creator__creator_name', 'creator__user__username')
    list_filter = ('status', 'is_paid', 'source', 'language', 'genre', 'created_at')
    ordering = ('-created_at',)
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('total_views', 'total_sales', 'total_revenue_generated', 'created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('title', 'slug', 'author', 'narrator', 'description', 'cover_image')
        }),
        ('Categorization & Status', {
            'fields': ('language', 'genre', 'status', 'source', 'publish_date')
        }),
        ('Creator & Monetization', {
            'fields': ('creator', 'is_creator_book', 'is_paid', 'price')
        }),
        ('Analytics (Read-Only)', {
            'fields': ('total_views', 'total_sales', 'total_revenue_generated', 'duration'),
            'classes': ('collapse',)
        }),
        ('Timestamps (Read-Only)', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def creator_link(self, obj):
        if obj.creator:
            link = reverse("admin:AudioXApp_creator_change", args=[obj.creator.pk])
            return format_html('<a href="{}">{}</a>', link, obj.creator)
        return "-"
    creator_link.short_description = 'Creator'
    creator_link.admin_order_field = 'creator'


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ('chapter_name', 'audiobook_title_link', 'chapter_order', 'is_tts_generated', 'created_at')
    search_fields = ('chapter_name', 'audiobook__title')
    list_filter = ('is_tts_generated', 'audiobook__language', 'created_at')
    ordering = ('audiobook', 'chapter_order')
    autocomplete_fields = ['audiobook'] # Makes selecting audiobook easier

    def audiobook_title_link(self, obj):
        link = reverse("admin:AudioXApp_audiobook_change", args=[obj.audiobook.pk])
        return format_html('<a href="{}">{}</a>', link, obj.audiobook.title)
    audiobook_title_link.short_description = 'Audiobook'
    audiobook_title_link.admin_order_field = 'audiobook__title'


@admin.register(Creator)
class CreatorAdmin(admin.ModelAdmin):
    list_display = ('user_email', 'creator_name', 'creator_unique_name', 'cid', 'verification_status', 'is_banned', 'available_balance', 'approved_at')
    search_fields = ('user__email', 'user__username', 'creator_name', 'creator_unique_name', 'cid')
    list_filter = ('verification_status', 'is_banned', 'approved_at', 'last_application_date')
    ordering = ('-user__date_joined',)
    readonly_fields = ('total_earning', 'approved_at', 'banned_at', 'last_application_date')
    autocomplete_fields = ['user', 'approved_by', 'banned_by']

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User Email'
    user_email.admin_order_field = 'user__email'


# --- NEW ADMIN REGISTRATION FOR UserDownloadedAudiobook ---
@admin.register(UserDownloadedAudiobook)
class UserDownloadedAudiobookAdmin(admin.ModelAdmin):
    list_display = (
        'user_email',
        'audiobook_title',
        'download_date',
        'is_active',
        'expiry_date',
        'last_verified_at',
        'download_id' # Displaying the UUID for reference
    )
    search_fields = (
        'user__username',
        'user__email',
        'audiobook__title',
        'download_id' # Search by UUID
    )
    list_filter = (
        'is_active',
        'download_date',
        'expiry_date',
        'last_verified_at',
        ('audiobook', admin.RelatedOnlyFieldListFilter), # Filter by audiobook
        ('user', admin.RelatedOnlyFieldListFilter),       # Filter by user
    )
    ordering = ('-download_date',)
    readonly_fields = ('download_id', 'download_date', 'user', 'audiobook') # Make some fields read-only
    # autocomplete_fields = ['user', 'audiobook'] # If you have many users/audiobooks

    fieldsets = (
        (None, {
            'fields': ('download_id', 'user', 'audiobook')
        }),
        ('Status & Timestamps', {
            'fields': ('is_active', 'download_date', 'expiry_date', 'last_verified_at')
        }),
    )

    def user_email(self, obj):
        if obj.user:
            # Assuming your User model is registered with an admin site
            # and 'AudioXApp' is your app_label.
            try:
                user_admin_url = reverse(f"admin:{obj.user._meta.app_label}_user_change", args=[obj.user.pk])
                return format_html('<a href="{}">{}</a>', user_admin_url, obj.user.email)
            except Exception: # Fallback if reverse fails
                return obj.user.email
        return "-"
    user_email.short_description = 'User Email'
    user_email.admin_order_field = 'user__email'

    def audiobook_title(self, obj):
        if obj.audiobook:
            try:
                audiobook_admin_url = reverse(f"admin:{obj.audiobook._meta.app_label}_audiobook_change", args=[obj.audiobook.pk])
                return format_html('<a href="{}">{}</a>', audiobook_admin_url, obj.audiobook.title)
            except Exception: # Fallback if reverse fails
                return obj.audiobook.title
        return "-"
    audiobook_title.short_description = 'Audiobook Title'
    audiobook_title.admin_order_field = 'audiobook__title'

# --- END NEW ADMIN REGISTRATION ---

# Register other models if they are not already (examples, keep your existing ones)
# admin.site.register(CoinTransaction)
# admin.site.register(AudiobookPurchase)
# admin.site.register(CreatorEarning)
# admin.site.register(CreatorApplicationLog)
# admin.site.register(WithdrawalAccount)
# admin.site.register(WithdrawalRequest)
# admin.site.register(Review)
# admin.site.register(Subscription)
# admin.site.register(AudiobookViewLog)
# admin.site.register(TicketCategory)
# admin.site.register(Ticket)
# admin.site.register(TicketMessage)
# admin.site.register(ListeningHistory)
# admin.site.register(UserLibraryItem)

# Ensure all your models that you want in the admin are registered.
# The @admin.register decorator is a clean way to do it, or use admin.site.register(Model, ModelAdminClass).
