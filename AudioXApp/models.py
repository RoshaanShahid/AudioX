from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.hashers import make_password




class CustomUserManager(BaseUserManager):
    def create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError(_("The Email must be set"))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class SubscriptionType(models.TextChoices):
        FREE = 'FR', _('Free')
        PREMIUM = 'PR', _('Premium')

    profile_pic = models.ImageField(
        upload_to='profile_pics/',
        blank=True,
        null=True,
        default=settings.STATIC_URL + 'img/default_profile.png'
    )
    userid = models.AutoField(primary_key=True)
    email = models.EmailField(_("email address"), unique=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    password = models.CharField(max_length=255)
    full_name = models.CharField(max_length=255, blank=True, null=True)
    date_joined = models.DateTimeField(default=timezone.now)
    username = models.CharField(max_length=150, blank=True, null=True)
    bio = models.TextField(max_length=500, blank=True, null=True)
    subscription_type = models.CharField(
        max_length=2,
        choices=SubscriptionType.choices,
        default=SubscriptionType.FREE,
    )
    coins = models.PositiveIntegerField(default=0)  # Coins directly in the User model

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:
        db_table = 'USERS'

    def __str__(self):
        return self.email


# 🚀 Creator Model (Disjoint from User)
class Creator(models.Model):
    creator_id = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    total_audiobooks = models.PositiveIntegerField(default=0)
    total_earning = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    bio = models.TextField(max_length=500, blank=True, null=True)

    class Meta:
        db_table = "CREATORS"

    def __str__(self):
        return f"Creator: {self.creator_id.email}"

class Admin(models.Model):
    class RoleChoices(models.TextChoices):
        FULL_ACCESS = 'full_access', _('Full Access')
        MANAGE_CONTENT = 'manage_content', _('Manage Content')
        MANAGE_CREATORS = 'manage_creators', _('Manage Creators')
        MANAGE_DISCUSSIONS = 'manage_discussions', _('Manage Discussions')
        MANAGE_TRANSACTIONS = 'manage_transactions', _('Manage Transactions')

    adminid = models.AutoField(primary_key=True)
    email = models.EmailField(_("email address"), unique=True)
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=255)
    roles = models.CharField(
        max_length=255,
        choices=RoleChoices.choices,
        blank=True,
    )

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def __str__(self):
        return self.username

    class Meta:
        db_table = 'ADMINS'


# 🚀 Audiobook Model (Linked to Creator)
class Audiobook(models.Model):
    audiobook_id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255, blank=True, null=True)
    narrator = models.CharField(max_length=255, blank=True, null=True)
    language = models.CharField(max_length=100, blank=True, null=True)
    duration = models.DurationField(blank=True, null=True)
    file_url = models.URLField()  # File storage URL
    description = models.TextField(blank=True, null=True)
    publish_date = models.DateTimeField(default=timezone.now)
    genre = models.CharField(max_length=100, blank=True, null=True)
    
    # Foreign Key to Creator (who uploads audiobooks)
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name="audiobooks")

    class Meta:
        db_table = "AUDIOBOOKS"

    def __str__(self):
        return self.title
    

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

    

