"""
============================================================================
AUDIOX PLATFORM - DJANGO MODELS
============================================================================
Comprehensive data models for the AudioX audiobook platform including:
- User management with subscription tiers and usage limits
- Creator profiles and verification system
- Audiobook and chapter management with moderation
- Coin-based economy and transaction tracking
- Community features (chat rooms, reviews, support tickets)
- Admin management and content moderation

Author: AudioX Development Team
Version: 2.1
Last Updated: 2024
============================================================================
"""

# ============================================================================
# IMPORTS AND DEPENDENCIES
# ============================================================================

import uuid
import os
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.db import models, transaction
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.contrib.auth.hashers import make_password, check_password
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from django.core.files.storage import default_storage
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
from django.urls import reverse
from django.conf import settings
from django.db.models import Avg, Sum, F, Prefetch, Q, Max, Value, IntegerField
from django.db.models.functions import Cast, Substr, Replace

from .audio_utils import get_audio_duration

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logger = logging.getLogger(__name__)

# ============================================================================
# FILE UPLOAD PATH FUNCTIONS
# ============================================================================

def creator_cnic_path(instance, filename):
    """
    Generate file path for creator CNIC documents.
    
    Args:
        instance: Model instance (CreatorApplicationLog or Creator)
        filename: Original filename
        
    Returns:
        str: Generated file path
    """
    user_id = None
    if hasattr(instance, 'creator') and instance.creator and hasattr(instance.creator, 'user_id'):
        user_id = instance.creator.user_id
    elif hasattr(instance, 'user') and instance.user and hasattr(instance.user, 'user_id'):
        user_id = instance.user.user_id

    if user_id:
        _, extension = os.path.splitext(filename)
        unique_filename = f'{uuid.uuid4()}{extension}'
        if isinstance(instance, CreatorApplicationLog):
            path_prefix = 'creator_application_logs'
        elif isinstance(instance, Creator):
            path_prefix = 'creator_verification'
        else:
            path_prefix = 'creator_documents/unknown_type'
        return f'{path_prefix}/{user_id}/{unique_filename}'
    return f'creator_documents/unknown_user/{uuid.uuid4()}{os.path.splitext(filename)[1]}'

def chatroom_cover_image_path(instance, filename):
    """Generate file path for chatroom cover images."""
    room_id_str = str(instance.room_id) if instance.room_id else "new_room"
    _, extension = os.path.splitext(filename)
    unique_filename = f'{uuid.uuid4().hex[:12]}{extension}'
    return f'chatroom_covers/{room_id_str}/{unique_filename}'

def creator_profile_pic_path(instance, filename):
    """Generate file path for creator profile pictures."""
    user_id = instance.user.user_id if hasattr(instance, 'user') and instance.user else 'unknown'
    _, extension = os.path.splitext(filename)
    unique_filename = f'{uuid.uuid4()}{extension}'
    return f'creator_profile_pics/{user_id}/{unique_filename}'

def withdrawal_payment_slip_path(instance, filename):
    """Generate file path for withdrawal payment slips."""
    creator_id = instance.creator.user_id if instance.creator and hasattr(instance.creator, 'user_id') else 'unknown_creator'
    request_pk_str = str(instance.id) if instance.id else "new"
    _, extension = os.path.splitext(filename)
    unique_filename = f'slip_{request_pk_str}_{uuid.uuid4().hex[:6]}{extension}'
    return f'withdrawal_slips/{creator_id}/{unique_filename}'

# ============================================================================
# USER MANAGEMENT MODELS
# ============================================================================

