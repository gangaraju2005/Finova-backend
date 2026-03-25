from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

def send_otp_email(user, otp, email_type='verification'):
    """
    Sends a branded HTML email with an OTP.
    
    :param user: CustomUser instance
    :param otp: The 6-digit code
    :param email_type: 'verification' or 'password_reset'
    """
    profile = getattr(user, 'profile', None)
    display_name = profile.username if profile and profile.username else user.first_name or 'User'
    
    if email_type == 'verification':
        subject = 'Finovo - Verify Your Email'
        template = 'emails/verify_email.html'
        title = "Email Verification"
        preheader = "Verify your email to getting started with Finovo."
    else:
        subject = 'Finovo - Reset Your Password'
        template = 'emails/forgot_password.html'
        title = "Password Reset"
        preheader = "Reset your Finovo password safely."

    context = {
        'display_name': display_name,
        'otp': otp,
        'title': title,
    }

    # Render HTML content
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
        <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
        <title>{subject}</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
            body {{
                background-color: #f6f9fc;
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                margin: 0;
                padding: 0;
                -webkit-font-smoothing: antialiased;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                padding: 40px 20px;
            }}
            .header {{
                text-align: center;
                padding-bottom: 30px;
            }}
            .logo {{
                font-size: 28px;
                font-weight: 800;
                color: #2D3142;
                letter-spacing: -1px;
                margin: 0;
            }}
            .card {{
                background-color: #ffffff;
                border-radius: 20px;
                padding: 40px;
                box-shadow: 0 10px 25px rgba(0,0,0,0.05);
            }}
            h1 {{
                font-size: 22px;
                font-weight: 700;
                color: #2D3142;
                margin: 0 0 16px;
                text-align: center;
            }}
            p {{
                font-size: 16px;
                line-height: 24px;
                color: #4C5C68;
                margin: 0 0 24px;
                text-align: center;
            }}
            .otp-container {{
                background-color: #F8F9FA;
                border: 2px dashed #E9ECEF;
                border-radius: 12px;
                padding: 24px;
                margin: 20px 0;
                text-align: center;
            }}
            .otp-code {{
                font-size: 36px;
                font-weight: 800;
                color: #000000;
                letter-spacing: 8px;
                margin-left: 8px;
            }}
            .footer {{
                text-align: center;
                margin-top: 30px;
                color: #9BA4AC;
                font-size: 13px;
            }}
            .highlight {{
                color: #FFB347;
                font-weight: 600;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2 class="logo">Finovo</h2>
            </div>
            <div class="card">
                <h1>{title}</h1>
                <p>Hello <strong>{display_name}</strong>,</p>
                {"<p>Welcome to Finovo! Use the code below to verify your email address and unlock all features.</p>" if email_type == 'verification' else "<p>We received a request to reset your password. Use the secure code below to continue.</p>"}
                
                <div class="otp-container">
                    <div class="otp-code">{otp}</div>
                </div>
                
                <p>This code will expire in <strong>15 minutes</strong>. If you didn't request this, you can safely ignore this email.</p>
                
                <p style="margin-top: 32px; font-size: 14px; opacity: 0.8;">
                    Happy saving,<br/>
                    <strong>The Finovo Team</strong>
                </p>
            </div>
            <div class="footer">
                &copy; 2024 Finovo - Your Minimalist Financial Companion
            </div>
        </div>
    </body>
    </html>
    """
    
    text_content = strip_tags(html_content)
    
    msg = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, [user.email])
    msg.attach_alternative(html_content, "text/html")
    msg.send()
