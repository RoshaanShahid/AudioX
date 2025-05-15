# AudioXApp/models.py

from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.utils import timezone # Ensure timezone is imported
from django.utils.translation import gettext_lazy as _
from django.core.validators import validate_email, RegexValidator, MinValueValidator, MaxValueValidator, FileExtensionValidator
from django.contrib.auth.hashers import make_password, check_password
from django.utils.text import slugify
from decimal import Decimal 
import os
import uuid
from django.conf import settings 
from datetime import timedelta 
from django.db.models import Avg, Sum, F, Prefetch, Q # Added Q for conditional unique constraint
from django.db import transaction # Added for atomic transactions

import logging # Added for logging within models if needed
logger = logging.getLogger(__name__)


# Helper functions (creator_cnic_path, creator_profile_pic_path remain the same)
def creator_cnic_path(instance, filename):
    user_id = None
    # Ensure Creator model is defined before being used here or use string reference 'AudioXApp.Creator'
    if isinstance(instance, Creator) and instance.user and instance.user.user_id:
        user_id = instance.user.user_id
    elif isinstance(instance, CreatorApplicationLog) and instance.creator and instance.creator.user_id: # Corrected type
        user_id = instance.creator.user_id 
    if user_id:
        _, extension = os.path.splitext(filename)
        unique_filename = f'{uuid.uuid4()}{extension}'
        path_prefix = 'creator_application_logs' if isinstance(instance, CreatorApplicationLog) else 'creator_verification'
        return f'{path_prefix}/{user_id}/{unique_filename}'
    return f'creator_verification/unknown/{uuid.uuid4()}{os.path.splitext(filename)[1]}'

def creator_profile_pic_path(instance, filename):
    user_id = instance.user.user_id if instance.user else 'unknown'
    _, extension = os.path.splitext(filename)
    unique_filename = f'{uuid.uuid4()}{extension}'
    return f'creator_profile_pics/{user_id}/{unique_filename}'


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        if not extra_fields.get('username'): # Ensure username is provided
            raise ValueError('The Username field must be set')
        if not extra_fields.get('full_name'): # Ensure full_name is provided
            raise ValueError('The Full Name field must be set')
        user = self.model(email=email, **extra_fields)
        user.set_password(password) 
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True) # Superusers should be active by default

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        extra_fields.setdefault('username', email.split('@')[0] + '_super') 
        extra_fields.setdefault('full_name', 'Super User') 
        extra_fields.setdefault('phone_number', extra_fields.get('phone_number', '')) 
        extra_fields.setdefault('bio', extra_fields.get('bio', '')) 

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    user_id = models.BigAutoField(primary_key=True) 
    full_name = models.CharField(max_length=255)
    username = models.CharField(max_length=255, unique=True)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, blank=False, null=False, default='') 
    bio = models.TextField(blank=False, null=False, default='') 
    profile_pic = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    
    SUBSCRIPTION_CHOICES = [
        ('FR', 'Free'),
        ('PR', 'Premium'),
    ]
    subscription_type = models.CharField(max_length=2, choices=SUBSCRIPTION_CHOICES, default='FR')

    coins = models.IntegerField(default=0) 

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False) 
    is_superuser = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True) 

    is_2fa_enabled = models.BooleanField(default=False, verbose_name="2FA Enabled") 

    purchased_audiobooks = models.ManyToManyField(
        'Audiobook', 
        through='AudiobookPurchase',
        related_name='purchased_by_users'
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'full_name'] 

    objects = UserManager()

    class Meta:
        db_table = 'USERS' 

    def __str__(self):
        return self.email

    @property
    def is_creator(self):
        try:
            is_approved_and_not_banned = (
                hasattr(self, 'creator_profile') and 
                self.creator_profile.verification_status == 'approved' and
                not getattr(self.creator_profile, 'is_banned', False) 
            )
            return is_approved_and_not_banned
        except Creator.DoesNotExist: 
            return False
        except AttributeError: 
            return False


    def has_purchased_audiobook(self, audiobook):
        return AudiobookPurchase.objects.filter(user=self, audiobook=audiobook, status='COMPLETED').exists()


class AdminManager(BaseUserManager): 
    def create_admin(self, email, username, password, roles, **extra_fields):
        if not email: raise ValueError('Admin must have an email address')
        if not username: raise ValueError('Admin must have a username')
        if not password: raise ValueError('Admin must have a password')
        if not roles: raise ValueError('Admin must have at least one role')
        email = self.normalize_email(email)
        admin = self.model(email=email, username=username, roles=roles, **extra_fields)
        admin.set_password(password) 
        admin.save(using=self._db)
        return admin

