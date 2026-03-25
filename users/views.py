from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework_simplejwt.tokens import RefreshToken

from django.utils import timezone
from datetime import timedelta
from django.core.mail import send_mail
from django.conf import settings
from .email_utils import send_otp_email
import random
import string

from .serializers import LoginSerializer, RegisterSerializer, ProfileSerializer
from .models import UserProfile, OTPVerification

User = get_user_model()


class SendOTPView(APIView):
    """
    POST /api/users/send-otp/
    Generates a 6-digit OTP and sends it to the provided email via SMTP.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        if not email:
            return Response({'error': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        import random
        from django.core.mail import send_mail
        from django.conf import settings

        otp_code = str(random.randint(100000, 999999))
        
        # Save or update OTP in DB
        otp_obj, created = OTPVerification.objects.update_or_create(
            email=email,
            defaults={'otp_code': otp_code, 'is_verified': False}
        )
        # Note: update_or_create handles the timestamp automatically if using auto_now or manually
        from django.utils import timezone
        otp_obj.created_at = timezone.now()
        otp_obj.save()

        try:
            send_mail(
                subject='Finovo Verification Code',
                message=f'Your verification code for Finovo is: {otp_code}\n\nThis code will expire in 10 minutes.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            return Response({'message': 'OTP sent successfully.'}, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"SMTP Error: {str(e)}")
            return Response({'error': 'Failed to send email. please try again later.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VerifyOTPView(APIView):
    """
    POST /api/users/verify-otp/
    Verifies the 6-digit OTP for the given email.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        otp_code = request.data.get('otp', '').strip()

        if not email or not otp_code:
            return Response({'error': 'Email and OTP are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            otp_obj = OTPVerification.objects.get(email=email, otp_code=otp_code)
            
            if otp_obj.is_expired():
                return Response({'error': 'OTP has expired.'}, status=status.HTTP_400_BAD_REQUEST)
            
            otp_obj.is_verified = True
            otp_obj.save()
            
            # Step 3: Set is_verified = True for the User
            user_to_verify = User.objects.filter(email__iexact=email).first()
            if user_to_verify:
                user_to_verify.is_verified = True
                user_to_verify.save()
            
            return Response({'message': 'OTP verified successfully.'}, status=status.HTTP_200_OK)
        except OTPVerification.DoesNotExist:
            return Response({'error': 'Invalid OTP.'}, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    """
    POST /api/auth/login/

    Accepts { email, password } and returns JWT access + refresh tokens
    along with basic user profile data.
    """

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email    = serializer.validated_data['email']
        password = serializer.validated_data['password']

        from django.contrib.auth import authenticate

        # CustomUser uses email as USERNAME_FIELD
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response(
                {'error': 'No account found with this email address.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        authenticated_user = authenticate(
            request, email=user.email, password=password
        )
        if authenticated_user is None:
            return Response(
                {'error': 'Incorrect password. Please try again.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(authenticated_user)
        return Response(
            {
                'access':  str(refresh.access_token),
                'refresh': str(refresh),
                'user': {
                    'id':         authenticated_user.id,
                    'email':      authenticated_user.email,
                    'first_name': authenticated_user.first_name,
                    'last_name':  authenticated_user.last_name,
                    'is_verified': getattr(authenticated_user, 'is_verified', False),
                },
            },
            status=status.HTTP_200_OK,
        )


class RegisterView(APIView):
    """
    POST /api/auth/register/

    Accepts { full_name, email, password }.
    Creates a new user and immediately returns JWT tokens so the user
    is logged in right after registration.
    """

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        full_name = serializer.validated_data['full_name'].strip()
        username  = serializer.validated_data.get('username', '').strip()
        email          = serializer.validated_data['email']
        mobile_number  = serializer.validated_data.get('mobile_number', '').strip()
        password       = serializer.validated_data['password']

        # Split full name into first / last name
        name_parts = full_name.split(' ', 1)
        first_name = name_parts[0]
        last_name  = name_parts[1] if len(name_parts) > 1 else ''

        user = User.objects.create_user(
            email=email,
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_verified=False,
        )

        from .models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.username = username
        profile.phone_number = mobile_number
        
        # Send initial verification OTP
        try:
            # Generate initial OTP for email verification
            otp = ''.join(random.choices(string.digits, k=6))
            profile.otp_code = otp
            profile.otp_expiry = timezone.now() + timedelta(minutes=10)
            profile.save()
            
            send_otp_email(user, otp, 'verification')
        except Exception as e:
            print(f"Error sending welcome OTP: {e}")
            profile.save() # Ensure profile is saved even if mail fails

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                'message': 'Registration successful. Account created.',
                'user': {
                    'id':           user.id,
                    'email':        user.email,
                    'first_name':   user.first_name,
                    'last_name':    user.last_name,
                    'username':     username,
                    'phone_number': mobile_number,
                    'is_verified':  False,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class ProfileView(APIView):
    """
    GET  /api/users/profile/  — returns the authenticated user's profile
    PATCH /api/users/profile/ — updates first_name, last_name, monthly_savings_goal
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def _get_or_create_profile(self, user):
        profile, _ = UserProfile.objects.get_or_create(user=user)
        return profile

    def get(self, request):
        user = request.user
        profile = self._get_or_create_profile(user)
        serializer = ProfileSerializer(
            {'user': user, 'profile': profile}
        )
        return Response(serializer.data)

    def patch(self, request):
        user = request.user
        profile = self._get_or_create_profile(user)

        data = request.data
        print(f"DEBUG: Profile update for {user.email}")
        print(f"DEBUG: Received data keys: {list(data.keys())}")
        print(f"DEBUG: Received files: {list(request.FILES.keys())}")

        # Update user fields
        if 'first_name' in data:
            user.first_name = data['first_name']
        if 'last_name' in data:
            user.last_name = data['last_name']
        if 'email' in data:
            new_email = data['email'].strip().lower()
            # Only update if different; skip if already taken by another user
            if new_email and new_email != user.email:
                if User.objects.filter(email__iexact=new_email).exclude(pk=user.pk).exists():
                    return Response(
                        {'error': 'Email already in use by another account.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                user.email = new_email
        user.save()

        # Update profile fields
        if 'monthly_savings_goal' in data:
            try:
                profile.monthly_savings_goal = Decimal(str(data['monthly_savings_goal']))
            except Exception:
                return Response(
                    {'error': 'Invalid savings goal value.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if 'phone_number' in data:
            profile.phone_number = data['phone_number']
        if 'avatar' in request.FILES:
            profile.avatar = request.FILES['avatar']
        profile.save()

        serializer = ProfileSerializer({'user': user, 'profile': profile})
        return Response(serializer.data)


class DeleteAccountView(APIView):
    """
    DELETE /api/auth/delete-account/
    Body: { "password": "<current password>" }

    Permanently deletes the authenticated user and ALL associated data
    (transactions, budgets, notifications, profile, etc.).
    Requires password confirmation.
    """
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request):
        user = request.user
        password = request.data.get('password', '')

        if not password:
            return Response(
                {'error': 'Password is required to delete your account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from django.contrib.auth import authenticate
        authenticated = authenticate(request, email=user.email, password=password)
        if authenticated is None:
            return Response(
                {'error': 'Incorrect password. Please try again.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Django CASCADE handles all related data automatically via FK
        user.delete()
        return Response(
            {'message': 'Your account and all associated data have been permanently deleted.'},
            status=status.HTTP_200_OK,
        )


# ── OTP & Email Verification ──────────────────────────────────────────────────

class SendOTPView(APIView):
    """
    POST /api/auth/send-otp/
    Body: { "email": "..." }
    """
    def post(self, request):
        email = request.data.get('email', '').lower().strip()
        if not email:
            return Response({'error': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email__iexact=email)
            profile, _ = UserProfile.objects.get_or_create(user=user)
            
            # Generate 6-digit OTP
            otp = ''.join(random.choices(string.digits, k=6))
            profile.otp_code = otp
            profile.otp_expiry = timezone.now() + timedelta(minutes=10)
            profile.save()

            # Send email
            send_otp_email(user, otp, 'verification')

            return Response({'message': 'OTP sent successfully.'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'No account found with this email.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VerifyEmailOTPView(APIView):
    """
    POST /api/auth/verify-email-otp/
    Body: { "email": "...", "otp": "..." }
    """
    def post(self, request):
        email = request.data.get('email', '').lower().strip()
        otp = request.data.get('otp', '').strip()

        if not email or not otp:
            return Response({'error': 'Email and OTP are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email__iexact=email)
            profile = user.profile
            
            if profile.otp_code == otp and profile.otp_expiry > timezone.now():
                user.is_verified = True
                user.save()
                profile.otp_code = None # Clear OTP
                profile.save()
                return Response({'message': 'Email verified successfully.'}, status=status.HTTP_200_OK)
            else:
                return Response({'error': 'Invalid or expired OTP.'}, status=status.HTTP_400_BAD_REQUEST)
        except (User.DoesNotExist, UserProfile.DoesNotExist):
            return Response({'error': 'Invalid request.'}, status=status.HTTP_400_BAD_REQUEST)


class ForgotPasswordView(APIView):
    """
    POST /api/auth/forgot-password/
    Body: { "email": "..." }
    """
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        try:
            user = User.objects.get(email__iexact=email)
            profile, _ = UserProfile.objects.get_or_create(user=user)
            
            otp = ''.join(random.choices(string.digits, k=6))
            profile.otp_code = otp
            profile.otp_expiry = timezone.now() + timedelta(minutes=15)
            profile.save()

            send_otp_email(user, otp, 'password_reset')
            return Response({'message': 'Reset code sent to your email.'})
        except User.DoesNotExist:
            # For security, don't confirm if user exists or not
            return Response({'message': 'Reset code sent to your email.'})


class ResetPasswordView(APIView):
    """
    POST /api/auth/reset-password/
    Body: { "email": "...", "otp": "...", "new_password": "..." }
    """
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        otp = request.data.get('otp', '').strip()
        new_password = request.data.get('new_password', '')

        if not new_password:
            return Response({'error': 'New password is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email__iexact=email)
            profile = user.profile
            
            if profile.otp_code == otp and profile.otp_expiry > timezone.now():
                user.set_password(new_password)
                user.save()
                profile.otp_code = None
                profile.save()
                return Response({'message': 'Password has been reset successfully.'})
            else:
                return Response({'error': 'Invalid or expired OTP.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({'error': 'Something went wrong.'}, status=status.HTTP_400_BAD_REQUEST)
