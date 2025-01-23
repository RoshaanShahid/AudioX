from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.conf import settings

class CustomUserManager(BaseUserManager):
    """
    Custom user model manager where email is the unique identifiers
    for authentication instead of usernames.
    """

    def create_user(self, email, password, **extra_fields):
        """
        Create and save a User with the given email and password.
        """
        if not email:
            raise ValueError(_("The Email must be set"))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))
        return self.create_user(email, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model for the audix_db database.
    """

    class SubscriptionType(models.TextChoices):
        FREE = 'FR', _('Free')
        PREMIUM = 'PR', _('Premium')

    profile_pic = models.ImageField(
        upload_to='profile_pics/',
        blank=True,
        null=True,
        default=settings.STATIC_URL + 'img/default_profile.png'  # Default from static
    )
    userid = models.AutoField(primary_key=True)
    email = models.EmailField(_("email address"), unique=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    password = models.CharField(max_length=255) # password will be handled by set_password
    full_name = models.CharField(max_length=255, blank=True, null=True)
    date_joined = models.DateTimeField(default=timezone.now)
    username = models.CharField(max_length=150, blank=True, null=True)
    bio = models.TextField(max_length=500, blank=True, null=True)  # Add the bio field
    subscription_type = models.CharField(
        max_length=2,
        choices=SubscriptionType.choices,
        default=SubscriptionType.FREE,
    )

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)


    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:
        db_table = 'USERS'

    def __str__(self):
        return self.email