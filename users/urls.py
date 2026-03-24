from django.urls import path
from .views import (
    LoginView, RegisterView, ProfileView, DeleteAccountView,
    SendOTPView, VerifyEmailOTPView, ForgotPasswordView, ResetPasswordView
)

urlpatterns = [
    path('login/',            LoginView.as_view(),          name='auth-login'),
    path('register/',         RegisterView.as_view(),       name='auth-register'),
    path('profile/',          ProfileView.as_view(),        name='user-profile'),
    path('delete-account/',   DeleteAccountView.as_view(),  name='delete-account'),
    
    # OTP & Password Reset
    path('send-otp/',         SendOTPView.as_view(),        name='send-otp'),
    path('verify-email-otp/', VerifyEmailOTPView.as_view(), name='verify-email-otp'),
    path('forgot-password/',  ForgotPasswordView.as_view(), name='forgot-password'),
    path('reset-password/',   ResetPasswordView.as_view(),  name='reset-password'),
]
