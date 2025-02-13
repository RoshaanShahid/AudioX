# models.py
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.utils.timezone import make_aware  # Import make_aware

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

    # Add related_name here:
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='audiox_users',  # Unique related_name
        blank=True,
        help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='audiox_users',  # Unique related_name
        blank=True,
        help_text='Specific permissions for this user.',
    )


    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'full_name']

    def __str__(self):
        return self.email

    class Meta:
        db_table = 'USERS'  # Specify the desired table name


class Admin(AbstractBaseUser, PermissionsMixin):
    adminid = models.AutoField(primary_key=True)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=255, unique=True)
    roles = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=True)
    is_superuser = models.BooleanField(default=False)

    groups = models.ManyToManyField(
        'auth.Group',
        related_name='audiox_admins',  # Unique related_name
        blank=True,
        help_text='The groups this admin belongs to. An admin will get all permissions granted to each of their groups.',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='audiox_admins',  # Unique related_name
        blank=True,
        help_text='Specific permissions for this admin.',
    )

    objects = BaseUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'roles']

    def __str__(self):
        return self.email
    
    def has_perm(self, perm, obj=None):
        "Does the admin have a specific permission?"
        # Simplest possible answer: Yes, always
        return True

    def has_module_perms(self, app_label):
        "Does the admin have permissions to view the app `app_label`?"
        # Simplest possible answer: Yes, always
        return True

    class Meta:
        db_table = 'ADMINS'  # Specify the desired table name

class CoinTransaction(models.Model):
    TRANSACTION_TYPES = (
        ('purchase', 'Purchase'),
        ('reward', 'Reward'),
        ('spent', 'Spent'),
        ('refund', 'Refund'),
        ('gift_sent', 'Gift Sent'),    # Add gift_sent
        ('gift_received', 'Gift Received'),  # Add gift_received
    )
    STATUS_CHOICES = (
        ('completed', 'Completed'),
        ('pending', 'Pending'),
        ('failed', 'Failed'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='coin_transactions')
    transaction_type = models.CharField(max_length=15, choices=TRANSACTION_TYPES)  # Increased max_length
    amount = models.IntegerField()
    transaction_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    pack_name = models.CharField(max_length=255, blank=True, null=True)  # for buycoins
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # for buycoins, ALLOW NULL
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='gifts_sent')  # For gifts
    recipient = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='gifts_received') # Add recipient field

    def __str__(self):
        return f"{self.user.username} - {self.transaction_type} - {self.amount} coins"

    class Meta:
        db_table = 'COIN_TRANSACTIONS'  # Specify the desired table name


# Add this new Subscription model.
class Subscription(models.Model):
    PLAN_CHOICES = (
        ('monthly', 'Monthly Premium'),
        ('annual', 'Annual Premium'),
        ('free', 'Free Tier')  # Good practice to include a free tier
    )
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('canceled', 'Canceled'),
        ('expired', 'Expired'),  # Important for handling renewals
        ('pending', 'Pending Payment'), # For initial payment processing
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription') # One subscription per user
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES)
    start_date = models.DateTimeField()  # When the subscription started
    end_date = models.DateTimeField()    # When it expires/renews
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)  # For Stripe integration
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True) # For Stripe integration

    def __str__(self):
        return f"{self.user.username} - {self.get_plan_display()} ({self.status})"

    class Meta:
        db_table = 'SUBSCRIPTIONS'

    def is_active(self):
        return self.status == 'active' and self.end_date >= timezone.now()
    
    def cancel(self):
        # Add logic here to handle cancellation with your payment gateway (e.g., Stripe).
        # This is a *placeholder*. You MUST implement actual cancellation logic.
        self.status = 'canceled'
        self.save()

    def update_status(self):
        """Updates the subscription status based on the end date."""
        now = timezone.now()
        if self.status == 'active' and self.end_date < now:
            self.status = 'expired'
            self.save()
    
    @property
    def remaining_days(self):
        """Calculates the number of days remaining in the subscription."""
        if self.status == 'active':
            remaining = self.end_date - timezone.now()
            return max(0, remaining.days)  # Ensure it's not negative
        return 0