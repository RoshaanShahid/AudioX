# AudioXApp/admin.py

from django.contrib import admin
from .models import (
    User, Admin, CoinTransaction, AudiobookPurchase, CreatorEarning,
    Creator, CreatorApplicationLog, WithdrawalAccount, WithdrawalRequest,
    Audiobook, Chapter, Review, Subscription, AudiobookViewLog,
    TicketCategory, Ticket, TicketMessage,
    ListeningHistory, UserLibraryItem,
    UserDownloadedAudiobook
)
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import reverse

# --- User Admin ---
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'username', 'full_name', 'subscription_type', 'is_active', 'is_staff', 'is_creator')
    search_fields = ('email', 'username', 'full_name')
    list_filter = ('is_active', 'is_staff', 'subscription_type', 'date_joined')
    ordering = ('-date_joined',)

# --- Custom Admin ---
@admin.register(Admin)
class CustomAdminAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'get_display_roles_list_admin', 'is_active', 'last_login')
    search_fields = ('username', 'email')
    list_filter = ('is_active', 'roles')
    ordering = ('username',)

    def get_display_roles_list_admin(self, obj):
        return ", ".join(obj.get_display_roles_list())
    get_display_roles_list_admin.short_description = 'Roles'

# --- Audiobook Admin ---
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

# --- Chapter Admin ---
@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ('chapter_name', 'audiobook_title_link', 'chapter_order', 'is_tts_generated', 'created_at')
    search_fields = ('chapter_name', 'audiobook__title')
    list_filter = ('is_tts_generated', 'audiobook__language', 'created_at')
    ordering = ('audiobook', 'chapter_order')
    autocomplete_fields = ['audiobook']

    def audiobook_title_link(self, obj):
        link = reverse("admin:AudioXApp_audiobook_change", args=[obj.audiobook.pk])
        return format_html('<a href="{}">{}</a>', link, obj.audiobook.title)
    audiobook_title_link.short_description = 'Audiobook'
    audiobook_title_link.admin_order_field = 'audiobook__title'

# --- Creator Admin ---
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

# --- User Downloaded Audiobook Admin ---
@admin.register(UserDownloadedAudiobook)
class UserDownloadedAudiobookAdmin(admin.ModelAdmin):
    list_display = (
        'user_email',
        'audiobook_title',
        'download_date',
        'is_active',
        'expiry_date',
        'last_verified_at',
        'download_id'
    )
    search_fields = (
        'user__username',
        'user__email',
        'audiobook__title',
        'download_id'
    )
    list_filter = (
        'is_active',
        'download_date',
        'expiry_date',
        'last_verified_at',
        ('audiobook', admin.RelatedOnlyFieldListFilter),
        ('user', admin.RelatedOnlyFieldListFilter),
    )
    ordering = ('-download_date',)
    readonly_fields = ('download_id', 'download_date', 'user', 'audiobook')
    
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
            try:
                user_admin_url = reverse(f"admin:{obj.user._meta.app_label}_user_change", args=[obj.user.pk])
                return format_html('<a href="{}">{}</a>', user_admin_url, obj.user.email)
            except Exception:
                return obj.user.email
        return "-"
    user_email.short_description = 'User Email'
    user_email.admin_order_field = 'user__email'

    def audiobook_title(self, obj):
        if obj.audiobook:
            try:
                audiobook_admin_url = reverse(f"admin:{obj.audiobook._meta.app_label}_audiobook_change", args=[obj.audiobook.pk])
                return format_html('<a href="{}">{}</a>', audiobook_admin_url, obj.audiobook.title)
            except Exception:
                return obj.audiobook.title
        return "-"
    audiobook_title.short_description = 'Audiobook Title'
    audiobook_title.admin_order_field = 'audiobook__title'