class Admin(models.Model): 
    class RoleChoices(models.TextChoices):
        FULL_ACCESS = 'full_access', _('Full Access')
        MANAGE_USERS = 'manage_users', _('Manage Users')
        MANAGE_CONTENT = 'manage_content', _('Manage Content')
        MANAGE_CREATORS = 'manage_creators', _('Manage Creators')
        MANAGE_DISCUSSIONS = 'manage_discussions', _('Manage Discussions')
        MANAGE_TRANSACTIONS = 'manage_transactions', _('Manage Transactions')
        MANAGE_WITHDRAWALS = 'manage_withdrawals', _('Manage Withdrawals')

    adminid = models.AutoField(primary_key=True)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=255, unique=True)
    password = models.CharField(max_length=128) 
    roles = models.CharField(max_length=255, help_text="Comma-separated list of roles")
    is_active = models.BooleanField(default=True)
    last_login = models.DateTimeField(blank=True, null=True)

    objects = AdminManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'roles']

    def __str__(self):
        return self.username

    def set_password(self, raw_password):
        self.password = make_password(raw_password)
        self.last_login = None 

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def get_roles_list(self):
        if self.roles:
            return [role.strip() for role in self.roles.split(',') if role.strip()]
        return []
    
    def get_display_roles(self):
        if not self.roles:
            return "No Roles Assigned"
        role_list = self.roles.split(',')
        formatted_roles = []
        for role_code in role_list:
            role_code = role_code.strip()
            if role_code:
                label = dict(self.RoleChoices.choices).get(role_code, role_code.replace('_', ' ').title())
                formatted_roles.append(label)
        return ", ".join(formatted_roles)

    def has_role(self, role_value):
        return role_value in self.get_roles_list()

    @property
    def is_anonymous(self): 
        return False
    @property
    def is_authenticated(self): 
        return True
    
    def has_perm(self, perm, obj=None):
        return self.is_active and ('full_access' in self.get_roles_list())

    def has_module_perms(self, app_label):
        return self.is_active and ('full_access' in self.get_roles_list())

    class Meta:
        db_table = 'ADMINS'
        verbose_name = "Custom Administrator"
        verbose_name_plural = "Custom Administrators"


class CoinTransaction(models.Model): 
    TRANSACTION_TYPES = (
        ('purchase', 'Purchase'), 
        ('reward', 'Reward'), 
        ('spent', 'Spent'), 
        ('refund', 'Refund'),
        ('gift_sent', 'Gift Sent'),
        ('gift_received', 'Gift Received'),
        ('withdrawal', 'Withdrawal'), 
        ('withdrawal_fee', 'Withdrawal Fee') 
    )
    STATUS_CHOICES = (
        ('completed', 'Completed'),
        ('pending', 'Pending'),
        ('failed', 'Failed'),
        ('processing', 'Processing'), 
        ('rejected', 'Rejected') 
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='coin_transactions')
    transaction_type = models.CharField(max_length=15, choices=TRANSACTION_TYPES)
    amount = models.IntegerField() 
    transaction_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    pack_name = models.CharField(max_length=255, blank=True, null=True) 
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) 
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='gifts_sent')
    recipient = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='gifts_received')
    description = models.TextField(blank=True, null=True) 

    class Meta:
        db_table = 'COIN_TRANSACTIONS'
        ordering = ['-transaction_date']

    def __str__(self):
        return f"{self.user.username} - {self.get_transaction_type_display()} ({self.amount}) on {self.transaction_date.strftime('%Y-%m-%d')}"


