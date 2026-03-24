from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    """Validates the payload for the login endpoint."""

    email    = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
        style={'input_type': 'password'},
    )


class RegisterSerializer(serializers.Serializer):
    """Validates the payload for the registration endpoint."""

    full_name = serializers.CharField(max_length=150)
    username  = serializers.CharField(max_length=50, required=False, allow_blank=True)
    email     = serializers.EmailField()
    mobile_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    password  = serializers.CharField(
        min_length=6,
        write_only=True,
        style={'input_type': 'password'},
    )

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                'An account with this email already exists.'
            )
        return value.lower()

    def validate_username(self, value):
        from users.models import UserProfile
        if value and UserProfile.objects.filter(username__iexact=value.strip()).exists():
            raise serializers.ValidationError('This username is already taken.')
        return value.strip()


class ProfileSerializer(serializers.Serializer):
    """Serializes the combined User + UserProfile data for the profile endpoint."""

    id                   = serializers.SerializerMethodField()
    email                = serializers.SerializerMethodField()
    first_name           = serializers.SerializerMethodField()
    last_name            = serializers.SerializerMethodField()
    full_name            = serializers.SerializerMethodField()
    username             = serializers.SerializerMethodField()
    is_verified          = serializers.SerializerMethodField()
    monthly_savings_goal = serializers.SerializerMethodField()
    avatar_url           = serializers.SerializerMethodField()
    phone_number         = serializers.SerializerMethodField()

    def get_id(self, obj):
        return obj['user'].id

    def get_email(self, obj):
        return obj['user'].email

    def get_first_name(self, obj):
        return obj['user'].first_name

    def get_last_name(self, obj):
        return obj['user'].last_name

    def get_full_name(self, obj):
        user = obj['user']
        return f"{user.first_name} {user.last_name}".strip()

    def get_username(self, obj):
        return obj['profile'].username or ''

    def get_is_verified(self, obj):
        return getattr(obj['user'], 'is_verified', False)

    def get_monthly_savings_goal(self, obj):
        return float(obj['profile'].monthly_savings_goal)

    def get_avatar_url(self, obj):
        return obj['profile'].avatar_url or ''

    def get_phone_number(self, obj):
        return obj['profile'].phone_number or ''