class UserManager(BaseUserManager):
    """
    Custom user manager for handling user creation with required fields.
    """
    
    def create_user(self, email, password=None, **extra_fields):
        """
        Create and save a regular user with the given email and password.
        
        Args:
            email (str): User's email address
            password (str): User's password
            **extra_fields: Additional user fields
            
        Returns:
            User: Created user instance
            
        Raises:
            ValueError: If required fields are missing
        """
        if not email:
            raise ValueError(_('The Email field must be set'))
        email = self.normalize_email(email)
        if not extra_fields.get('username'):
            raise ValueError(_('The Username field must be set'))
        if not extra_fields.get('full_name'):
            raise ValueError(_('The Full Name field must be set'))
        
        # Set default values for optional fields
        extra_fields.setdefault('phone_number', None)
        extra_fields.setdefault('bio', None)
        
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Create and save a superuser with the given email and password.
        
        Args:
            email (str): Superuser's email address
            password (str): Superuser's password
            **extra_fields: Additional user fields
            
        Returns:
            User: Created superuser instance
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))
        
        # Set default superuser fields
        extra_fields.setdefault('username', email.split('@')[0] + '_super')
        extra_fields.setdefault('full_name', 'Super User Admin')
        extra_fields.setdefault('requires_extra_details_post_social_signup', False)
        extra_fields.setdefault('phone_number', None)
        extra_fields.setdefault('bio', 'Default administrator bio.')
        
        return self.create_user(email, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model with subscription tiers and usage tracking.
    
    Features:
    - Email-based authentication
    - Subscription management (FREE/PREMIUM)
    - Usage limits for FREE users
    - Coin balance management
    - Social signup support
    - Platform ban functionality
    """
    
    # ============================================================================
    # BASIC USER FIELDS
    # ============================================================================
    
    user_id = models.BigAutoField(primary_key=True)
    full_name = models.CharField(
        max_length=255, 
        blank=False, 
        null=False,
        help_text=_("User's full name")
    )
    username = models.CharField(
        max_length=255, 
        unique=True,
        help_text=_("Unique username for the user")
    )
    email = models.EmailField(
        unique=True,
        help_text=_("User's email address (used for login)")
    )
    phone_number = models.CharField(
        max_length=20, 
        blank=True, 
        null=True, 
        default=None,
        help_text=_("User's phone number (optional)")
    )
    bio = models.TextField(
        blank=True, 
        null=True, 
        default=None,
        help_text=_("User's biography (optional)")
    )
    profile_pic = models.ImageField(
        upload_to='profile_pics/', 
        blank=True, 
        null=True,
        help_text=_("User's profile picture")
    )
    
    # ============================================================================
    # SUBSCRIPTION AND ACCOUNT STATUS
    # ============================================================================
    
    SUBSCRIPTION_CHOICES = [
        ('FR', 'Free'), 
        ('PR', 'Premium')
    ]
    
    subscription_type = models.CharField(
        max_length=2, 
        choices=SUBSCRIPTION_CHOICES, 
        default='FR',
        help_text=_("User's subscription tier")
    )
    coins = models.IntegerField(
        default=0,
        help_text=_("User's current coin balance")
    )
    
    # ============================================================================
    # ACCOUNT STATUS AND PERMISSIONS
    # ============================================================================
    
    is_active = models.BooleanField(
        default=True, 
        help_text=_("Designates whether this user should be treated as active. Unselect this instead of deleting accounts.")
    )
    is_staff = models.BooleanField(
        default=False,
        help_text=_("Designates whether the user can log into the admin site.")
    )
    is_superuser = models.BooleanField(
        default=False,
        help_text=_("Designates that this user has all permissions without explicitly assigning them.")
    )
    date_joined = models.DateTimeField(
        auto_now_add=True,
        help_text=_("Date when the user account was created")
    )
    is_2fa_enabled = models.BooleanField(
        default=False, 
        verbose_name=_("2FA Enabled"),
        help_text=_("Whether two-factor authentication is enabled")
    )
    
    # ============================================================================
    # PLATFORM BAN MANAGEMENT
    # ============================================================================
    
    is_banned_by_admin = models.BooleanField(
        default=False, 
        help_text=_("Set to true if the user is banned from the entire platform by an admin.")
    )
    platform_ban_reason = models.TextField(
        blank=True, 
        null=True, 
        help_text=_("Reason provided by admin if the user is banned from the platform.")
    )
    platform_banned_at = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text=_("Timestamp when the user was banned from the platform.")
    )
    platform_banned_by = models.ForeignKey(
        'Admin', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='platform_banned_users', 
        help_text=_("Admin who banned this user from the platform.")
    )
    
    # ============================================================================
    # SOCIAL SIGNUP SUPPORT
    # ============================================================================
    
    requires_extra_details_post_social_signup = models.BooleanField(
        default=False, 
        help_text=_("True if user signed up via social media and needs to provide phone number and confirm/edit full name.")
    )
    
    # ============================================================================
    # USAGE TRACKING FOR FREE VS PREMIUM LIMITS
    # ============================================================================
    
    # Document-to-Audio Usage Tracking
    monthly_document_conversions = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of document-to-audio conversions used this month")
    )
    last_document_conversion_reset = models.DateTimeField(
        default=timezone.now,
        help_text=_("Last time the document conversion counter was reset")
    )
    
    # Coin Gifting Usage Tracking
    monthly_coin_gifts = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of coin gifts sent this month")
    )
    last_coin_gift_reset = models.DateTimeField(
        default=timezone.now,
        help_text=_("Last time the coin gift counter was reset")
    )
    
    # Usage Limits Constants
    FREE_MONTHLY_DOCUMENT_LIMIT = 3
    FREE_MONTHLY_COIN_GIFT_LIMIT = 3
    
    # ============================================================================
    # RELATIONSHIPS
    # ============================================================================
    
    purchased_audiobooks = models.ManyToManyField(
        'Audiobook', 
        through='AudiobookPurchase', 
        related_name='purchased_by_users'
    )
    library_audiobooks = models.ManyToManyField(
        'Audiobook', 
        through='UserLibraryItem', 
        related_name='saved_in_libraries', 
        blank=True
    )
    
    # ============================================================================
    # DJANGO AUTH CONFIGURATION
    # ============================================================================
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'full_name']
    objects = UserManager()

    class Meta:
        db_table = 'USERS'
        verbose_name = _("User")
        verbose_name_plural = _("Users")

    def __str__(self):
        return self.email

    # ============================================================================
    # USAGE TRACKING METHODS FOR FREE VS PREMIUM LIMITS
    # ============================================================================
    
    def _reset_monthly_counter_if_needed(self, counter_type):
        """
        Reset monthly counter if a month has passed since last reset.
        
        Args:
            counter_type (str): Type of counter ('document' or 'coin_gift')
        """
        now = timezone.now()
        
        if counter_type == 'document':
            last_reset = self.last_document_conversion_reset
            if (now - last_reset).days >= 30:  # Reset every 30 days
                self.monthly_document_conversions = 0
                self.last_document_conversion_reset = now
                self.save(update_fields=['monthly_document_conversions', 'last_document_conversion_reset'])
                logger.info(f"Reset document conversion counter for user {self.username}")
                
        elif counter_type == 'coin_gift':
            last_reset = self.last_coin_gift_reset
            if (now - last_reset).days >= 30:  # Reset every 30 days
                self.monthly_coin_gifts = 0
                self.last_coin_gift_reset = now
                self.save(update_fields=['monthly_coin_gifts', 'last_coin_gift_reset'])
                logger.info(f"Reset coin gift counter for user {self.username}")
    
    def can_use_document_conversion(self):
        """
        Check if user can perform document-to-audio conversion.
        
        Returns:
            tuple: (can_use: bool, error_message: str or None)
        """
        if self.subscription_type == 'PR':  # Premium users have unlimited access
            return True, None
            
        # Reset counter if needed
        self._reset_monthly_counter_if_needed('document')
        
        if self.monthly_document_conversions >= self.FREE_MONTHLY_DOCUMENT_LIMIT:
            return False, f"You've reached your monthly limit of {self.FREE_MONTHLY_DOCUMENT_LIMIT} document conversions. Upgrade to Premium for unlimited access."
        
        return True, None
    
    def can_gift_coins(self):
        """
        Check if user can gift coins.
        
        Returns:
            tuple: (can_gift: bool, error_message: str or None)
        """
        if self.subscription_type == 'PR':  # Premium users have unlimited access
            return True, None
            
        # Reset counter if needed
        self._reset_monthly_counter_if_needed('coin_gift')
        
        if self.monthly_coin_gifts >= self.FREE_MONTHLY_COIN_GIFT_LIMIT:
            return False, f"You've reached your monthly limit of {self.FREE_MONTHLY_COIN_GIFT_LIMIT} coin gifts. Upgrade to Premium for unlimited gifting."
        
        return True, None
    
    def increment_document_conversion_usage(self):
        """Increment the document conversion usage counter."""
        if self.subscription_type == 'FR':  # Only track for free users
            self._reset_monthly_counter_if_needed('document')
            self.monthly_document_conversions = F('monthly_document_conversions') + 1
            self.save(update_fields=['monthly_document_conversions'])
            self.refresh_from_db(fields=['monthly_document_conversions'])
            logger.info(f"User {self.username} used document conversion. Count: {self.monthly_document_conversions}")
    
    def increment_coin_gift_usage(self):
        """Increment the coin gift usage counter."""
        if self.subscription_type == 'FR':  # Only track for free users
            self._reset_monthly_counter_if_needed('coin_gift')
            self.monthly_coin_gifts = F('monthly_coin_gifts') + 1
            self.save(update_fields=['monthly_coin_gifts'])
            self.refresh_from_db(fields=['monthly_coin_gifts'])
            logger.info(f"User {self.username} sent coin gift. Count: {self.monthly_coin_gifts}")
    
    def get_usage_status(self):
        """
        Get current usage status for the user.
        
        FIXED: Properly handles new users and ensures they get full allowance.
        
        Returns:
            dict: Usage status with limits and remaining counts
        """
        if self.subscription_type == 'PR':
            return {
                'is_premium': True,
                'document_conversions': {'used': 0, 'limit': 'Unlimited', 'remaining': 'Unlimited'},
                'coin_gifts': {'used': 0, 'limit': 'Unlimited', 'remaining': 'Unlimited'}
            }
        
        # Reset counters if needed (this handles new users properly)
        self._reset_monthly_counter_if_needed('document')
        self._reset_monthly_counter_if_needed('coin_gift')
        
        # FIXED: Calculate remaining properly for new users
        document_remaining = max(0, self.FREE_MONTHLY_DOCUMENT_LIMIT - self.monthly_document_conversions)
        coin_gift_remaining = max(0, self.FREE_MONTHLY_COIN_GIFT_LIMIT - self.monthly_coin_gifts)
        
        return {
            'is_premium': False,
            'document_conversions': {
                'used': self.monthly_document_conversions,
                'limit': self.FREE_MONTHLY_DOCUMENT_LIMIT,
                'remaining': document_remaining
            },
            'coin_gifts': {
                'used': self.monthly_coin_gifts,
                'limit': self.FREE_MONTHLY_COIN_GIFT_LIMIT,
                'remaining': coin_gift_remaining
            }
        }

    # ============================================================================
    # USER UTILITY METHODS
    # ============================================================================

    @property
    def is_creator(self):
        """
        Check if user is an approved creator.
        
        Returns:
            bool: True if user is an approved and non-banned creator
        """
        try:
            if hasattr(self, 'creator_profile'):
                profile = self.creator_profile
                return profile.verification_status == 'approved' and not getattr(profile, 'is_banned', False)
            return False
        except Exception:
            return False

    def has_purchased_audiobook(self, audiobook):
        """
        Check if user has purchased audiobook through ANY method (Stripe OR Coins).
        
        Args:
            audiobook: Audiobook instance to check
            
        Returns:
            bool: True if user has purchased the audiobook
        """
        # Check Stripe purchases
        stripe_purchase_exists = AudiobookPurchase.objects.filter(
            user=self, 
            audiobook=audiobook, 
            status='COMPLETED'
        ).exists()
        
        if stripe_purchase_exists:
            return True
        
        # Check coin purchases
        coin_purchase_exists = CoinPurchase.objects.filter(
            user=self,
            audiobook=audiobook
        ).exists()
        
        return coin_purchase_exists

    def is_in_library(self, audiobook):
        """
        Check if audiobook is in user's library.
        
        Args:
            audiobook: Audiobook instance to check
            
        Returns:
            bool: True if audiobook is in user's library
        """
        return self.library_audiobooks.filter(pk=audiobook.pk).exists()

    def has_unlocked_chapter(self, chapter):
        """
        Check if user has unlocked a specific chapter via coin purchase.
        
        Args:
            chapter: Chapter instance to check
            
        Returns:
            bool: True if user has unlocked the chapter
        """
        return ChapterUnlock.objects.filter(user=self, chapter=chapter).exists()

# ============================================================================
# COIN SYSTEM MODELS
# ============================================================================

class CoinPack(models.Model):
    """
    Model for coin packages that users can purchase.
    
    Represents different coin bundles with pricing and bonus coins.
    """
    
    name = models.CharField(
        max_length=100,
        help_text=_("Display name for the coin pack")
    )
    coins = models.PositiveIntegerField(
        help_text=_("Base number of coins in this pack")
    )
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text=_("Price of the coin pack in PKR")
    )
    bonus_coins = models.PositiveIntegerField(
        default=0,
        help_text=_("Additional bonus coins included")
    )
    is_popular = models.BooleanField(
        default=False,
        help_text=_("Mark this pack as popular for UI highlighting")
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_("Whether this pack is available for purchase")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['price']
        db_table = 'COIN_PACKS'
        verbose_name = _("Coin Pack")
        verbose_name_plural = _("Coin Packs")
        
    def __str__(self):
        return f"{self.name} - {self.coins} coins"
    
    @property
    def total_coins(self):
        """Returns total coins including bonus."""
        return self.coins + self.bonus_coins
    
    @property
    def price_per_coin(self):
        """Calculate price per coin."""
        if self.coins > 0:
            return self.price / self.coins
        return 0
    
    @property
    def discount_percentage(self):
        """Calculate discount percentage based on bonus coins."""
        if self.bonus_coins > 0 and self.coins > 0:
            return (self.bonus_coins / self.coins) * 100
        return 0

class CoinTransaction(models.Model):
    """
    Model for tracking all coin-related transactions.
    
    Handles purchases, gifts, spending, refunds, and other coin movements.
    """
    
    TRANSACTION_TYPES = (
        ('purchase', 'Purchase'), 
        ('reward', 'Reward'), 
        ('spent', 'Spent'), 
        ('refund', 'Refund'), 
        ('gift_sent', 'Gift Sent'), 
        ('gift_received', 'Gift Received'), 
        ('withdrawal', 'Withdrawal'), 
        ('withdrawal_fee', 'Withdrawal Fee'),
        ('audiobook_purchase', 'Audiobook Purchase'),
    )
    
    STATUS_CHOICES = (
        ('completed', 'Completed'), 
        ('pending', 'Pending'), 
        ('failed', 'Failed'), 
        ('processing', 'Processing'), 
        ('rejected', 'Rejected')
    )
    
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='coin_transactions',
        help_text=_("User who performed the transaction")
    )
    transaction_type = models.CharField(
        max_length=20, 
        choices=TRANSACTION_TYPES,
        help_text=_("Type of coin transaction")
    )
    amount = models.IntegerField(
        help_text=_("Amount of coins (positive for credit, negative for debit)")
    )
    transaction_date = models.DateTimeField(
        auto_now_add=True,
        help_text=_("When the transaction occurred")
    )
    status = models.CharField(
        max_length=10, 
        choices=STATUS_CHOICES, 
        default='pending',
        help_text=_("Current status of the transaction")
    )
    pack_name = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text=_("Name of coin pack if this was a purchase")
    )
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text=_("Price paid in PKR for coin purchases")
    )
    sender = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='gifts_sent',
        help_text=_("User who sent the gift (for gift transactions)")
    )
    recipient = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='gifts_received',
        help_text=_("User who received the gift (for gift transactions)")
    )
    description = models.TextField(
        blank=True, 
        null=True,
        help_text=_("Additional description or notes")
    )
    related_audiobook = models.ForeignKey(
        'Audiobook', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        help_text=_("Audiobook purchased with coins")
    )
    
    class Meta:
        db_table = 'COIN_TRANSACTIONS'
        ordering = ['-transaction_date']
        verbose_name = _("Coin Transaction")
        verbose_name_plural = _("Coin Transactions")
        
    def __str__(self):
        return f"{self.user.username} - {self.get_transaction_type_display()} ({self.amount}) on {self.transaction_date.strftime('%Y-%m-%d')}"

class CoinPurchase(models.Model):
    """
    Track coin-based purchases of audiobooks.
    
    Separate from regular purchases to handle coin-specific logic.
    """
    
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='coin_purchases',
        help_text=_("User who made the purchase")
    )
    audiobook = models.ForeignKey(
        'Audiobook', 
        on_delete=models.CASCADE, 
        related_name='coin_purchases',
        help_text=_("Audiobook that was purchased")
    )
    coins_spent = models.PositiveIntegerField(
        help_text=_("Number of coins spent on this purchase")
    )
    purchase_date = models.DateTimeField(
        auto_now_add=True,
        help_text=_("When the purchase was made")
    )
    
    # Commission tracking (same logic as Stripe)
    creator_earning = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00,
        help_text=_("Amount credited to creator")
    )
    platform_commission = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00,
        help_text=_("Platform commission from this purchase")
    )
    
    class Meta:
        unique_together = ('user', 'audiobook')  # Prevent duplicate purchases
        db_table = 'COIN_PURCHASES'
        verbose_name = _("Coin Purchase")
        verbose_name_plural = _("Coin Purchases")
        
    def __str__(self):
        return f"{self.user.username} - {self.audiobook.title} ({self.coins_spent} coins)"

# ============================================================================
# ADMIN MANAGEMENT MODELS
# ============================================================================

class AdminManager(BaseUserManager):
    """Custom manager for Admin model."""
    
    def create_admin(self, email, username, password, roles, **extra_fields):
        """
        Create a new admin user.
        
        Args:
            email (str): Admin's email
            username (str): Admin's username
            password (str): Admin's password
            roles (str): Comma-separated list of roles
            **extra_fields: Additional fields
            
        Returns:
            Admin: Created admin instance
        """
        if not email: 
            raise ValueError('Admin must have an email address')
        if not username: 
            raise ValueError('Admin must have a username')
        if not password: 
            raise ValueError('Admin must have a password')
        if not roles: 
            raise ValueError('Admin must have at least one role')
        
        email = self.normalize_email(email)
        admin = self.model(email=email, username=username, roles=roles, **extra_fields)
        admin.set_password(password)
        admin.save(using=self._db)
        return admin

class Admin(models.Model):
    """
    Custom admin model with role-based permissions.
    
    Separate from Django's built-in admin for custom role management.
    """
    
    class RoleChoices(models.TextChoices):
        FULL_ACCESS = 'full_access', _('Full Access (Grants all permissions)')
        MANAGE_CREATORS = 'manage_creators', _('Manage Creators (Applications, profiles, content)')
        MANAGE_USERS = 'manage_users', _('Manage Users (Profiles, subscriptions, support history)')
        MANAGE_FINANCIALS = 'manage_financials', _('Manage Financials (Transactions, withdrawals, reports)')
        MANAGE_CONTENT = 'manage_content', _('Manage Content (Audiobooks, categories, site content)')
        MANAGE_SUPPORT = 'manage_support', _('Manage Support (Tickets, FAQs, user assistance)')
        MANAGE_ADMINS = 'manage_admins', _('Manage Admins (Create, edit, assign roles to other admins)')

    adminid = models.AutoField(primary_key=True)
    email = models.EmailField(
        unique=True,
        help_text=_("Admin's email address")
    )
    username = models.CharField(
        max_length=255, 
        unique=True,
        help_text=_("Admin's username")
    )
    password = models.CharField(
        max_length=128,
        help_text=_("Hashed password")
    )
    roles = models.CharField(
        max_length=512, 
        help_text=_("Comma-separated list of roles")
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_("Whether this admin account is active")
    )
    last_login = models.DateTimeField(
        blank=True, 
        null=True,
        help_text=_("Last login timestamp")
    )
    
    objects = AdminManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'roles']

    def __str__(self):
        return self.username

    def set_password(self, raw_password):
        """Set password with Django's password hashing."""
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        """Check password against stored hash."""
        return check_password(raw_password, self.password)

    def get_roles_list(self):
        """Get list of roles assigned to this admin."""
        if self.roles:
            return [role.strip() for role in self.roles.split(',') if role.strip()]
        return []

    def get_display_roles(self):
        """Get human-readable role names."""
        if not self.roles:
            return "No Roles Assigned"
        display_names = self.get_display_roles_list()
        return ", ".join(display_names) if display_names else "No Roles Assigned"

    def get_display_roles_list(self):
        """Get list of human-readable role names."""
        if not self.roles:
            return []
        current_role_choices_dict = dict(self.RoleChoices.choices)
        role_codes = self.get_roles_list()
        display_names = []
        for role_code in role_codes:
            display_name = current_role_choices_dict.get(role_code, role_code.replace('_', ' ').title())
            display_names.append(str(display_name))
        return display_names

    def has_role(self, role_value):
        """Check if admin has specific role."""
        return role_value in self.get_roles_list()

    @property
    def is_anonymous(self): 
        return False
    
    @property
    def is_authenticated(self): 
        return True
    
    def has_perm(self, perm, obj=None):
        """Check if admin has permission."""
        if not self.is_active: 
            return False
        return 'full_access' in self.get_roles_list()
    
    def has_module_perms(self, app_label):
        """Check if admin has module permissions."""
        if not self.is_active: 
            return False
        return 'full_access' in self.get_roles_list()

    class Meta:
        db_table = 'ADMINS'
        verbose_name = _("Custom Administrator")
        verbose_name_plural = _("Custom Administrators")

# ============================================================================
# AUDIOBOOK PURCHASE MODELS
# ============================================================================

class AudiobookPurchase(models.Model):
    """
    Model for tracking Stripe-based audiobook purchases.
    
    Handles payment processing, commission calculation, and purchase status.
    """
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'), 
        ('COMPLETED', 'Completed'), 
        ('FAILED', 'Failed'), 
        ('REFUNDED', 'Refunded')
    ]
    
    purchase_id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='audiobook_purchases',
        help_text=_("User who made the purchase")
    )
    audiobook = models.ForeignKey(
        'Audiobook', 
        on_delete=models.CASCADE, 
        related_name='audiobook_sales',
        help_text=_("Audiobook that was purchased")
    )
    purchase_date = models.DateTimeField(
        auto_now_add=True,
        help_text=_("When the purchase was made")
    )
    amount_paid = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        help_text=_("Total amount paid by the user in PKR.")
    )
    platform_fee_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal(getattr(settings, 'PLATFORM_FEE_PERCENTAGE_AUDIOBOOK', '10.00')), 
        help_text=_("Platform fee percentage at the time of purchase.")
    )
    platform_fee_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        help_text=_("Calculated platform fee in PKR.")
    )
    creator_share_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        help_text=_("Amount credited to the creator in PKR.")
    )
    stripe_checkout_session_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        db_index=True, 
        help_text=_("Stripe Checkout Session ID for reference.")
    )
    stripe_payment_intent_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        db_index=True, 
        help_text=_("Stripe Payment Intent ID for reference.")
    )
    status = models.CharField(
        max_length=10, 
        choices=STATUS_CHOICES, 
        default='PENDING',
        help_text=_("Current status of the purchase")
    )
    
    class Meta:
        db_table = 'AUDIOBOOK_PURCHASES'
        ordering = ['-purchase_date']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'audiobook'], 
                condition=Q(status='COMPLETED'), 
                name='unique_completed_purchase_per_user_audiobook'
            )
        ]
        verbose_name = _("Audiobook Purchase")
        verbose_name_plural = _("Audiobook Purchases")
    
    def __str__(self):
        return f"Purchase of '{self.audiobook.title}' by {self.user.username} on {self.purchase_date.strftime('%Y-%m-%d')}"
    
    def save(self, *args, **kwargs):
        """Calculate commission amounts before saving."""
        if self.amount_paid is not None:
            self.platform_fee_amount = (self.amount_paid * self.platform_fee_percentage) / Decimal('100.00')
            self.creator_share_amount = self.amount_paid - self.platform_fee_amount
        super().save(*args, **kwargs)