class Creator(models.Model): 
    VERIFICATION_STATUS_CHOICES = (
        ('pending', 'Pending Verification'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    )
    unique_name_validator = RegexValidator(
        regex=r'^[a-zA-Z0-9_]+$',
        message='Unique name can only contain letters, numbers, and underscores.',
        code='invalid_creator_unique_name'
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name='creator_profile')
    cid = models.CharField(max_length=100, unique=True, null=True, blank=True, db_index=True, help_text="Unique Creator ID (e.g., cid-1001), generated upon approval.")
    creator_name = models.CharField(max_length=100, blank=False, null=False, help_text="Public display name for the creator")
    creator_unique_name = models.CharField(max_length=50, unique=True, blank=False, null=False, validators=[unique_name_validator], help_text="Unique handle (@yourname) for URLs and mentions")
    creator_profile_pic = models.ImageField(upload_to=creator_profile_pic_path, blank=True, null=True, help_text="Optional: Specific profile picture for the creator page.")
    total_earning = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Total gross earnings from sales before platform fees.")
    available_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Net earnings available for withdrawal after platform fees.")
    cnic_front = models.ImageField(upload_to=creator_cnic_path, blank=False, null=True, help_text="Front side of CNIC") 
    cnic_back = models.ImageField(upload_to=creator_cnic_path, blank=False, null=True, help_text="Back side of CNIC") 
    verification_status = models.CharField(max_length=10, choices=VERIFICATION_STATUS_CHOICES, default='pending')
    terms_accepted_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when creator terms were accepted")
    is_banned = models.BooleanField(default=False, db_index=True, help_text="Is this creator currently banned?")
    ban_reason = models.TextField(blank=True, null=True, help_text="Reason provided by admin if creator is banned.")
    banned_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when the creator was banned.")
    banned_by = models.ForeignKey(Admin, on_delete=models.SET_NULL, null=True, blank=True, related_name='banned_creators', help_text="Admin who banned this creator.")
    rejection_reason = models.TextField(blank=True, null=True, help_text="Reason provided by admin if application is rejected")
    last_application_date = models.DateTimeField(null=True, blank=True, help_text="Timestamp of the most recent application submission")
    application_attempts_current_month = models.PositiveIntegerField(default=0, help_text="Number of applications submitted in the current cycle (resets monthly)")
    approved_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when the application was approved.")
    approved_by = models.ForeignKey(Admin, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_creators', help_text="Admin who approved this application.")
    attempts_at_approval = models.PositiveIntegerField(null=True, blank=True, help_text="Number of attempts made when this application was approved.") 
    welcome_popup_shown = models.BooleanField(default=False, help_text="Has the 'Welcome Creator' popup been shown?") 
    rejection_popup_shown = models.BooleanField(default=False, help_text="Has the 'Application Rejected' popup been shown?") 
    admin_notes = models.TextField(blank=True, null=True, help_text="Internal notes for admins (e.g., unban reason).") 
    last_name_change_date = models.DateTimeField(null=True, blank=True, help_text="Timestamp of the last display name change.") 
    last_unique_name_change_date = models.DateTimeField(null=True, blank=True, help_text="Timestamp of the last unique name (@handle) change.") 
    last_withdrawal_request_date = models.DateTimeField(null=True, blank=True, help_text="Timestamp of the last non-cancelled withdrawal request made by the creator.") 
    profile_pic_updated_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp of the last profile picture update.") 

    class Meta:
        db_table = "CREATORS" 

    def __str__(self):
        status_part = "Banned" if self.is_banned else (self.cid or self.get_verification_status_display()) 
        return f"Creator: {self.creator_name or self.user.username} ({status_part})"

    @property
    def is_approved(self):
        return self.verification_status == 'approved' and not self.is_banned

    def get_attempts_this_month(self):
        if not self.last_application_date:
            return 0
        now = timezone.now()
        if (self.last_application_date.year == now.year and 
            self.last_application_date.month == now.month):
            return self.application_attempts_current_month
        else:
            return 0 

    def can_reapply(self):
        if self.is_banned or self.verification_status in ['approved', 'pending']:
            return False
        if self.verification_status == 'rejected':
            attempts_this_month = self.get_attempts_this_month()
            return attempts_this_month < getattr(settings, 'MAX_CREATOR_APPLICATION_ATTEMPTS', 3) 
        return True 

    def can_request_withdrawal(self):
        has_pending_or_processing_request = self.withdrawal_requests.filter(
            status__in=['pending', 'processing', 'approved'] 
        ).exists()

        if has_pending_or_processing_request:
            return False, "You already have a withdrawal request that is being processed or is pending approval."

        if self.last_withdrawal_request_date: 
            cooldown_days = getattr(settings, 'WITHDRAWAL_REQUEST_COOLDOWN_DAYS', 15)
            cooldown = timedelta(days=cooldown_days)
            if timezone.now() < self.last_withdrawal_request_date + cooldown:
                next_allowed_date = self.last_withdrawal_request_date + cooldown
                return False, f"You can make another withdrawal request after {next_allowed_date.strftime('%B %d, %Y')}."
        
        return True, ""


class CreatorApplicationLog(models.Model): 
    STATUS_CHOICES = (
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    )
    log_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name='application_logs')
    application_date = models.DateTimeField(default=timezone.now, help_text="Timestamp when this specific application was submitted")
    attempt_number_monthly = models.PositiveIntegerField(help_text="Which attempt this was in the submission month")
    creator_name_submitted = models.CharField(max_length=100)
    creator_unique_name_submitted = models.CharField(max_length=50)
    cnic_front_submitted = models.ImageField(upload_to=creator_cnic_path, blank=True, null=True, help_text="CNIC Front submitted for this attempt")
    cnic_back_submitted = models.ImageField(upload_to=creator_cnic_path, blank=True, null=True, help_text="CNIC Back submitted for this attempt")
    terms_accepted_at_submission = models.DateTimeField(help_text="Timestamp when terms were accepted for this submission")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='submitted', db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when the application was approved or rejected")
    processed_by = models.ForeignKey(Admin, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_creator_applications', help_text="Admin who approved or rejected this specific application.")
    rejection_reason = models.TextField(blank=True, null=True, help_text="Reason provided if this specific application was rejected")

    class Meta:
        db_table = "CREATOR_APPLICATION_LOGS"
        ordering = ['creator', '-application_date']
        verbose_name = "Creator Application Log"
        verbose_name_plural = "Creator Application Logs"

    def __str__(self):
        return f"Log for {self.creator.user.username} ({self.application_date.strftime('%Y-%m-%d %H:%M')}) - Status: {self.get_status_display()}"


class Audiobook(models.Model):
    STATUS_CHOICES = (
        ('PUBLISHED', 'Published'),
        ('INACTIVE', 'Inactive'), 
        ('REJECTED', 'Rejected'), 
        ('PAUSED_BY_ADMIN', 'Paused by Admin') 
    )
    audiobook_id = models.AutoField(primary_key=True) 
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255, blank=True, null=True)
    narrator = models.CharField(max_length=255, blank=True, null=True) 
    language = models.CharField(max_length=100, blank=True, null=True)
    duration = models.DurationField(blank=True, null=True) 
    description = models.TextField(blank=False, null=True) 
    publish_date = models.DateTimeField(default=timezone.now) 
    genre = models.CharField(max_length=100, blank=True, null=True)
    creator = models.ForeignKey('Creator', on_delete=models.CASCADE, related_name="audiobooks") 
    slug = models.SlugField(max_length=255, unique=True, blank=True) 
    cover_image = models.ImageField(upload_to='audiobook_covers/', blank=False, null=True) 
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PUBLISHED', db_index=True, help_text="The current status of the audiobook.")
    
    total_views = models.PositiveIntegerField(default=0, help_text="Total number of times the audiobook detail page has been viewed.")
    
    is_paid = models.BooleanField(default=False, help_text="Is this audiobook paid or free?")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, validators=[MinValueValidator(Decimal('0.00'))], help_text="Price in PKR if the audiobook is paid (set to 0.00 if free).")
    
    total_sales = models.PositiveIntegerField(default=0, help_text="Number of times this audiobook has been sold.")
    total_revenue_generated = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Total gross revenue generated by this audiobook before platform fees.")
    
    created_at = models.DateTimeField(default=timezone.now, editable=False, help_text="Timestamp when the audiobook record was created.")
    updated_at = models.DateTimeField(auto_now=True, help_text="Timestamp when the audiobook record was last updated.")

    class Meta:
        db_table = "AUDIOBOOKS" 
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.slug or ('update_fields' in kwargs and 'title' in kwargs.get('update_fields', [])):
            base_slug = slugify(self.title) or "audiobook"
            slug = base_slug
            counter = 1
            pk_to_exclude = self.pk if self.pk is not None else uuid.uuid4() 
            while Audiobook.objects.filter(slug=slug).exclude(pk=pk_to_exclude).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        
        if not self.is_paid:
            self.price = Decimal('0.00')
        
        super().save(*args, **kwargs)

    def __str__(self):
        price_info = f"(PKR {self.price})" if self.is_paid else "(Free)"
        status_display = self.get_status_display() if hasattr(self, 'get_status_display') else self.status
        return f"{self.title} [{status_display}] {price_info}"

    def clean(self):
        super().clean()
        if not self.is_paid and self.price != Decimal('0.00'):
            raise ValidationError({'price': _('Price must be 0.00 for free audiobooks.')})

    @property
    def average_rating(self):
        avg = self.reviews.aggregate(Avg('rating'))['rating__avg']
        return round(avg, 1) if avg is not None else None 

    def update_sales_analytics(self, amount_paid):
        if self.status == 'PUBLISHED': 
            Audiobook.objects.filter(pk=self.pk).update(
                total_sales=F('total_sales') + 1,
                total_revenue_generated=F('total_revenue_generated') + Decimal(amount_paid)
            )
            self.refresh_from_db(fields=['total_sales', 'total_revenue_generated']) 
        else: 
            logger.warning(f"Sale not recorded for analytics as audiobook '{self.title}' is not PUBLISHED. Status: {self.status}")
    
    @property
    def first_chapter_audio_url(self):
        first_chapter = self.chapters.order_by('chapter_order').first()
        if first_chapter and first_chapter.audio_file and first_chapter.audio_file.name:
            try:
                if default_storage.exists(first_chapter.audio_file.name):
                    return first_chapter.audio_file.url
            except Exception:
                pass 
        return None

    @property
    def first_chapter_title(self):
        first_chapter = self.chapters.order_by('chapter_order').first()
        if first_chapter:
            return first_chapter.chapter_name
        return None


