from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import validate_email # Import validate_email
# Import password hashing utilities needed for Admin model
from django.contrib.auth.hashers import make_password, check_password
# Import slugify
from django.utils.text import slugify


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        # Validate email format before creating user
        try:
            validate_email(email)
        except models.ValidationError:
             raise ValueError('Invalid email address format provided.')

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        # Ensure superuser has required fields if any are missing defaults
        extra_fields.setdefault('username', email.split('@')[0] + '_admin') # Example default username
        extra_fields.setdefault('full_name', 'Admin User') # Example default full name

        return self.create_user(email, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    user_id = models.AutoField(primary_key=True)
    full_name = models.CharField(max_length=255)
    username = models.CharField(max_length=255, unique=True)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    profile_pic = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    coins = models.IntegerField(default=0)
    subscription_type = models.CharField(max_length=2, choices=[('FR', 'Free'), ('PR', 'Premium')], default='FR')
    date_joined = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    # --- 2FA Field ---
    is_2fa_enabled = models.BooleanField(default=False, verbose_name="2FA Enabled")
    # --- End 2FA Field ---

    groups = models.ManyToManyField(
        'auth.Group',
        related_name='audiox_users', # Changed related_name to avoid clash
        blank=True,
        help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.',
        verbose_name=_('groups'),
        related_query_name="user",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='audiox_users_permissions', # Changed related_name to avoid clash
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name=_('user permissions'),
        related_query_name="user",
    )

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'full_name'] # Ensure these are provided for createsuperuser too

    def __str__(self):
        return self.email

# --- Admin Model ---
class Admin(models.Model):
    class RoleChoices(models.TextChoices):
        FULL_ACCESS = 'full_access', _('Full Access')
        MANAGE_CONTENT = 'manage_content', _('Manage Content')
        MANAGE_CREATORS = 'manage_creators', _('Manage Creators')
        MANAGE_DISCUSSIONS = 'manage_discussions', _('Manage Discussions')
        MANAGE_TRANSACTIONS = 'manage_transactions', _('Manage Transactions')

    adminid = models.AutoField(primary_key=True)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=255, unique=True)
    password = models.CharField(max_length=128) # Need password field for BaseUserManager
    roles = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=True)
    is_superuser = models.BooleanField(default=False)
    last_login = models.DateTimeField(blank=True, null=True) # Needed for admin interface/BaseUserManager

    groups = models.ManyToManyField(
        'auth.Group',
        related_name='audiox_admins',
        blank=True,
        help_text='The groups this admin belongs to. An admin will get all permissions granted to each of their groups.',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='audiox_admins_permissions', # Changed related_name
        blank=True,
        help_text='Specific permissions for this admin.',
    )

    # Use BaseUserManager for Admin as well if you want password hashing etc.
    # Otherwise, handle password setting manually or use a different approach.
    objects = BaseUserManager() # Using BaseUserManager requires password handling

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'roles']

    def __str__(self):
        return self.email

    # Required methods for BaseUserManager/Admin interface
    def set_password(self, raw_password):
        self.password = make_password(raw_password)
        # Store the raw password temporarily if needed, but generally avoid it
        # self._password = raw_password

    def check_password(self, raw_password):
        """
        Return a boolean of whether the raw_password was correct. Handles
        hashing formats behind the scenes.
        """
        # The setter argument is deprecated in recent Django versions for check_password
        # It automatically handles password upgrades if needed.
        return check_password(raw_password, self.password)

    def has_perm(self, perm, obj=None):
        # Simplistic check, customize as needed based on roles/permissions
        return self.is_active and (self.is_superuser or self.is_staff)

    def has_module_perms(self, app_label):
         # Simplistic check, customize as needed
        return self.is_active and (self.is_superuser or self.is_staff)

    class Meta:
        db_table = 'ADMINS'