# ============================================================================
# CREATOR MANAGEMENT MODELS
# ============================================================================

class Creator(models.Model):
    """
    Model for creator profiles and verification.
    
    Handles creator applications, verification status, earnings, and bans.
    """
    
    VERIFICATION_STATUS_CHOICES = (
        ('pending', 'Pending Verification'), 
        ('approved', 'Approved'), 
        ('rejected', 'Rejected')
    )
    
    # Validator for unique creator names
    unique_name_validator = RegexValidator(
        regex=r'^[a-zA-Z0-9_]+$', 
        message='Unique name can only contain letters, numbers, and underscores.', 
        code='invalid_creator_unique_name'
    )
    
    # ============================================================================
    # BASIC CREATOR INFORMATION
    # ============================================================================
    
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        primary_key=True, 
        related_name='creator_profile'
    )
    cid = models.CharField(
        max_length=100, 
        unique=True, 
        null=True, 
        blank=True, 
        db_index=True, 
        help_text=_("Unique Creator ID, generated upon approval.")
    )
    creator_name = models.CharField(
        max_length=100, 
        blank=False, 
        null=False, 
        help_text=_("Public display name for the creator")
    )
    creator_unique_name = models.CharField(
        max_length=50, 
        unique=True, 
        blank=False, 
        null=False, 
        validators=[unique_name_validator], 
        help_text=_("Unique handle (@yourname) for URLs and mentions")
    )
    creator_profile_pic = models.ImageField(
        upload_to=creator_profile_pic_path, 
        blank=True, 
        null=True, 
        help_text=_("Optional: Specific profile picture for the creator page.")
    )
    
    # ============================================================================
    # FINANCIAL INFORMATION
    # ============================================================================
    
    total_earning = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0.00, 
        help_text=_("Total gross earnings from sales before platform fees.")
    )
    available_balance = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0.00, 
        help_text=_("Net earnings available for withdrawal after platform fees.")
    )
    
    # ============================================================================
    # VERIFICATION DOCUMENTS
    # ============================================================================
    
    cnic_front = models.ImageField(
        upload_to=creator_cnic_path, 
        blank=False, 
        null=True, 
        help_text=_("Front side of CNIC")
    )
    cnic_back = models.ImageField(
        upload_to=creator_cnic_path, 
        blank=False, 
        null=True, 
        help_text=_("Back side of CNIC")
    )
    
    # ============================================================================
    # VERIFICATION STATUS
    # ============================================================================
    
    verification_status = models.CharField(
        max_length=10, 
        choices=VERIFICATION_STATUS_CHOICES, 
        default='pending'
    )
    terms_accepted_at = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text=_("Timestamp when creator terms were accepted during the last application")
    )
    
    # ============================================================================
    # BAN MANAGEMENT
    # ============================================================================
    
    is_banned = models.BooleanField(
        default=False, 
        db_index=True, 
        help_text=_("Is this creator currently banned?")
    )
    ban_reason = models.TextField(
        blank=True, 
        null=True, 
        help_text=_("Reason provided by admin if creator is banned.")
    )
    banned_at = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text=_("Timestamp when the creator was banned.")
    )
    banned_by = models.ForeignKey(
        Admin, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='banned_creators', 
        help_text=_("Admin who banned this creator.")
    )
    
    # ============================================================================
    # APPLICATION MANAGEMENT
    # ============================================================================
    
    rejection_reason = models.TextField(
        blank=True, 
        null=True, 
        help_text=_("Reason provided by admin if the LATEST application is rejected")
    )
    last_application_date = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text=_("Timestamp of the most recent application submission")
    )
    application_attempts_current_month = models.PositiveIntegerField(
        default=0, 
        help_text=_("Number of applications submitted in the current cycle (resets monthly based on last_application_date)")
    )
    
    # ============================================================================
    # APPROVAL TRACKING
    # ============================================================================
    
    approved_at = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text=_("Timestamp when the application was approved.")
    )
    approved_by = models.ForeignKey(
        Admin, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='approved_creators', 
        help_text=_("Admin who approved this application.")
    )
    attempts_at_approval = models.PositiveIntegerField(
        null=True, 
        blank=True, 
        help_text=_("Number of attempts made when this application was approved.")
    )
    
    # ============================================================================
    # UI STATE MANAGEMENT
    # ============================================================================
    
    welcome_popup_shown = models.BooleanField(
        default=False, 
        help_text=_("Has the 'Welcome Creator' popup been shown?")
    )
    rejection_popup_shown = models.BooleanField(
        default=False, 
        help_text=_("Has the 'Application Rejected' popup been shown?")
    )
    
    # ============================================================================
    # ADMIN NOTES AND TRACKING
    # ============================================================================
    
    admin_notes = models.TextField(
        blank=True, 
        null=True, 
        help_text=_("Internal notes for admins regarding this creator.")
    )
    last_name_change_date = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text=_("Timestamp of the last display name change.")
    )
    last_unique_name_change_date = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text=_("Timestamp of the last unique name (@handle) change.")
    )
    last_withdrawal_request_date = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text=_("Timestamp of the last non-cancelled withdrawal request.")
    )
    profile_pic_updated_at = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text=_("Timestamp of the last profile picture update.")
    )

    class Meta:
        db_table = "CREATORS"
        verbose_name = _("Creator")
        verbose_name_plural = _("Creators")
    
    def __str__(self):
        status_part = "Banned" if self.is_banned else (self.cid or self.get_verification_status_display())
        return f"Creator: {self.creator_name or self.user.username} ({status_part})"

    @property
    def is_approved(self):
        """Check if creator is approved and not banned."""
        return self.verification_status == 'approved' and not self.is_banned

    @property
    def primary_withdrawal_account(self):
        """Get the primary withdrawal account for this creator."""
        if hasattr(self, '_prefetched_objects_cache') and 'withdrawal_accounts' in self._prefetched_objects_cache:
            for acc in self._prefetched_objects_cache['withdrawal_accounts']:
                if acc.is_primary:
                    return acc
            return None
        return self.withdrawal_accounts.filter(is_primary=True).first()

    def get_attempts_this_month(self):
        """Get number of application attempts this month."""
        if not self.last_application_date: 
            return 0
        now = timezone.now()
        if (self.last_application_date.year == now.year and self.last_application_date.month == now.month):
            return self.application_attempts_current_month
        else:
            return 0

    def can_reapply(self):
        """Check if creator can submit a new application."""
        if self.is_banned or self.verification_status in ['approved', 'pending']: 
            return False
        if self.verification_status == 'rejected':
            attempts_this_month = self.get_attempts_this_month()
            return attempts_this_month < getattr(settings, 'MAX_CREATOR_APPLICATION_ATTEMPTS', 3)
        return True

    def can_request_withdrawal(self):
        """
        Check if creator can request withdrawal.
        
        Returns:
            tuple: (can_withdraw: bool, error_message: str)
        """
        min_withdrawal_amount_setting = getattr(settings, 'MIN_CREATOR_WITHDRAWAL_AMOUNT', '50.00')
        try:
            min_withdrawal_amount = Decimal(min_withdrawal_amount_setting)
        except InvalidOperation:
            logger.error(f"Invalid MIN_CREATOR_WITHDRAWAL_AMOUNT setting: '{min_withdrawal_amount_setting}'. Defaulting to Decimal('50.00').")
            min_withdrawal_amount = Decimal('50.00')

        if self.available_balance < min_withdrawal_amount:
            return False, f"Your available balance (PKR {self.available_balance:,.2f}) is below the minimum withdrawal amount of PKR {min_withdrawal_amount:,.2f}."

        return True, ""

    def get_status_for_active_page(self):
        """Get status string for filtering on admin pages."""
        if self.is_banned:
            return 'banned'
        elif self.verification_status == 'approved':
            return 'approved'
        elif self.verification_status == 'pending':
            return 'pending'
        elif self.verification_status == 'rejected':
            return 'rejected'
        return 'all'