class Chapter(models.Model):
    TTS_VOICE_CHOICES = [
        # ('default', 'Original Uploaded Audio'), # Removed as per request
        ('ali_narrator', 'Ali Narrator (Male PK)'),
        ('aisha_narrator', 'Aisha Narrator (Female PK)'),
        # Add other specific voice IDs as you map them to Google voices
    ]

    chapter_id = models.AutoField(primary_key=True) 
    audiobook = models.ForeignKey(Audiobook, on_delete=models.CASCADE, related_name="chapters") 
    chapter_name = models.CharField(max_length=255)
    chapter_order = models.PositiveIntegerField()
    
    audio_file = models.FileField(upload_to="chapters_audio/", blank=True, null=True, help_text="Audio file for the chapter (MP3, WAV, OGG). Either upload this or provide text for TTS.") 
    text_content = models.TextField(blank=True, null=True, help_text="Text content for this chapter. Used for TTS if audio_file is not uploaded directly, or can be generated from uploaded audio via STT.")
    
    is_tts_generated = models.BooleanField(default=False, help_text="True if this chapter's audio was generated using Text-to-Speech.")
    tts_voice_id = models.CharField(
        max_length=50, 
        choices=TTS_VOICE_CHOICES, 
        default=None, # IMPORTANT: Changed default to None
        blank=True, null=True, 
        help_text="Voice used if audio was generated by TTS."
    )
    
    is_preview_eligible = models.BooleanField(default=False, help_text="Can this chapter be previewed by premium users if the book is paid but not purchased?")
    
    created_at = models.DateTimeField(default=timezone.now, editable=False, help_text="Timestamp when the chapter was added.")
    updated_at = models.DateTimeField(auto_now=True, help_text="Timestamp when the chapter was last updated.")

    class Meta:
        db_table = "CHAPTERS" 
        ordering = ['audiobook', 'chapter_order']
        unique_together = ('audiobook', 'chapter_order')

    def __str__(self):
        tts_info = ""
        if self.is_tts_generated and self.tts_voice_id:
            try:
                # Check if get_tts_voice_id_display method exists and tts_voice_id is not None
                if hasattr(self, 'get_tts_voice_id_display') and self.tts_voice_id:
                    display_name = self.get_tts_voice_id_display()
                    # Avoid showing "None" if tts_voice_id was None but somehow passed the check
                    if display_name and str(display_name).lower() != 'none': 
                        tts_info = f" (TTS: {display_name})"
                    elif self.tts_voice_id: # Fallback to raw ID if display name is None/empty but ID exists
                         tts_info = f" (TTS: {self.tts_voice_id})"
                elif self.tts_voice_id: # Fallback if get_tts_voice_id_display is missing
                    tts_info = f" (TTS: {self.tts_voice_id})"
            except Exception: # Catch any error during display name retrieval
                if self.tts_voice_id: # Still try to show the ID if an error occurred
                    tts_info = f" (TTS: {self.tts_voice_id} - Error displaying name)"
        
        return f"{self.chapter_order}: {self.chapter_name}{tts_info} ({self.audiobook.title})"

    def save(self, *args, **kwargs):
        if self.chapter_order == 1:
            self.is_preview_eligible = True
        if not self.is_tts_generated:
            self.tts_voice_id = None 
        super().save(*args, **kwargs)

    @property
    def duration_display(self): 
        return "--:--" 


