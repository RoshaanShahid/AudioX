from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
#from .models import User, Admin, CoinTransaction, Subscription



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