class CreatorEarning(models.Model):
    """
    Model for tracking creator earnings from various sources.
    
    Provides detailed earning history with transaction linking.
    """
    
    EARNING_TYPES = (
        ('sale', 'Sale Earning'), 
        ('view', 'View Earning'), 
        ('bonus', 'Bonus'), 
        ('adjustment', 'Adjustment')
    )
    
    earning_id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    creator = models.ForeignKey(
        'Creator', 
        on_delete=models.CASCADE, 
        related_name='earnings_log'
    )
    audiobook = models.ForeignKey(
        'Audiobook', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='earning_entries'
    )
    purchase = models.OneToOneField(
        AudiobookPurchase, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='earning_record', 
        help_text=_("Link to the specific purchase if this earning is from a sale.")
    )
    earning_type = models.CharField(
        max_length=10, 
        choices=EARNING_TYPES, 
        default='sale', 
        db_index=True
    )
    amount_earned = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        help_text=_("Net amount earned by the creator for this transaction.")
    )
    transaction_date = models.DateTimeField(
        default=timezone.now, 
        db_index=True
    )
    view_count_for_earning = models.PositiveIntegerField(
        null=True, 
        blank=True, 
        help_text=_("Number of views this earning entry represents, if type is 'view'.")
    )
    earning_per_view_at_transaction = models.DecimalField(
        max_digits=6, 
        decimal_places=4, 
        null=True, 
        blank=True, 
        help_text=_("Earning rate per view at the time of this transaction, if type is 'view'.")
    )
    notes = models.TextField(
        blank=True, 
        null=True, 
        help_text=_("Any notes related to this earning, e.g., reason for adjustment or bonus.")
    )
    audiobook_title_at_transaction = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        help_text=_("Title of the audiobook at the time of the transaction (denormalized).")
    )
    
    class Meta:
        db_table = 'CREATOR_EARNINGS'
        ordering = ['-transaction_date']
        verbose_name = _("Creator Earning")
        verbose_name_plural = _("Creator Earnings")
    
    def __str__(self):
        title = self.audiobook_title_at_transaction if self.audiobook_title_at_transaction else (self.audiobook.title if self.audiobook else 'Platform Earning')
        return f"Earning of PKR {self.amount_earned} for {self.creator.creator_name} from '{title}' ({self.get_earning_type_display()}) on {self.transaction_date.strftime('%Y-%m-%d')}"
    
    def save(self, *args, **kwargs):
        """Auto-populate audiobook title if not set."""
        if not self.audiobook_title_at_transaction and self.audiobook:
            self.audiobook_title_at_transaction = self.audiobook.title
        super().save(*args, **kwargs)

class CreatorApplicationLog(models.Model):
    """
    Model for logging creator application attempts.
    
    Maintains history of all application submissions for audit purposes.
    """
    
    STATUS_CHOICES = (
        ('submitted', 'Submitted'), 
        ('approved', 'Approved'), 
        ('rejected', 'Rejected')
    )
    
    log_id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    creator = models.ForeignKey(
        Creator, 
        on_delete=models.CASCADE, 
        related_name='application_logs'
    )
    application_date = models.DateTimeField(
        default=timezone.now, 
        help_text=_("Timestamp when this specific application was submitted")
    )
    attempt_number_monthly = models.PositiveIntegerField(
        help_text=_("Which attempt this was in the submission month (at the time of submission)")
    )
    creator_name_submitted = models.CharField(max_length=100)
    creator_unique_name_submitted = models.CharField(max_length=50)
    cnic_front_submitted = models.ImageField(
        upload_to=creator_cnic_path, 
        blank=True, 
        null=True, 
        help_text=_("CNIC Front submitted for this attempt")
    )
    cnic_back_submitted = models.ImageField(
        upload_to=creator_cnic_path, 
        blank=True, 
        null=True, 
        help_text=_("CNIC Back submitted for this attempt")
    )
    terms_accepted_at_submission = models.DateTimeField(
        help_text=_("Timestamp when terms were accepted for this submission")
    )
    status = models.CharField(
        max_length=10, 
        choices=STATUS_CHOICES, 
        default='submitted', 
        db_index=True
    )
    processed_at = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text=_("Timestamp when the application was approved or rejected")
    )
    processed_by = models.ForeignKey(
        Admin, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='processed_creator_applications', 
        help_text=_("Admin who approved or rejected this specific application.")
    )
    rejection_reason = models.TextField(
        blank=True, 
        null=True, 
        help_text=_("Reason provided if this specific application was rejected")
    )
    
    class Meta:
        db_table = "CREATOR_APPLICATION_LOGS"
        ordering = ['creator', '-application_date']
        verbose_name = _("Creator Application Log")
        verbose_name_plural = _("Creator Application Logs")
    
    def __str__(self):
        return f"Log for {self.creator.user.username} ({self.application_date.strftime('%Y-%m-%d %H:%M')}) - Status: {self.get_status_display()}"

# ============================================================================
# WITHDRAWAL SYSTEM MODELS
# ============================================================================

class WithdrawalAccount(models.Model):
    """
    Model for creator withdrawal account information.
    
    Supports multiple payment methods including banks and mobile wallets.
    """
    
    ACCOUNT_TYPE_CHOICES = (
        ('bank', 'Bank Account'),
        ('jazzcash', 'JazzCash'),
        ('easypaisa', 'Easypaisa'),
        ('nayapay', 'Nayapay'),
        ('upaisa', 'Upaisa')
    )
    
    # Validators for different account types
    iban_validator = RegexValidator(
        regex=r'^PK\d{2}[A-Z]{4}\d{16}$', 
        message='Enter a valid Pakistani IBAN (e.g., PK12ABCD0123456789012345).', 
        code='invalid_iban'
    )
    mobile_account_validator = RegexValidator(
        regex=r'^03\d{9}$', 
        message='Enter a valid 11-digit mobile account number (e.g., 03xxxxxxxxx).', 
        code='invalid_mobile_account'
    )
    
    account_id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    creator = models.ForeignKey(
        Creator, 
        on_delete=models.CASCADE, 
        related_name='withdrawal_accounts'
    )
    account_type = models.CharField(
        max_length=20, 
        choices=ACCOUNT_TYPE_CHOICES, 
        blank=False, 
        null=False
    )
    account_title = models.CharField(
        max_length=100, 
        blank=False, 
        null=False, 
        help_text=_("Full name registered with the account.")
    )
    account_identifier = models.CharField(
        max_length=34, 
        blank=False, 
        null=False, 
        help_text=_("Account Number (JazzCash/Easypaisa/Nayapay/Upaisa) or IBAN (Bank Account).")
    )
    bank_name = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        help_text=_("Required only if Account Type is 'Bank Account'.")
    )
    is_primary = models.BooleanField(
        default=False, 
        help_text=_("Mark one account as primary for withdrawals.")
    )
    added_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text=_("Timestamp when this account was last used for a withdrawal.")
    )
    
    class Meta:
        db_table = "WITHDRAWAL_ACCOUNTS"
        ordering = ['creator', '-added_at']
        constraints = [
            models.UniqueConstraint(
                fields=['creator'], 
                condition=models.Q(is_primary=True), 
                name='unique_primary_withdrawal_account_per_creator'
            )
        ]
        verbose_name = _("Withdrawal Account")
        verbose_name_plural = _("Withdrawal Accounts")
    
    def __str__(self):
        identifier_display = self.account_identifier[-4:] if len(self.account_identifier) >= 4 else self.account_identifier
        primary_marker = " (Primary)" if self.is_primary else ""
        return f"{self.creator.creator_name} - {self.get_account_type_display()}: ...{identifier_display}{primary_marker}"
    
    def clean(self):
        """Validate account information based on type."""
        super().clean()
        if self.account_type == 'bank':
            if not self.bank_name: 
                raise ValidationError({'bank_name': _("Bank name is required for bank accounts.")})
            try: 
                self.iban_validator(self.account_identifier)
            except ValidationError as e: 
                raise ValidationError({'account_identifier': e.messages})
        elif self.account_type in ['jazzcash', 'easypaisa', 'nayapay', 'upaisa']:
            self.bank_name = None
            try: 
                self.mobile_account_validator(self.account_identifier)
            except ValidationError as e: 
                raise ValidationError({'account_identifier': e.messages})
        else:
            self.bank_name = None
    
    def save(self, *args, **kwargs):
        """Ensure only one primary account per creator."""
        self.full_clean()
        if self.is_primary:
            WithdrawalAccount.objects.filter(creator=self.creator, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)

