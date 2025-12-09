"""
Email Service for OTP Verification - Resend Only
Simplified for production use with Resend API
"""
import os
from datetime import datetime

# Import Resend (required)
try:
    import resend
    RESEND_AVAILABLE = True
except ImportError:
    RESEND_AVAILABLE = False
    print("❌ CRITICAL: Resend not installed. Run: pip install resend")

# Email configuration
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")

async def send_otp_email(
    email: str, 
    otp_code: str, 
    purpose: str,
    expires_minutes: int = 10
) -> bool:
    """
    Send OTP email using Resend API ONLY
    
    Args:
        email: Recipient email
        otp_code: 6-digit OTP code
        purpose: "register" or "login"
        expires_minutes: OTP expiry time (default 10 minutes)
        
    Returns:
        bool: True if sent successfully, False otherwise
    """
    # Validation checks
    if not RESEND_API_KEY:
        print("❌ RESEND_API_KEY not configured in environment")
        return False
    
    if not RESEND_AVAILABLE:
        print("❌ Resend package not installed")
        return False
    
    try:
        print(f"📧 Sending OTP via Resend to {email}...")
        return await send_otp_resend(email, otp_code, purpose, expires_minutes)
    except Exception as e:
        print(f"❌ Email sending error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def send_otp_resend(
    email: str,
    otp_code: str,
    purpose: str,
    expires_minutes: int = 10
) -> bool:
    """
    Send OTP via Resend API
    Uses HTTPS (port 443) - works on Render Free Tier
    """
    try:
        resend.api_key = RESEND_API_KEY
        
        subject = get_email_subject(purpose)
        html = get_email_html(otp_code, purpose, expires_minutes)
        
        # Send via Resend
        params = {
            "from": EMAIL_FROM,
            "to": [email],
            "subject": subject,
            "html": html,
        }
        
        response = resend.Emails.send(params)
        print(f"✅ Resend response: {response}")
        return True
        
    except Exception as e:
        print(f"❌ Resend error: {e}")
        import traceback
        traceback.print_exc()
        return False

def get_email_subject(purpose: str) -> str:
    """Get email subject based on purpose"""
    if purpose == "register":
        return "Xác thực tài khoản - Mã OTP"
    elif purpose == "login":
        return "Đăng nhập - Mã OTP"
    else:
        return "Mã xác thực OTP"

def get_email_html(otp_code: str, purpose: str, expires_minutes: int) -> str:
    """Generate HTML email content"""
    
    if purpose == "register":
        title = "Xác thực tài khoản"
        description = "Bạn đang tạo tài khoản mới. Vui lòng sử dụng mã OTP bên dưới để hoàn tất đăng ký:"
    else:
        title = "Đăng nhập tài khoản"
        description = "Bạn đang đăng nhập vào tài khoản. Vui lòng sử dụng mã OTP bên dưới:"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f9f9f9;
            }}
            .container {{
                background-color: white;
                padding: 40px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            .header {{
                text-align: center;
                margin-bottom: 30px;
            }}
            .logo {{
                font-size: 24px;
                font-weight: bold;
                color: #007AFF;
                margin-bottom: 10px;
            }}
            .title {{
                font-size: 24px;
                font-weight: bold;
                margin-bottom: 20px;
                color: #333;
            }}
            .otp-container {{
                text-align: center;
                margin: 30px 0;
                padding: 30px;
                background-color: #f8f9fa;
                border-radius: 8px;
                border: 2px dashed #007AFF;
            }}
            .otp-code {{
                font-size: 36px;
                font-weight: bold;
                color: #007AFF;
                letter-spacing: 8px;
                margin: 10px 0;
                font-family: 'Courier New', monospace;
            }}
            .otp-label {{
                font-size: 14px;
                color: #666;
                margin-bottom: 10px;
            }}
            .warning {{
                background-color: #fff3cd;
                border: 1px solid #ffeaa7;
                border-radius: 5px;
                padding: 15px;
                margin: 20px 0;
                color: #856404;
            }}
            .footer {{
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #eee;
                font-size: 12px;
                color: #666;
                text-align: center;
            }}
            .security-tips {{
                margin-top: 20px;
                padding: 15px;
                background-color: #e9ecef;
                border-radius: 5px;
                font-size: 14px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">🍳 App Cook</div>
                <h1 class="title">{title}</h1>
            </div>
            
            <p>Xin chào,</p>
            <p>{description}</p>
            
            <div class="otp-container">
                <div class="otp-label">Mã xác thực OTP của bạn:</div>
                <div class="otp-code">{otp_code}</div>
                <div style="font-size: 14px; color: #666;">
                    Mã có hiệu lực trong {expires_minutes} phút
                </div>
            </div>
            
            <div class="warning">
                <strong>⚠️ Lưu ý bảo mật:</strong>
                <ul style="margin: 10px 0; padding-left: 20px;">
                    <li>Không chia sẻ mã này với bất kỳ ai</li>
                    <li>Mã chỉ có hiệu lực trong {expires_minutes} phút</li>
                    <li>Nếu bạn không yêu cầu mã này, vui lòng bỏ qua email</li>
                </ul>
            </div>
            
            <div class="security-tips">
                <strong>💡 Mẹo bảo mật:</strong><br>
                App Cook sẽ không bao giờ yêu cầu bạn cung cấp mã OTP qua điện thoại hoặc email khác.
                Chỉ nhập mã này trên ứng dụng chính thức của chúng tôi.
            </div>
            
            <div class="footer">
                <p>Email này được gửi tự động từ hệ thống App Cook</p>
                <p>Thời gian: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
                <p>Nếu bạn cần hỗ trợ, vui lòng liên hệ: support@appcook.com</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html