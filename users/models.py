from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _

class CustomUserManager(BaseUserManager):
    """
    Custom user model manager where email is the unique identifier
    for authentication instead of usernames.
    """
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_("The Email must be set"))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))
        return self.create_user(email, password, **extra_fields)

class CustomUser(AbstractUser):
    """
    Custom User model for Finovo.
    Uses email as the primary unique identifier for authentication
    and entirely removes the default username field.
    """
    username = None
    email = models.EmailField(_("email address"), unique=True)
    is_verified = models.BooleanField(default=False, help_text='Whether the user has verified their email.')
    
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return self.email


class UserProfile(models.Model):
    """
    One-to-one extension of CustomUser.
    Stores extra profile data like monthly savings goal.
    Created automatically on user registration via a Django signal.
    """
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    monthly_savings_goal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text='Monthly savings target in the user\'s currency.',
    )
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    phone_number = models.CharField(max_length=20, blank=True, default='',
        help_text='User phone number, e.g. +1 (555) 000-1234')
    username = models.CharField(max_length=50, blank=True, default='',
        help_text='Display username chosen at registration.')
    
    # OTP fields for email verification and forgot password
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    otp_expiry = models.DateTimeField(blank=True, null=True)

    @property
    def avatar_url(self):
        """Returns the full URL to the avatar either from file or generic default."""
        if self.avatar:
            try:
                return self.avatar.url
            except ValueError:
                return ""
        return ""

    def __str__(self):
        return f'Profile({self.user.email})'