class WithdrawalRequest(models.Model):
    """
    Model for creator withdrawal requests.
    
    Handles the complete withdrawal workflow from request to completion.
    """
    
    STATUS_CHOICES = (
        ('PENDING', 'Pending Approval'), 
        ('PROCESSING', 'Processing Payment'), 
        ('COMPLETED', 'Payment Completed'), 
        ('REJECTED', 'Rejected by Admin'), 
        ('FAILED', 'Payment Failed')
    )
    
    id = models.AutoField(primary_key=True)
    old_request_id = models.CharField(
        max_length=255, 
        null=True, 
        blank=True, 
        help_text=_("Legacy request ID, if applicable.")
    )
    creator = models.ForeignKey(
        Creator, 
        on_delete=models.CASCADE, 
        related_name='withdrawal_requests'
    )
    amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))], 
        help_text=_("Amount requested for withdrawal in PKR")
    )
    withdrawal_account = models.ForeignKey(
        WithdrawalAccount, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=False, 
        related_name='withdrawal_requests', 
        help_text=_("The account selected for this withdrawal request.")
    )
    status = models.CharField(
        max_length=25, 
        choices=STATUS_CHOICES, 
        default='PENDING', 
        db_index=True
    )
    request_date = models.DateTimeField(auto_now_add=True)
    processed_date = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text=_("Timestamp when request was Approved or Rejected by admin")
    )
    admin_notes = models.TextField(
        blank=True, 
        null=True, 
        help_text=_("Reason for rejection, or other admin notes. Visible to creator.")
    )
    processed_by = models.ForeignKey(
        Admin, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='processed_withdrawals', 
        help_text=_("Admin who last updated the status (approved/rejected/marked processing)")
    )
    payment_slip = models.ImageField(
        upload_to=withdrawal_payment_slip_path, 
        blank=True, 
        null=True, 
        help_text=_("Payment slip uploaded by admin upon approval.")
    )
    payment_reference = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        help_text=_("Payment transaction reference, if any.")
    )

    @property
    def display_request_id(self): 
        """Generate user-friendly request ID."""
        return f"REQ-{self.id + 10000}"
    
    class Meta:
        db_table = 'WITHDRAWAL_REQUESTS'
        ordering = ['-request_date']
        verbose_name = _("Withdrawal Request")
        verbose_name_plural = _("Withdrawal Requests")
    
    def __str__(self):
        account_info = f"to ...{self.withdrawal_account.account_identifier[-4:]}" if self.withdrawal_account and len(self.withdrawal_account.account_identifier) >= 4 else (f"to {self.withdrawal_account.get_account_type_display()}" if self.withdrawal_account else "to [Deleted Account]")
        return f"Withdrawal {self.display_request_id} by {self.creator.creator_name} for PKR {self.amount} {account_info} ({self.get_status_display()})"

    def mark_as_processing_by_admin(self, admin_user, notes=""):
        """Mark withdrawal request as processing."""
        if self.status == 'PENDING':
            self.status = 'PROCESSING'
            self.processed_by = admin_user
            timestamp_note = f"Marked as 'Processing' by {admin_user.username} on {timezone.now().strftime('%Y-%m-%d %H:%M')}."
            full_note = f"{timestamp_note} {notes}".strip()
            self.admin_notes = f"{full_note}\n{self.admin_notes}" if self.admin_notes else full_note
            try:
                self.save(update_fields=['status', 'admin_notes', 'processed_by'])
                logger.info(f"Withdrawal request {self.display_request_id} for {self.creator.creator_name} marked as PROCESSING by admin {admin_user.username}.")
            except Exception as e:
                logger.error(f"Error marking request {self.display_request_id} as PROCESSING: {e}", exc_info=True)
                raise
        else:
            logger.warning(f"Attempt to mark non-PENDING request {self.display_request_id} as PROCESSING. Current status: {self.status}")
            raise ValueError(f"Request must be 'Pending' to be marked as 'Processing'. Current status: {self.get_status_display()}")

    def complete_payment_by_admin(self, admin_user, payment_slip_file=None, reference="", notes=""):
        """Complete withdrawal payment."""
        if self.status == 'PROCESSING':
            self.status = 'COMPLETED'
            self.processed_date = timezone.now()
            self.processed_by = admin_user
            self.payment_reference = reference
            if payment_slip_file:
                self.payment_slip.save(payment_slip_file.name, payment_slip_file, save=False)

            timestamp_note = f"Payment Completed by {admin_user.username} on {self.processed_date.strftime('%Y-%m-%d %H:%M')}."
            if reference: timestamp_note += f" Reference: {reference}."
            if self.payment_slip and self.payment_slip.name: timestamp_note += " Payment slip uploaded."
            full_note = f"{timestamp_note} {notes}".strip()
            self.admin_notes = f"{full_note}\n{self.admin_notes}" if self.admin_notes else full_note

            update_fields_list = ['status', 'processed_date', 'admin_notes', 'processed_by', 'payment_reference']
            if payment_slip_file:
                update_fields_list.append('payment_slip')

            try:
                with transaction.atomic():
                    self.save(update_fields=update_fields_list)
                    if self.withdrawal_account:
                        self.withdrawal_account.last_used_at = self.processed_date
                        self.withdrawal_account.save(update_fields=['last_used_at'])
                logger.info(f"Withdrawal request {self.display_request_id} for {self.creator.creator_name} marked as COMPLETED by admin {admin_user.username}.")
            except Exception as e:
                logger.error(f"Error completing request {self.display_request_id}: {e}", exc_info=True)
                raise
        else:
            logger.warning(f"Attempt to mark non-PROCESSING request {self.display_request_id} as COMPLETED. Current status: {self.status}")
            raise ValueError(f"Request must be 'Processing' to be marked as 'Completed'. Current status: {self.get_status_display()}")

    def reject_by_admin(self, admin_user, reason="No reason provided."):
        """Reject withdrawal request and return funds."""
        if self.status in ['PENDING', 'PROCESSING']:
            original_amount = self.amount
            status_before_change = self.get_status_display()
            self.status = 'REJECTED'
            self.processed_by = admin_user
            self.processed_date = timezone.now()
            timestamp_note = f"Rejected by Admin {admin_user.username} on {self.processed_date.strftime('%Y-%m-%d %H:%M')}."
            self.admin_notes = f"{timestamp_note} Reason: {reason}".strip()
            try:
                with transaction.atomic():
                    self.save(update_fields=['status', 'admin_notes', 'processed_date', 'processed_by'])
                    creator = self.creator
                    creator.available_balance = F('available_balance') + original_amount
                    creator.save(update_fields=['available_balance'])
                    logger.info(f"Returned PKR {original_amount} to creator {creator.creator_name}'s available balance after admin rejection of withdrawal {self.display_request_id} (Status was: {status_before_change}).")
            except Exception as e:
                logger.error(f"ERROR: Failed to save admin rejection or return amount for withdrawal {self.display_request_id}: {e}", exc_info=True)
                raise
        else:
            logger.warning(f"Attempt to REJECT request {self.display_request_id} with unsuitable status: {self.status}")
            raise ValueError(f"Request cannot be rejected. Current status: {self.get_status_display()}.")

    def fail_payment_by_admin(self, admin_user, reason="Payment processing failed."):
        """Mark payment as failed and return funds."""
        if self.status == 'PROCESSING':
            original_amount = self.amount
            self.status = 'FAILED'
            self.processed_by = admin_user
            self.processed_date = timezone.now()
            timestamp_note = f"Payment Failed as reported by Admin {admin_user.username} on {self.processed_date.strftime('%Y-%m-%d %H:%M')}."
            self.admin_notes = f"{timestamp_note} Reason: {reason}".strip()
            try:
                with transaction.atomic():
                    self.save(update_fields=['status', 'admin_notes', 'processed_date', 'processed_by'])
                    creator = self.creator
                    creator.available_balance = F('available_balance') + original_amount
                    creator.save(update_fields=['available_balance'])
                    logger.info(f"Returned PKR {original_amount} to creator {creator.creator_name}'s available balance after withdrawal {self.display_request_id} payment FAILED.")
            except Exception as e:
                logger.error(f"ERROR: Failed to mark as FAILED or return amount for withdrawal {self.display_request_id}: {e}", exc_info=True)
                raise
        else:
            logger.warning(f"Attempt to mark request {self.display_request_id} as FAILED from unsuitable status: {self.status}")
            raise ValueError(f"Request must be 'Processing' to be marked as 'Failed'. Current status: {self.get_status_display()}.")

# ============================================================================
# AUDIOBOOK AND CONTENT MODELS
# ============================================================================

class Audiobook(models.Model):
    """
    Model for audiobooks with moderation and publishing workflow.
    
    Supports both creator uploads and external content with comprehensive
    status tracking and moderation capabilities.
    """
    
    class ModerationStatusChoices(models.TextChoices):
        """Internal moderation status choices."""
        APPROVED = 'approved', _('Approved')
        PENDING_REVIEW = 'pending_review', _('Pending Review')
        NEEDS_REVIEW = 'needs_review', _('Needs Manual Review')
        REJECTED = 'rejected', _('Rejected')

    STATUS_CHOICES = (
        ('PUBLISHED', 'Published'),
        ('INACTIVE', 'Inactive'),
        ('UNDER_REVIEW', 'Under Review'),
        ('REJECTED', 'Rejected by Admin'),
        ('PAUSED_BY_ADMIN', 'Paused by Admin'),
        ('TAKEDOWN', 'Takedown by Admin') 
    )
    
    SOURCE_CHOICES = (
        ('creator', 'Creator Upload'),
        ('librivox', 'LibriVox'),
        ('archive', 'Archive.org'),
    )

    # ============================================================================
    # BASIC AUDIOBOOK INFORMATION
    # ============================================================================
    
    audiobook_id = models.AutoField(primary_key=True)
    title = models.CharField(
        max_length=255,
        help_text=_("Title of the audiobook")
    )
    author = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text=_("Author of the original work")
    )
    narrator = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text=_("Narrator of the audiobook")
    )
    language = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text=_("Primary language of the audiobook")
    )
    duration = models.DurationField(
        blank=True, 
        null=True, 
        help_text=_("Total duration of the audiobook. Calculated from chapters if possible.")
    )
    description = models.TextField(
        blank=False, 
        null=True, 
        help_text=_("Detailed description of the audiobook.")
    )
    publish_date = models.DateTimeField(
        default=timezone.now, 
        help_text=_("Original publication date or date added to platform.")
    )
    genre = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text=_("Genre classification")
    )
    
    # ============================================================================
    # RELATIONSHIPS AND METADATA
    # ============================================================================
    
    creator = models.ForeignKey(
        'Creator', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="audiobooks",
        help_text=_("Creator who uploaded this audiobook")
    )
    slug = models.SlugField(
        max_length=255, 
        unique=True, 
        blank=True, 
        help_text=_("URL-friendly identifier, auto-generated from title.")
    )
    cover_image = models.ImageField(
        upload_to='audiobook_covers/', 
        blank=True, 
        null=True,
        help_text=_("Cover image for the audiobook")
    )
    
    # ============================================================================
    # STATUS AND MODERATION
    # ============================================================================
    
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='INACTIVE', 
        db_index=True, 
        help_text=_("Public visibility of the audiobook (e.g., Published, Inactive).")
    )
    moderation_status = models.CharField(
        max_length=20, 
        choices=ModerationStatusChoices.choices, 
        default=ModerationStatusChoices.PENDING_REVIEW, 
        db_index=True, 
        help_text=_("Internal status for content moderation.")
    )
    moderation_notes = models.TextField(
        blank=True, 
        null=True, 
        help_text=_("Internal notes from the moderation process (e.g., why it was flagged or rejected).")
    )
    last_moderated_at = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text=_("Timestamp of the last moderation action.")
    )
    
    # ============================================================================
    # SOURCE AND CONTENT TYPE
    # ============================================================================
    
    source = models.CharField(
        max_length=10, 
        choices=SOURCE_CHOICES, 
        default='creator', 
        db_index=True, 
        help_text=_("Source of the audiobook (Creator, LibriVox, Archive.org)")
    )
    is_creator_book = models.BooleanField(
        default=True, 
        help_text=_("True if uploaded by a platform creator, False if a placeholder for an external book (e.g., for reviews only).")
    )
    
    # ============================================================================
    # ANALYTICS AND METRICS
    # ============================================================================
    
    total_views = models.PositiveIntegerField(
        default=0, 
        help_text=_("Total number of times the audiobook detail page has been viewed.")
    )
    total_sales = models.PositiveIntegerField(
        default=0, 
        help_text=_("Number of times this audiobook has been sold (for paid books).")
    )
    total_revenue_generated = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0.00, 
        help_text=_("Total gross revenue generated by this audiobook before platform fees.")
    )
    
    # ============================================================================
    # PRICING AND MONETIZATION
    # ============================================================================
    
    is_paid = models.BooleanField(
        default=False, 
        help_text=_("Is this audiobook paid or free?")
    )
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'), 
        validators=[MinValueValidator(Decimal('0.00'))], 
        help_text=_("Price in PKR if the audiobook is paid (set to 0.00 if free).")
    )
    
    # ============================================================================
    # TIMESTAMPS
    # ============================================================================
    
    created_at = models.DateTimeField(
        default=timezone.now, 
        editable=False, 
        help_text=_("Timestamp when the audiobook record was created.")
    )
    updated_at = models.DateTimeField(
        auto_now=True, 
        help_text=_("Timestamp when the audiobook record was last updated.")
    )
    
    # ============================================================================
    # TAKEDOWN MANAGEMENT
    # ============================================================================
    
    takedown_by = models.ForeignKey(
        Admin, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='takedown_audiobooks',
        help_text=_("Admin who initiated the takedown")
    )
    takedown_at = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text=_("Timestamp when the audiobook was taken down.")
    )
    takedown_reason = models.TextField(
        blank=True, 
        null=True, 
        help_text=_("Reason for the takedown, provided by the admin.")
    )

    class Meta:
        db_table = "AUDIOBOOKS"
        ordering = ['-created_at']
        verbose_name = _("Audiobook")
        verbose_name_plural = _("Audiobooks")

    def save(self, *args, **kwargs):
        """Auto-generate slug and handle status transitions."""
        # Generate unique slug if not set
        if not self.slug or (kwargs.get('update_fields') and 'title' in kwargs['update_fields'] and 'slug' not in kwargs['update_fields']):
            base_slug = slugify(self.title) or "audiobook"
            slug = base_slug
            counter = 1
            pk_to_exclude = self.pk if self.pk is not None else uuid.uuid4()
            while Audiobook.objects.filter(slug=slug).exclude(pk=pk_to_exclude).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        
        # Ensure free audiobooks have zero price
        if not self.is_paid:
            self.price = Decimal('0.00')
        
        # Set creator book flag based on creator presence
        if self.creator:
            self.is_creator_book = True
            self.source = 'creator'
        elif self.source != 'creator':
            self.is_creator_book = False
            
        # Handle status transitions based on moderation
        if self.moderation_status == self.ModerationStatusChoices.APPROVED and self.status in ['INACTIVE', 'UNDER_REVIEW']:
            self.status = 'PUBLISHED'
        elif self.moderation_status == self.ModerationStatusChoices.REJECTED:
            self.status = 'REJECTED'

        super().save(*args, **kwargs)

    def __str__(self):
        price_info = f"(PKR {self.price})" if self.is_paid else "(Free)"
        mod_status_display = self.get_moderation_status_display()
        return f"{self.title} [Public: {self.get_status_display()} | Mod: {mod_status_display}] {price_info}"

    def clean(self):
        """Validate pricing consistency."""
        super().clean()
        if not self.is_paid and self.price != Decimal('0.00'):
            raise ValidationError({'price': _('Price must be 0.00 for free audiobooks.')})
        if self.is_paid and self.price <= Decimal('0.00'):
            raise ValidationError({'price': _('Price must be greater than 0.00 for paid audiobooks.')})

    @property
    def duration_in_seconds(self):
        """Get duration in seconds."""
        if self.duration:
            return int(self.duration.total_seconds())
        return 0

    @property
    def average_rating(self):
        """Calculate average rating from reviews."""
        avg = self.reviews.filter(audiobook=self).aggregate(Avg('rating'))['rating__avg']
        return round(avg, 1) if avg is not None else None

    def update_sales_analytics(self, amount_paid):
        """Update sales metrics after a purchase."""
        if self.status == 'PUBLISHED' and self.is_creator_book:
            Audiobook.objects.filter(pk=self.pk).update(
                total_sales=F('total_sales') + 1, 
                total_revenue_generated=F('total_revenue_generated') + Decimal(amount_paid)
            )
            self.refresh_from_db(fields=['total_sales', 'total_revenue_generated'])
        else:
            logger.warning(f"Sale not recorded for analytics for '{self.title}'. Status: {self.status}, Is Creator Book: {self.is_creator_book}")

    @property
    def first_chapter_audio_url(self):
        """Get URL for the first chapter's audio."""
        first_chapter = self.chapters.order_by('chapter_order').first()
        if first_chapter and first_chapter.audio_file and first_chapter.audio_file.name:
            try:
                if default_storage.exists(first_chapter.audio_file.name):
                    return first_chapter.audio_file.url
                else:
                    logger.warning(f"Audio file {first_chapter.audio_file.name} for chapter {first_chapter.chapter_id} of audiobook {self.title} not found in storage.")
            except Exception as e:
                logger.error(f"Error checking existence or getting URL for {first_chapter.audio_file.name}: {e}")
        return None

    @property
    def first_chapter_title(self):
        """Get title of the first chapter."""
        first_chapter = self.chapters.order_by('chapter_order').first()
        if first_chapter:
            return first_chapter.chapter_name
        return None