class Review(models.Model): 
    review_id = models.AutoField(primary_key=True) 
    audiobook = models.ForeignKey(Audiobook, on_delete=models.CASCADE, related_name='reviews') 
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], help_text="Rating from 1 to 5 stars.")
    comment = models.TextField(blank=True, null=True, help_text="User's review comment (optional).")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'REVIEWS' 
        ordering = ['-created_at']
        unique_together = ('audiobook', 'user')
        verbose_name = "Audiobook Review"
        verbose_name_plural = "Audiobook Reviews"

    def __str__(self):
        return f"Review by {self.user.username} for {self.audiobook.title} ({self.rating} stars)"


class Subscription(models.Model): 
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
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription')
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES)
    start_date = models.DateTimeField() 
    end_date = models.DateTimeField(null=True, blank=True) 
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active', db_index=True)
    
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    stripe_payment_method_brand = models.CharField(max_length=50, blank=True, null=True, help_text="e.g., visa, mastercard")
    stripe_payment_method_last4 = models.CharField(max_length=4, blank=True, null=True, help_text="Last 4 digits of the card")

    class Meta:
        db_table = 'SUBSCRIPTIONS' 

    def __str__(self):
        return f"{self.user.username} - {self.get_plan_display()} ({self.get_status_display()})"

    def is_active(self):
        return self.status == 'active' and (self.end_date is None or self.end_date >= timezone.now())

    def cancel(self):
        if self.status == 'active':
            self.status = 'canceled'
            self.save(update_fields=['status'])

    def update_status(self): 
        now = timezone.now()
        if self.status == 'active' and self.end_date and self.end_date < now:
            self.status = 'expired'
            self.save(update_fields=['status'])
            if self.user.subscription_type == 'PR': 
                self.user.subscription_type = 'FR'
                self.user.save(update_fields=['subscription_type'])
    
    @property
    def remaining_days(self):
        if self.status in ['active', 'canceled'] and self.end_date: 
            remaining = self.end_date - timezone.now()
            return max(0, remaining.days)
        return 0


