from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
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

    groups = models.ManyToManyField(
        'auth.Group',
        related_name='audiox_users',
        blank=True,
        help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='audiox_users',
        blank=True,
        help_text='Specific permissions for this user.',
    )

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'full_name']

    def __str__(self):
        return self.email

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
    roles = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=True)
    is_superuser = models.BooleanField(default=False)

    groups = models.ManyToManyField(
        'auth.Group',
        related_name='audiox_admins',
        blank=True,
        help_text='The groups this admin belongs to. An admin will get all permissions granted to each of their groups.',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='audiox_admins',
        blank=True,
        help_text='Specific permissions for this admin.',
    )

    objects = BaseUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'roles']

    def __str__(self):
        return self.email
    
    def has_perm(self, perm, obj=None):
        return True

    def has_module_perms(self, app_label):
        return True

    class Meta:
        db_table = 'ADMINS'

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

class Creator(models.Model):
    creator_id = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    total_audiobooks = models.PositiveIntegerField(default=0)
    total_earning = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    bio = models.TextField(max_length=500, blank=True, null=True)

    class Meta:
        db_table = "CREATORS"

    def __str__(self):
        return f"Creator: {self.creator_id.email}"

class Audiobook(models.Model):
    audiobook_id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255, blank=True, null=True)
    narrator = models.CharField(max_length=255, blank=True, null=True)
    language = models.CharField(max_length=100, blank=True, null=True)
    duration = models.DurationField(blank=True, null=True)
    file_url = models.URLField()
    description = models.TextField(blank=True, null=True)
    publish_date = models.DateTimeField(default=timezone.now)
    genre = models.CharField(max_length=100, blank=True, null=True)
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name="audiobooks")

    class Meta:
        db_table = "AUDIOBOOKS"


class Chapter(models.Model):
    chapter_id = models.AutoField(primary_key=True)
    audiobook = models.ForeignKey(Audiobook, on_delete=models.CASCADE, related_name="chapters")
    chapter_name = models.CharField(max_length=255)
    chapter_order = models.PositiveIntegerField()
    chapter_time = models.PositiveIntegerField(help_text="Start time in seconds")
    chapter_duration = models.PositiveIntegerField(help_text="Duration in seconds")
    audio_file = models.FileField(upload_to="chapters/", blank=True, null=True)  # 📌 New: Stores actual audio file

    class Meta:
        db_table = "CHAPTERS"
        ordering = ['chapter_order']  # Ensures chapters are retrieved in order

    def __str__(self):
        return f"{self.chapter_order}: {self.chapter_name} ({self.audiobook.title})"

class Subscription(models.Model):
    PLAN_CHOICES = (
        ('monthly', 'Monthly Premium'),
        ('annual', 'Annual Premium'),
        ('free', 'Free Tier')
    )
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('canceled', 'Canceled'),
        ('expired', 'Expired'),
        ('pending', 'Pending Payment'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription')
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_plan_display()} ({self.status})"

    class Meta:
        db_table = 'SUBSCRIPTIONS'

    def is_active(self):
        return self.status == 'active' and self.end_date >= timezone.now()
    
    def cancel(self):
        self.status = 'canceled'
        self.save()

    def update_status(self):
        now = timezone.now()
        if self.status == 'active' and self.end_date < now:
            self.status = 'expired'
            self.save()

    @property
    def remaining_days(self):
        if self.status == 'active':
            remaining = self.end_date - timezone.now()
            return max(0, remaining.days)
        return 0