class Chapter(models.Model):
    """
    Model for individual audiobook chapters.
    
    Supports both uploaded audio files and external URLs with
    comprehensive metadata and moderation capabilities.
    """
    
    class ModerationStatusChoices(models.TextChoices):
        """Internal moderation status choices for chapters."""
        APPROVED = 'approved', _('Approved')
        PENDING_REVIEW = 'pending_review', _('Pending Review')
        NEEDS_REVIEW = 'needs_review', _('Needs Manual Review')
        REJECTED = 'rejected', _('Rejected')

    # ============================================================================
    # BASIC CHAPTER INFORMATION
    # ============================================================================
    
    chapter_id = models.AutoField(primary_key=True)
    audiobook = models.ForeignKey(
        'Audiobook', 
        on_delete=models.CASCADE, 
        related_name="chapters",
        help_text=_("Audiobook this chapter belongs to")
    )
    chapter_name = models.CharField(
        max_length=255,
        help_text=_("Name/title of the chapter")
    )
    chapter_order = models.PositiveIntegerField(
        help_text=_("Order of this chapter within the audiobook")
    )
    
    # ============================================================================
    # AUDIO CONTENT
    # ============================================================================
    
    audio_file = models.FileField(
        upload_to="chapters_audio/", 
        blank=True, 
        null=True,
        help_text=_("Uploaded audio file for this chapter")
    )
    external_audio_url = models.URLField(
        max_length=1024, 
        blank=True, 
        null=True,
        help_text=_("External URL for audio content")
    )
    external_chapter_identifier = models.CharField(
        max_length=255, 
        unique=True, 
        blank=True, 
        null=True,
        help_text=_("Unique identifier for external chapters")
    )
    
    # ============================================================================
    # METADATA AND ANALYTICS
    # ============================================================================
    
    duration_seconds = models.FloatField(
        null=True, 
        blank=True,
        help_text=_("Duration of the chapter in seconds")
    )
    size_bytes = models.PositiveBigIntegerField(
        null=True, 
        blank=True,
        help_text=_("File size in bytes")
    )
    text_content = models.TextField(
        blank=True, 
        null=True,
        help_text=_("Text content of the chapter")
    )
    transcript = models.TextField(
        blank=True, 
        null=True,
        help_text=_("Audio transcript")
    )
    
    # ============================================================================
    # MODERATION
    # ============================================================================
    
    moderation_status = models.CharField(
        max_length=20, 
        choices=ModerationStatusChoices.choices, 
        default=ModerationStatusChoices.PENDING_REVIEW, 
        db_index=True,
        help_text=_("Internal moderation status")
    )
    moderation_notes = models.TextField(
        blank=True, 
        null=True,
        help_text=_("Internal moderation notes")
    )
    
    # ============================================================================
    # TTS (TEXT-TO-SPEECH) SUPPORT
    # ============================================================================
    
    is_tts_generated = models.BooleanField(
        default=False,
        help_text=_("Whether this chapter was generated using TTS")
    )
    tts_voice_id = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text=_("Voice ID used for TTS generation")
    )
    source_document_filename = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text=_("Original document filename if converted from text")
    )
    
    # ============================================================================
    # ADDITIONAL FLAGS
    # ============================================================================
    
    is_preview_eligible = models.BooleanField(
        default=False,
        help_text=_("Whether this chapter can be used for previews")
    )
    
    # ============================================================================
    # TIMESTAMPS
    # ============================================================================
    
    created_at = models.DateTimeField(
        default=timezone.now, 
        editable=False
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "CHAPTERS"
        ordering = ['audiobook', 'chapter_order']
        unique_together = (('audiobook', 'chapter_order'),)
        verbose_name = _("Chapter")
        verbose_name_plural = _("Chapters")

    def __str__(self):
        tts_info = ""
        if self.is_tts_generated and self.tts_voice_id:
            try:
                display_name = self.get_tts_voice_id_display() if hasattr(self, 'get_tts_voice_id_display') else self.tts_voice_id
                if display_name and str(display_name).lower() != 'none': 
                    tts_info = f" (TTS: {display_name})"
                elif self.tts_voice_id: 
                    tts_info = f" (TTS: {self.tts_voice_id})"
            except Exception:
                if self.tts_voice_id: 
                    tts_info = f" (TTS: {self.tts_voice_id} - Error displaying name)"
        
        mod_status_display = self.get_moderation_status_display()
        return f"{self.chapter_order}: {self.chapter_name} ({self.audiobook.title}) [Mod: {mod_status_display}]{tts_info}"

    def save(self, *args, **kwargs):
        """Auto-calculate duration and file size."""
        is_new_file = False
        if not self.pk:
            is_new_file = True
        else:
            try:
                old = Chapter.objects.get(pk=self.pk)
                if old.audio_file != self.audio_file:
                    is_new_file = True
            except Chapter.DoesNotExist:
                is_new_file = True

        if is_new_file and self.audio_file:
            self.size_bytes = self.audio_file.size

        super().save(*args, **kwargs)

        # Calculate duration after saving
        if is_new_file and self.audio_file and self.duration_seconds is None:
            try:
                duration = get_audio_duration(self.audio_file)
                
                if duration is not None:
                    Chapter.objects.filter(pk=self.pk).update(duration_seconds=duration)
                    logger.info(f"Successfully calculated and saved duration ({duration}s) for Chapter {self.pk}")

            except Exception as e:
                logger.error(f"Could not calculate duration for Chapter {self.pk} on second save pass. Error: {e}", exc_info=True)

    @property
    def duration_display(self):
        """Get human-readable duration."""
        if self.duration_seconds is not None:
            try:
                seconds = int(self.duration_seconds)
                if seconds < 0: 
                    return "--:--"
                minutes = seconds // 60
                secs = seconds % 60
                return f"{minutes}:{secs:02d}"
            except (ValueError, TypeError):
                return "--:--"
        return "--:--"

    def get_streaming_url(self):
        """Get streaming URL for this chapter."""
        if self.external_audio_url:
            return reverse('AudioXApp:stream_audio') + f'?url={quote(self.external_audio_url, safe="")}'
        elif self.audio_file and hasattr(self.audio_file, 'url'):
            try:
                if default_storage.exists(self.audio_file.name):
                    relative_url = self.audio_file.url
                    return reverse('AudioXApp:stream_audio') + f'?url={quote(relative_url, safe="")}'
                else:
                    logger.warning(f"Local audio file missing for chapter {self.pk}: {self.audio_file.name}")
            except Exception as e:
                logger.error(f"Error getting streaming URL for local chapter {self.pk}: {e}")
        return None

    @property
    def frontend_id(self):
        """Get frontend-compatible ID."""
        return str(self.pk)

# ============================================================================
# REVIEW AND RATING MODELS
# ============================================================================

class Review(models.Model):
    """
    Model for user reviews and ratings of audiobooks.
    
    Allows users to rate and comment on audiobooks they've accessed.
    """
    
    review_id = models.AutoField(primary_key=True)
    audiobook = models.ForeignKey(
        Audiobook, 
        on_delete=models.CASCADE, 
        related_name='reviews',
        help_text=_("Audiobook being reviewed")
    )
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='reviews',
        help_text=_("User who wrote the review")
    )
    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)], 
        help_text=_("Rating from 1 to 5 stars.")
    )
    comment = models.TextField(
        blank=True, 
        null=True, 
        help_text=_("User's review comment (optional).")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'REVIEWS'
        ordering = ['-created_at']
        unique_together = (('audiobook', 'user'))
        verbose_name = _("Audiobook Review")
        verbose_name_plural = _("Audiobook Reviews")
    
    def __str__(self): 
        return f"Review by {self.user.username} for {self.audiobook.title} ({self.rating} stars)"

# ============================================================================
# SUBSCRIPTION MODELS
# ============================================================================

class Subscription(models.Model):
    """
    Model for user premium subscriptions.
    
    Handles subscription lifecycle, billing, and status management.
    """
    
    PLAN_CHOICES = (
        ('monthly', 'Monthly Premium'),
        ('annual', 'Annual Premium'),
    )
    
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('canceled', 'Canceled'),
        ('expired', 'Expired'),
        ('pending', 'Pending Payment'),
        ('failed', 'Payment Failed'),
        ('past_due', 'Past Due')
    )
    
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='subscription'
    )
    plan = models.CharField(
        max_length=20, 
        choices=PLAN_CHOICES,
        help_text=_("Subscription plan type")
    )
    start_date = models.DateTimeField(
        help_text=_("When the subscription started")
    )
    end_date = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text=_("End of the current billing cycle. For 'canceled' status, this is when access ends.")
    )
    status = models.CharField(
        max_length=10, 
        choices=STATUS_CHOICES, 
        default='active', 
        db_index=True
    )
    stripe_subscription_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        db_index=True,
        help_text=_("Stripe subscription ID")
    )
    stripe_customer_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        db_index=True,
        help_text=_("Stripe customer ID")
    )
    stripe_payment_method_brand = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        help_text=_("e.g., visa, mastercard")
    )
    stripe_payment_method_last4 = models.CharField(
        max_length=4, 
        blank=True, 
        null=True, 
        help_text=_("Last 4 digits of the card")
    )
    
    class Meta: 
        db_table = 'SUBSCRIPTIONS'
        verbose_name = _("Subscription")
        verbose_name_plural = _("Subscriptions")
    
    def __str__(self): 
        return f"{self.user.username} - {self.get_plan_display()} ({self.get_status_display()})"
    
    def is_active(self): 
        """Check if subscription is currently active."""
        return self.status == 'active' and (self.end_date is None or self.end_date >= timezone.now())

    def cancel(self):
        """Cancel the subscription."""
        if self.status == 'active': 
            self.status = 'canceled'
            self.save(update_fields=['status'])

    def update_status(self):
        """Update subscription status based on end date."""
        now = timezone.now()
        if self.status in ['active', 'canceled'] and self.end_date and self.end_date < now:
            self.status = 'expired'
            self.save(update_fields=['status'])
            if self.user.subscription_type == 'PR': 
                self.user.subscription_type = 'FR'
                self.user.save(update_fields=['subscription_type'])

    @property
    def remaining_days(self):
        """Get remaining days in subscription."""
        if self.status in ['active', 'canceled'] and self.end_date:
            remaining = self.end_date - timezone.now()
            return max(0, remaining.days)
        return 0