# --- CoinTransaction Model ---
class CoinTransaction(models.Model):
    TRANSACTION_TYPES = (
        ('purchase', 'Purchase'),
        ('reward', 'Reward'),
        ('spent', 'Spent'),
        ('refund', 'Refund'),
        ('gift_sent', 'Gift Sent'),
        ('gift_received', 'Gift Received'),
    )
    STATUS_CHOICES = (
        ('completed', 'Completed'),
        ('pending', 'Pending'),
        ('failed', 'Failed'),
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

    class Meta:
        db_table = 'COIN_TRANSACTIONS'
        ordering = ['-transaction_date'] # Default ordering

# --- Creator Model ---
class Creator(models.Model):
    creator_id = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    total_audiobooks = models.PositiveIntegerField(default=0)
    total_earning = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    bio = models.TextField(max_length=500, blank=True, null=True)

    class Meta:
        db_table = "CREATORS"

    def __str__(self):
        return f"Creator: {self.creator_id.email}"

# --- Audiobook Model ---
class Audiobook(models.Model):
    audiobook_id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255, blank=True, null=True)
    narrator = models.CharField(max_length=255, blank=True, null=True)
    language = models.CharField(max_length=100, blank=True, null=True)
    duration = models.DurationField(blank=True, null=True)
    file_url = models.URLField(max_length=1024) # Increased max_length for potentially long URLs
    description = models.TextField(blank=True, null=True)
    publish_date = models.DateTimeField(default=timezone.now)
    genre = models.CharField(max_length=100, blank=True, null=True)
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name="audiobooks")
    slug = models.SlugField(max_length=255, unique=True, blank=True) # Added slug field

    class Meta:
        db_table = "AUDIOBOOKS"

    def save(self, *args, **kwargs):
        if not self.slug: # Generate slug only if it doesn't exist
            self.slug = slugify(self.title)
            # Ensure uniqueness if multiple books might have the same title
            original_slug = self.slug
            counter = 1
            while Audiobook.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

# --- Chapter Model ---
class Chapter(models.Model):
    chapter_id = models.AutoField(primary_key=True)
    audiobook = models.ForeignKey(Audiobook, on_delete=models.CASCADE, related_name="chapters")
    chapter_name = models.CharField(max_length=255)
    chapter_order = models.PositiveIntegerField()
    chapter_time = models.PositiveIntegerField(help_text="Start time in seconds", default=0) # Added default
    chapter_duration = models.PositiveIntegerField(help_text="Duration in seconds", default=0) # Added default
    audio_file = models.FileField(upload_to="chapters/", blank=True, null=True)

    class Meta:
        db_table = "CHAPTERS"
        ordering = ['chapter_order']

    def __str__(self):
        return f"{self.chapter_order}: {self.chapter_name} ({self.audiobook.title})"

# --- Subscription Model ---
class Subscription(models.Model):
    PLAN_CHOICES = (
        ('monthly', 'Monthly Premium'),
        ('annual', 'Annual Premium'),
        ('free', 'Free Tier') # Should likely be handled by absence of active sub
    )
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('canceled', 'Canceled'),
        ('expired', 'Expired'),
        ('pending', 'Pending Payment'), # For incomplete payments
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription')
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True) # Allow null end date for indefinite?
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active') # Default to active on creation?
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_plan_display()} ({self.status})"

    class Meta:
        db_table = 'SUBSCRIPTIONS'

    def is_active(self):
        """Checks if the subscription is currently active."""
        return self.status == 'active' and (self.end_date is None or self.end_date >= timezone.now())

    def cancel(self):
        """Marks the subscription as canceled."""
        # Depending on policy, you might set end_date here or let it expire naturally
        self.status = 'canceled'
        self.save(update_fields=['status'])
        # Update related user status
        self.user.subscription_type = 'FR'
        self.user.save(update_fields=['subscription_type'])


    def update_status(self):
        """Updates status to expired if end_date has passed."""
        now = timezone.now()
        if self.status == 'active' and self.end_date and self.end_date < now:
            self.status = 'expired'
            self.save(update_fields=['status'])
            # Update related user status
            self.user.subscription_type = 'FR'
            self.user.save(update_fields=['subscription_type'])


    @property
    def remaining_days(self):
        """Calculates remaining days for active subscriptions."""
        if self.is_active() and self.end_date:
            remaining = self.end_date - timezone.now()
            return max(0, remaining.days)
        return 0