class WithdrawalAccount(models.Model): 
    ACCOUNT_TYPE_CHOICES = (
        ('bank', 'Bank Account'),
        ('jazzcash', 'JazzCash'),
        ('easypaisa', 'Easypaisa'),
        ('nayapay', 'Nayapay'),
        ('upaisa', 'Upaisa')
    )
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
    account_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name='withdrawal_accounts')
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES, blank=False, null=False)
    account_title = models.CharField(max_length=100, blank=False, null=False, help_text="Full name registered with the account.")
    account_identifier = models.CharField(max_length=34, blank=False, null=False, help_text="Account Number (JazzCash/Easypaisa/Nayapay/Upaisa) or IBAN (Bank Account).")
    bank_name = models.CharField(max_length=100, blank=True, null=True, help_text="Required only if Account Type is 'Bank Account'.")
    is_primary = models.BooleanField(default=False, help_text="Mark one account as primary for withdrawals.")
    added_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when this account was last used for a withdrawal.")

    class Meta:
        db_table = "WITHDRAWAL_ACCOUNTS" 
        ordering = ['creator', '-added_at']
        constraints = [
            models.UniqueConstraint(fields=['creator'], condition=models.Q(is_primary=True), name='unique_primary_withdrawal_account')
        ]

    def __str__(self):
        identifier_display = self.account_identifier[-4:] 
        primary_marker = " (Primary)" if self.is_primary else ""
        return f"{self.creator.creator_name} - {self.get_account_type_display()}: ...{identifier_display}{primary_marker}"

    def clean(self):
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
        self.full_clean() 
        if self.is_primary:
            WithdrawalAccount.objects.filter(creator=self.creator, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class WithdrawalRequest(models.Model): 
    STATUS_CHOICES = (
        ('pending', 'Pending'), 
        ('approved', 'Approved'), 
        ('processing', 'Processing'), 
        ('completed', 'Completed'), 
        ('rejected', 'Rejected by Admin'), 
        ('failed', 'Failed'), 
        ('cancelled', 'Cancelled by Creator'), 
    )
    request_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name='withdrawal_requests')
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))], help_text="Amount requested for withdrawal in PKR")
    withdrawal_account = models.ForeignKey(WithdrawalAccount, on_delete=models.SET_NULL, null=True, blank=False, related_name='withdrawal_requests', help_text="The account selected for this withdrawal request.")
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='pending', db_index=True)
    request_date = models.DateTimeField(auto_now_add=True)
    processed_date = models.DateTimeField(null=True, blank=True, help_text="Timestamp when payment was processed/completed/failed/rejected/cancelled")
    admin_notes = models.TextField(blank=True, null=True, help_text="Notes from admin (e.g., rejection reason, processing details)")
    processed_by = models.ForeignKey(Admin, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_withdrawals', help_text="Admin who last updated the status")

    class Meta:
        db_table = 'WITHDRAWAL_REQUESTS' 
        ordering = ['-request_date']
        verbose_name = "Withdrawal Request"
        verbose_name_plural = "Withdrawal Requests"

    def __str__(self):
        account_info = f"to ...{self.withdrawal_account.account_identifier[-4:]}" if self.withdrawal_account else "to [Deleted Account]"
        return f"Withdrawal Request {self.request_id} by {self.creator.creator_name} for PKR {self.amount} {account_info} ({self.get_status_display()})"
    
    def approve(self, admin_user):
        if self.status == 'pending':
            self.status = 'approved'
            self.processed_by = admin_user
            note = f"Approved by {admin_user.username} on {timezone.now().strftime('%Y-%m-%d %H:%M')}."
            self.admin_notes = f"{note}\n{self.admin_notes}" if self.admin_notes else note
            self.save(update_fields=['status', 'admin_notes', 'processed_by'])
    
    def reject(self, admin_user, reason=""): 
        if self.status in ['pending', 'approved']: 
            original_amount = self.amount
            self.status = 'rejected' 
            self.processed_by = admin_user
            self.processed_date = timezone.now()
            note = f"Rejected by Admin {admin_user.username} on {self.processed_date.strftime('%Y-%m-%d %H:%M')}. Reason: {reason}"
            self.admin_notes = f"{note}\n{self.admin_notes}" if self.admin_notes else note
            try:
                with transaction.atomic():
                    self.save(update_fields=['status', 'admin_notes', 'processed_date', 'processed_by'])
                    creator = self.creator
                    creator.available_balance = F('available_balance') + original_amount
                    creator.save(update_fields=['available_balance']) 
                    logger.info(f"Returned {original_amount} to creator {creator.creator_name}'s balance after admin rejection.") 
            except Exception as e: 
                logger.error(f"ERROR: Failed to save admin rejection or return amount {original_amount} to creator {self.creator.creator_name}: {e}")

    def process(self, admin_user, reference=""): 
        if self.status == 'approved': 
            self.status = 'processing'
            self.processed_by = admin_user
            note = f"Processing initiated by {admin_user.username} on {timezone.now().strftime('%Y-%m-%d %H:%M')}."
            if reference: note += f" Ref: {reference}"
            self.admin_notes = f"{note}\n{self.admin_notes}" if self.admin_notes else note
            self.save(update_fields=['status', 'admin_notes', 'processed_by'])

    def complete(self, admin_user, reference=""):
        if self.status == 'processing': 
            self.status = 'completed'
            self.processed_date = timezone.now()
            self.processed_by = admin_user
            note = f"Completed by {admin_user.username} on {self.processed_date.strftime('%Y-%m-%d %H:%M')}."
            if reference: note += f" Ref: {reference}"
            self.admin_notes = f"{note}\n{self.admin_notes}" if self.admin_notes else note
            self.save(update_fields=['status', 'processed_date', 'admin_notes', 'processed_by'])
            if self.withdrawal_account:
                self.withdrawal_account.last_used_at = self.processed_date
                self.withdrawal_account.save(update_fields=['last_used_at'])
    
    def fail(self, admin_user, reason=""):
        if self.status in ['processing', 'approved']: 
            original_amount = self.amount
            self.status = 'failed'
            self.processed_date = timezone.now()
            self.processed_by = admin_user
            note = f"Processing failed on {self.processed_date.strftime('%Y-%m-%d %H:%M')}. Reason: {reason}"
            self.admin_notes = f"{note}\n{self.admin_notes}" if self.admin_notes else note
            try:
                with transaction.atomic():
                    self.save(update_fields=['status', 'processed_date', 'admin_notes', 'processed_by'])
                    creator = self.creator
                    creator.available_balance = F('available_balance') + original_amount
                    creator.save(update_fields=['available_balance'])
                    logger.info(f"Returned {original_amount} to creator {creator.creator_name}'s balance after processing failure.")
            except Exception as e: 
                logger.error(f"ERROR: Failed to save failure or return amount {original_amount} to creator {self.creator.creator_name} after failure: {e}")


class AudiobookPurchase(models.Model): 
    purchase_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='audiobook_purchases')
    audiobook = models.ForeignKey(Audiobook, on_delete=models.CASCADE, related_name='audiobook_sales') 
    purchase_date = models.DateTimeField(auto_now_add=True)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, help_text="Total amount paid by the user in PKR.")
    platform_fee_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('10.00'), help_text="Platform fee percentage at the time of purchase.")
    platform_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Calculated platform fee in PKR.")
    creator_share_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Amount credited to the creator in PKR.")
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True, null=True, db_index=True, help_text="Stripe Checkout Session ID for reference.")
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, null=True, db_index=True, help_text="Stripe Payment Intent ID for reference.")
    STATUS_CHOICES = [('PENDING', 'Pending'), ('COMPLETED', 'Completed'), ('FAILED', 'Failed'), ('REFUNDED', 'Refunded')]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')


    class Meta:
        db_table = 'AUDIOBOOK_PURCHASES' 
        ordering = ['-purchase_date']
        unique_together = ('user', 'audiobook') 
        verbose_name = "Audiobook Purchase"
        verbose_name_plural = "Audiobook Purchases"

    def __str__(self):
        return f"Purchase of '{self.audiobook.title}' by {self.user.username} on {self.purchase_date.strftime('%Y-%m-%d')}"

    def save(self, *args, **kwargs):
        if self.amount_paid is not None: 
            self.platform_fee_amount = (self.amount_paid * self.platform_fee_percentage) / Decimal('100.00')
            self.creator_share_amount = self.amount_paid - self.platform_fee_amount
        super().save(*args, **kwargs)