# ============================================================================
# ANALYTICS AND TRACKING MODELS
# ============================================================================

class AudiobookViewLog(models.Model):
    """
    Model for tracking audiobook page views.
    
    Used for analytics and recommendation systems.
    """
    
    view_id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    audiobook = models.ForeignKey(
        Audiobook, 
        on_delete=models.CASCADE, 
        related_name='view_logs'
    )
    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='audiobook_views'
    )
    viewed_at = models.DateTimeField(
        default=timezone.now, 
        db_index=True
    )
    
    class Meta:
        db_table = 'AUDIOBOOK_VIEW_LOGS'
        ordering = ['-viewed_at']
        verbose_name = _("Audiobook View Log")
        verbose_name_plural = _("Audiobook View Logs")
        indexes = [
            models.Index(fields=['audiobook', 'viewed_at']), 
            models.Index(fields=['user', 'audiobook', 'viewed_at']),
        ]
    
    def __str__(self):
        user_str = self.user.username if self.user else "Anonymous"
        return f"View of '{self.audiobook.title}' by {user_str} at {self.viewed_at.strftime('%Y-%m-%d %H:%M')}"

class ListeningHistory(models.Model):
    """
    Model for tracking user listening progress.
    
    Stores position and completion status for each chapter.
    """
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='listening_history'
    )
    chapter = models.ForeignKey(
        Chapter, 
        on_delete=models.CASCADE, 
        related_name='listening_sessions'
    ) 
    last_position_seconds = models.FloatField(
        default=0, 
        help_text=_("The last position in seconds the user was at in this specific chapter.")
    )
    is_completed = models.BooleanField(
        default=False, 
        help_text=_("True if the user has finished this chapter.")
    )
    last_listened_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'LISTENING_HISTORY_CHAPTER'
        unique_together = ('user', 'chapter')
        ordering = ['-last_listened_at']
        verbose_name = _("Chapter Listening History")
        verbose_name_plural = _("Chapter Listening Histories")

    def __str__(self):
        status = "Completed" if self.is_completed else f"at {self.last_position_seconds:.1f}s"
        return f"History for {self.user.username} on '{self.chapter.chapter_name}': {status}"

# ============================================================================
# USER LIBRARY MODELS
# ============================================================================

class UserLibraryItem(models.Model):
    """
    Model for user's saved audiobooks library.
    
    Allows users to save audiobooks for later listening.
    """
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='library_items'
    )
    audiobook = models.ForeignKey(
        Audiobook, 
        on_delete=models.CASCADE, 
        related_name='saved_by_users'
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'USER_LIBRARY_ITEMS'
        unique_together = ('user', 'audiobook')
        ordering = ['-added_at']
        verbose_name = _("User Library Item")
        verbose_name_plural = _("User Library Items")

    def __str__(self):
        return f"'{self.audiobook.title}' in {self.user.username}'s library"

class UserDownloadedAudiobook(models.Model):
    """
    Model for tracking downloaded audiobooks for offline listening.
    
    Manages download permissions and expiry.
    """
    
    download_id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='downloaded_audiobooks', 
        verbose_name=_("User")
    )
    audiobook = models.ForeignKey(
        Audiobook, 
        on_delete=models.CASCADE, 
        related_name='user_downloads', 
        verbose_name=_("Audiobook")
    )
    download_date = models.DateTimeField(
        default=timezone.now, 
        verbose_name=_("Download Date")
    )
    expiry_date = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text=_("Optional: When the download access expires (e.g., for subscription-based downloads)."), 
        verbose_name=_("Expiry Date")
    )
    is_active = models.BooleanField(
        default=True, 
        help_text=_("Is this download currently active and usable offline? Set to False if expired or revoked."), 
        verbose_name=_("Is Active")
    )
    last_verified_at = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text=_("Timestamp when the client app last verified the download's validity with the server."), 
        verbose_name=_("Last Verified At")
    )

    class Meta:
        db_table = 'USER_DOWNLOADED_AUDIOBOOKS'
        ordering = ['-download_date']
        unique_together = ('user', 'audiobook')
        verbose_name = _("User Downloaded Audiobook")
        verbose_name_plural = _("User Downloaded Audiobooks")

    def __str__(self):
        return f"{self.user.username} downloaded '{self.audiobook.title}' on {self.download_date.strftime('%Y-%m-%d')}"

    @property
    def is_expired(self):
        """Check if download has expired."""
        if self.expiry_date and self.expiry_date < timezone.now():
            return True
        return False

    def deactivate_if_expired(self):
        """Deactivate download if expired."""
        if self.is_expired and self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])
            logger.info(f"Deactivated expired download (ID: {self.download_id}) for user {self.user.username} - audiobook '{self.audiobook.title}'.")
            return True
        return False

    def refresh_verification(self):
        """Update last verification timestamp."""
        self.last_verified_at = timezone.now()
        self.save(update_fields=['last_verified_at'])
        logger.info(f"Refreshed verification for download (ID: {self.download_id}) for user {self.user.username} - audiobook '{self.audiobook.title}'.")

# ============================================================================
# SUPPORT SYSTEM MODELS
# ============================================================================

class TicketCategory(models.Model):
    """
    Model for support ticket categories.
    
    Organizes support requests by type and creator-specific issues.
    """
    
    name = models.CharField(
        max_length=100, 
        unique=True,
        help_text=_("Category name")
    )
    description = models.TextField(
        blank=True, 
        null=True,
        help_text=_("Category description")
    )
    is_creator_specific = models.BooleanField(
        default=False, 
        help_text=_("Is this category primarily for creators?")
    )
    
    class Meta:
        db_table = "TICKET_CATEGORIES"
        verbose_name = _("Ticket Category")
        verbose_name_plural = _("Ticket Categories")
        ordering = ['name']
    
    def __str__(self): 
        return self.name

class Ticket(models.Model):
    """
    Model for support tickets.
    
    Handles user support requests with status tracking and admin assignment.
    """
    
    class StatusChoices(models.TextChoices):
        OPEN = 'OPEN', _('Open')
        PROCESSING = 'PROCESSING', _('Processing')
        AWAITING_USER = 'AWAITING_USER', _('Awaiting User Response')
        RESOLVED = 'RESOLVED', _('Resolved')
        CLOSED = 'CLOSED', _('Closed')
        REOPENED = 'REOPENED', _('Reopened')
    
    id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    ticket_display_id = models.CharField(
        max_length=20, 
        unique=True, 
        editable=False, 
        help_text=_("User-friendly ticket ID, e.g., AXT-1001")
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='support_tickets', 
        verbose_name=_("User")
    )
    creator_profile = models.ForeignKey(
        'Creator', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='creator_support_tickets', 
        verbose_name=_("Creator Profile"), 
        help_text=_("Associated creator profile, if the user is a creator and the issue is creator-specific.")
    )
    category = models.ForeignKey(
        TicketCategory, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=False, 
        related_name='tickets', 
        verbose_name=_("Category")
    )
    subject = models.CharField(
        max_length=255, 
        verbose_name=_("Subject")
    )
    description = models.TextField(
        verbose_name=_("Description")
    )
    status = models.CharField(
        max_length=20, 
        choices=StatusChoices.choices, 
        default=StatusChoices.OPEN, 
        verbose_name=_("Status")
    )
    created_at = models.DateTimeField(
        auto_now_add=True, 
        verbose_name=_("Created At")
    )
    updated_at = models.DateTimeField(
        auto_now=True, 
        verbose_name=_("Last Updated At")
    )
    resolved_at = models.DateTimeField(
        null=True, 
        blank=True, 
        verbose_name=_("Resolved At"), 
        help_text=_("Timestamp when the ticket was first marked as resolved.")
    )
    closed_at = models.DateTimeField(
        null=True, 
        blank=True, 
        verbose_name=_("Closed At"), 
        help_text=_("Timestamp when the ticket was finally closed (e.g., after a resolved period).")
    )
    assigned_admin_identifier = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        verbose_name=_("Assigned Admin Identifier"), 
        help_text=_("Identifier (e.g., username or ID) of the admin handling the ticket from your custom Admin system.")
    )
    
    class Meta:
        db_table = "SUPPORT_TICKETS"
        ordering = ['-created_at']
        verbose_name = _("Support Ticket")
        verbose_name_plural = _("Support Tickets")
    
    def __str__(self): 
        return f"{self.ticket_display_id} - {self.subject} ({self.user.username})"
    
    def save(self, *args, **kwargs):
        """Auto-generate ticket display ID and link creator profile."""
        if not self.ticket_display_id:
            last_ticket = Ticket.objects.all().order_by('ticket_display_id').last()
            if last_ticket and last_ticket.ticket_display_id.startswith('AXT-'):
                try:
                    last_num = int(last_ticket.ticket_display_id.split('-')[1])
                    new_id_num = last_num + 1
                except (IndexError, ValueError):
                    new_id_num = 1001
            else:
                new_id_num = 1001
            self.ticket_display_id = f"AXT-{new_id_num}"

        # Auto-link creator profile for creator-specific categories
        if self.user and hasattr(self.user, 'is_creator') and self.user.is_creator:
            if self.category and self.category.is_creator_specific:
                try:
                    if hasattr(self.user, 'creator_profile') and self.user.creator_profile:
                        self.creator_profile = self.user.creator_profile
                    else:
                        self.creator_profile = None
                        logger.info(f"User {self.user.pk} is_creator=True but creator_profile is None for ticket {getattr(self, 'id', 'new')}.")
                except Creator.DoesNotExist:
                    self.creator_profile = None
                    logger.warning(f"Creator profile not found for user {self.user.pk} on ticket {getattr(self, 'id', 'new')}.")
                except Exception as e:
                    self.creator_profile = None
                    logger.warning(f"Could not link creator_profile for user {self.user.pk} on ticket {getattr(self, 'id', 'new')}: {e}")
            elif self.category and not self.category.is_creator_specific:
                self.creator_profile = None
        else:
            self.creator_profile = None
        super().save(*args, **kwargs)

class TicketMessage(models.Model):
    """
    Model for support ticket messages/replies.
    
    Handles conversation between users and support staff.
    """
    
    id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    ticket = models.ForeignKey(
        Ticket, 
        on_delete=models.CASCADE, 
        related_name='messages', 
        verbose_name=_("Ticket")
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='ticket_messages', 
        verbose_name=_("User")
    )
    message = models.TextField(
        verbose_name=_("Message")
    )
    created_at = models.DateTimeField(
        auto_now_add=True, 
        verbose_name=_("Created At")
    )
    is_admin_reply = models.BooleanField(
        default=False, 
        verbose_name=_("Is Admin Reply"), 
        help_text=_("True if this message is from an admin/support agent.")
    )

    class Meta:
        db_table = "SUPPORT_TICKET_MESSAGES"
        ordering = ['created_at']
        verbose_name = _("Support Ticket Message")
        verbose_name_plural = _("Support Ticket Messages")
    
    def __str__(self):
        sender_name = _("Admin") if self.is_admin_reply else (self.user.username if self.user else _("System"))
        return _("Reply by %(sender)s on ticket %(ticket_id)s at %(timestamp)s") % {
            'sender': sender_name,
            'ticket_id': self.ticket.ticket_display_id if self.ticket else 'N/A',
            'timestamp': self.created_at.strftime('%Y-%m-%d %H:%M')
        }

# ============================================================================
# COMMUNITY FEATURES MODELS
# ============================================================================

class ChatRoom(models.Model):
    """
    Model for community chat rooms.
    
    Enables users to create and participate in topic-based discussions.
    """
    
    class RoomStatusChoices(models.TextChoices):
        ACTIVE = 'active', _('Active')
        CLOSED = 'closed', _('Closed by Owner')

    LANGUAGE_CHOICES = [
        ('EN', _('English')),
        ('UR', _('Urdu')),
        ('PA', _('Punjabi')),
        ('SI', _('Sindhi')),
    ]

    room_id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    name = models.CharField(
        max_length=100, 
        unique=True, 
        help_text=_("Name of the chat room.")
    )
    description = models.TextField(
        blank=False, 
        null=False, 
        help_text=_("Description for the chat room.")
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='owned_chatrooms', 
        help_text=_("The user who created and owns the room.")
    )
    cover_image = models.ImageField(
        upload_to=chatroom_cover_image_path, 
        blank=True, 
        null=True, 
        help_text=_("Optional cover image for the room.")
    )
    language = models.CharField(
        max_length=2, 
        choices=LANGUAGE_CHOICES, 
        default='EN', 
        blank=False, 
        null=False, 
        help_text=_("Primary language of the chat room.")
    )
    status = models.CharField(
        max_length=15, 
        choices=RoomStatusChoices.choices, 
        default=RoomStatusChoices.ACTIVE, 
        db_index=True, 
        help_text=_("The current status of the chat room (Active, Closed, etc.)")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "CHAT_ROOMS"
        ordering = ['-created_at', 'status']
        verbose_name = _("Chat Room")
        verbose_name_plural = _("Chat Rooms")

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    @property
    def member_count(self):
        """Get active member count."""
        return self.room_memberships.filter(status=ChatRoomMember.StatusChoices.ACTIVE).count()

    @property
    def is_open_for_interaction(self):
        """Check if room is open for new messages."""
        return self.status == self.RoomStatusChoices.ACTIVE

class ChatRoomMember(models.Model):
    """
    Model for chat room membership.
    
    Tracks user participation in chat rooms with roles and status.
    """
    
    class RoleChoices(models.TextChoices):
        MEMBER = 'member', _('Member')
        ADMIN = 'admin', _('Admin')

    class StatusChoices(models.TextChoices):
        ACTIVE = 'active', _('Active')
        LEFT = 'left', _('Left Voluntarily')
        ROOM_DISMISSED = 'room_dismissed', _('Room Dismissed')

    id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    room = models.ForeignKey(
        ChatRoom, 
        on_delete=models.CASCADE, 
        related_name='room_memberships'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='chat_room_memberships'
    )
    role = models.CharField(
        max_length=10, 
        choices=RoleChoices.choices, 
        default=RoleChoices.MEMBER
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20, 
        choices=StatusChoices.choices, 
        default=StatusChoices.ACTIVE, 
        db_index=True, 
        help_text=_("Current status of the member in the room.")
    )
    left_at = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text=_("Timestamp when the user left or was removed from the room.")
    )

    class Meta:
        db_table = "CHAT_ROOM_MEMBERS"
        unique_together = ('room', 'user')
        ordering = ['room', 'joined_at']
        verbose_name = _("Chat Room Member")
        verbose_name_plural = _("Chat Room Members")

    def __str__(self):
        return f"{self.user.username} in {self.room.name} as {self.get_role_display()} ({self.get_status_display()})"

class ChatMessage(models.Model):
    """
    Model for chat room messages.
    
    Supports text messages, audiobook recommendations, and system notifications.
    """
    
    class MessageTypeChoices(models.TextChoices):
        TEXT = 'text', _('Text Message')
        AUDIOBOOK_RECOMMENDATION = 'audiobook_recommendation', _('Audiobook Recommendation')
        USER_JOINED = 'user_joined', _('User Joined Notification')
        USER_LEFT = 'user_left', _('User Left Notification')
        ROOM_CREATED = 'room_created', _('Room Created Notification')
        ROOM_RENAMED = 'room_renamed', _('Room Renamed Notification')
        ROOM_CLOSED = 'room_closed', _('Room Closed Notification')

    message_id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    room = models.ForeignKey(
        ChatRoom, 
        on_delete=models.CASCADE, 
        related_name='messages'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='chat_messages', 
        help_text=_("User who sent the message. Null for system messages.")
    )
    message_type = models.CharField(
        max_length=30, 
        choices=MessageTypeChoices.choices, 
        default=MessageTypeChoices.TEXT
    )
    content = models.TextField(
        help_text=_("Content of the message. For recommendations, this might be an optional comment or the system message text.")
    )
    recommended_audiobook = models.ForeignKey(
        'Audiobook', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='chat_recommendations', 
        help_text=_("Link to an audiobook if this message is a recommendation.")
    )
    timestamp = models.DateTimeField(
        auto_now_add=True, 
        db_index=True
    )

    class Meta:
        db_table = "CHAT_MESSAGES"
        ordering = ['timestamp']
        verbose_name = _("Chat Message")
        verbose_name_plural = _("Chat Messages")

    def __str__(self):
        user_display = self.user.username if self.user else "System"
        return f"Msg by {user_display} in {self.room.name} ({self.get_message_type_display()}) at {self.timestamp.strftime('%Y-%m-%d %H:%M')}"

class ChatRoomInvitation(models.Model):
    """
    Model for chat room invitations.
    
    Handles invitation workflow for private or restricted rooms.
    """
    
    class StatusChoices(models.TextChoices):
        PENDING = 'pending', _('Pending')
        ACCEPTED = 'accepted', _('Accepted')
        DECLINED = 'declined', _('Declined')
        EXPIRED = 'expired', _('Expired')

    invitation_id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    room = models.ForeignKey(
        ChatRoom, 
        on_delete=models.CASCADE, 
        related_name='invitations'
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='sent_chat_invitations', 
        help_text=_("User who sent the invitation.")
    )
    invited_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='received_chat_invitations', 
        help_text=_("User who is invited to the room.")
    )
    status = models.CharField(
        max_length=10, 
        choices=StatusChoices.choices, 
        default=StatusChoices.PENDING, 
        db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "CHAT_ROOM_INVITATIONS"
        ordering = ['-created_at']
        verbose_name = _("Chat Room Invitation")
        verbose_name_plural = _("Chat Room Invitations")
        constraints = [
            models.UniqueConstraint(
                fields=['room', 'invited_user'],
                condition=models.Q(status='pending'),
                name='unique_pending_invitation_per_user_per_room'
            )
        ]

    def __str__(self):
        invited_user_display = self.invited_user.username if self.invited_user else "N/A"
        inviter_display = self.invited_by.username if self.invited_by else "N/A"
        return f"Invitation for {invited_user_display} to room '{self.room.name}' by {inviter_display} ({self.get_status_display()})"

# ============================================================================
# CONTENT MODERATION MODELS
# ============================================================================

class ContentReport(models.Model):
    """
    Model for user-submitted content reports.
    
    Allows users to report inappropriate audiobook content.
    """
    
    class ReportReason(models.TextChoices):
        HATE_SPEECH = 'HATE_SPEECH', _('Hate Speech')
        ABUSIVE_CONTENT = 'ABUSIVE_CONTENT', _('Abusive or Harassing Content')
        VIOLENT_CONTENT = 'VIOLENT_CONTENT', _('Violent or Graphic Content')
        COPYRIGHT_INFRINGEMENT = 'COPYRIGHT', _('Copyright Infringement')
        MISINFORMATION = 'MISINFORMATION', _('Misinformation or Spam')
        OTHER = 'OTHER', _('Other Issue')

    report_id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='submitted_reports'
    )
    audiobook = models.ForeignKey(
        Audiobook, 
        on_delete=models.CASCADE, 
        related_name='reports'
    )
    reason = models.CharField(
        max_length=30, 
        choices=ReportReason.choices
    )
    details = models.TextField(
        blank=True, 
        help_text=_("Additional details provided by the user.")
    )
    created_at = models.DateTimeField(
        auto_now_add=True, 
        db_index=True
    )
    is_resolved = models.BooleanField(
        default=False, 
        help_text=_("Has an admin reviewed and resolved this report?")
    )
    resolved_by = models.ForeignKey(
        Admin, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='resolved_content_reports'
    )
    resolved_at = models.DateTimeField(
        null=True, 
        blank=True
    )

    class Meta:
        db_table = "CONTENT_REPORTS"
        ordering = ['-created_at']
        verbose_name = _("Content Report")
        verbose_name_plural = _("Content Reports")
        unique_together = ('reported_by', 'audiobook')

    def __str__(self):
        return f"Report by {self.reported_by.username} for '{self.audiobook.title}' ({self.get_reason_display()})"

class BannedKeyword(models.Model):
    """
    Model for banned keywords in content moderation.
    
    Stores keywords that trigger automatic content flagging.
    """
    
    class LanguageChoices(models.TextChoices):
        ENGLISH = 'en', _('English')
        URDU = 'ur', _('Urdu')
        PUNJABI = 'pa', _('Punjabi')
        SINDHI = 'sd', _('Sindhi')

    keyword = models.CharField(
        max_length=100, 
        unique=True, 
        help_text=_("The word or phrase to be flagged. Case-insensitive.")
    )
    language = models.CharField(
        max_length=5, 
        choices=LanguageChoices.choices, 
        db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(
        Admin, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='added_keywords'
    )

    class Meta:
        db_table = "BANNED_KEYWORDS"
        ordering = ['language', 'keyword']
        verbose_name = _("Banned Keyword")
        verbose_name_plural = _("Banned Keywords")

    def __str__(self):
        return f"{self.keyword} ({self.get_language_display()})"

    def save(self, *args, **kwargs):
        """Normalize keyword for consistent matching."""
        self.keyword = self.keyword.lower().strip()
        super().save(*args, **kwargs)

# Add this new model to your existing models.py

class ChapterUnlock(models.Model):
    """
    Model for tracking individual chapter unlocks via coin purchases.
    
    Allows FREE users to unlock specific chapters of free audiobooks.
    """
    
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='chapter_unlocks',
        help_text=_("User who unlocked the chapter")
    )
    chapter = models.ForeignKey(
        Chapter, 
        on_delete=models.CASCADE, 
        related_name='user_unlocks',
        help_text=_("Chapter that was unlocked")
    )
    coins_spent = models.PositiveIntegerField(
        default=50,
        help_text=_("Number of coins spent to unlock this chapter")
    )
    unlocked_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_("When the chapter was unlocked")
    )
    
    class Meta:
        unique_together = ('user', 'chapter')  # Prevent duplicate unlocks
        db_table = 'CHAPTER_UNLOCKS'
        verbose_name = _("Chapter Unlock")
        verbose_name_plural = _("Chapter Unlocks")
        
    def __str__(self):
        return f"{self.user.username} unlocked '{self.chapter.chapter_name}' for {self.coins_spent} coins"

# ============================================================================
# END OF MODELS
# ============================================================================