class CreatorEarning(models.Model): 
    earning_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name='earnings_log') 
    audiobook = models.ForeignKey(Audiobook, on_delete=models.SET_NULL, null=True, blank=True, related_name='earning_entries') 
    purchase = models.OneToOneField(AudiobookPurchase, on_delete=models.CASCADE, null=True, blank=True, related_name='earning_record') 
    
    EARNING_TYPES = (
        ('sale', 'Sale Earning'),
        ('view', 'View Earning') 
    )
    earning_type = models.CharField(max_length=10, choices=EARNING_TYPES, default='sale', db_index=True)
    amount_earned = models.DecimalField(max_digits=10, decimal_places=2, help_text="Net amount earned by the creator for this transaction (sale or view batch).")
    transaction_date = models.DateTimeField(default=timezone.now, db_index=True) 
    
    view_count_for_earning = models.PositiveIntegerField(null=True, blank=True, help_text="Number of views this earning entry represents, if type is 'view'.")
    earning_per_view_at_transaction = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True, help_text="Earning rate per view at the time of this transaction, if type is 'view'.")
    
    notes = models.TextField(blank=True, null=True, help_text="Any notes related to this earning (e.g., 'From audiobook sale', 'Monthly view payout').")
    audiobook_title_at_transaction = models.CharField(max_length=255, blank=True, null=True, help_text="Title of the audiobook at the time of the transaction.") 

    class Meta:
        db_table = 'CREATOR_EARNINGS' 
        ordering = ['-transaction_date']
        verbose_name = "Creator Earning"
        verbose_name_plural = "Creator Earnings"

    def __str__(self):
        title = self.audiobook_title_at_transaction if self.audiobook_title_at_transaction else (self.audiobook.title if self.audiobook else 'N/A')
        return f"Earning of PKR {self.amount_earned} for {self.creator.creator_name} from '{title}' ({self.get_earning_type_display()}) on {self.transaction_date.strftime('%Y-%m-%d')}"

    def save(self, *args, **kwargs):
        if not self.audiobook_title_at_transaction and self.audiobook: 
            self.audiobook_title_at_transaction = self.audiobook.title
        super().save(*args, **kwargs)


class AudiobookViewLog(models.Model): 
    view_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    audiobook = models.ForeignKey(Audiobook, on_delete=models.CASCADE, related_name='view_logs')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audiobook_views') 
    viewed_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = 'AUDIOBOOK_VIEW_LOGS' 
        ordering = ['-viewed_at']
        verbose_name = "Audiobook View Log"
        verbose_name_plural = "Audiobook View Logs"
        indexes = [
            models.Index(fields=['audiobook', 'viewed_at']),
            models.Index(fields=['user', 'audiobook', 'viewed_at']),
        ]

    def __str__(self):
        user_str = self.user.username if self.user else "Anonymous"
        return f"View of '{self.audiobook.title}' by {user_str} at {self.viewed_at.strftime('%Y-%m-%d %H:%M')}"
