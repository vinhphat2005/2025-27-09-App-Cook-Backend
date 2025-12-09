"""
Email Service for OTP Verification
Supports multiple email providers: Resend, SendGrid, SMTP
"""
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import os
from datetime import datetime

# Try to import Resend (preferred method)
try:
    import resend
    RESEND_AVAILABLE = True
except ImportError:
    RESEND_AVAILABLE = False
    print("⚠️ Resend not installed. Install with: pip install resend")

# Email configuration từ environment variables
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "smtp")  # "resend", "sendgrid", or "smtp"
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@appcook.com")

# SMTP configuration (fallback)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")

async def send_otp_email(
    email: str, 
    otp_code: str, 
    purpose: str,
    expires_minutes: int = 10
) -> bool:
    """
    Send OTP email using configured provider
    
    Priority order:
    1. Resend (if RESEND_API_KEY is set) - RECOMMENDED for production
    2. SendGrid (if EMAIL_PROVIDER=sendgrid)
    3. SMTP (fallback)
    
    Args:
        email: Recipient email
        otp_code: 6-digit OTP code
        purpose: "register" or "login"
        expires_minutes: OTP expiry time
        
    Returns:
        bool: True if sent successfully, False otherwise
    """
    try:
        # Priority 1: Try Resend first (works on Render!)
        if RESEND_API_KEY and RESEND_AVAILABLE:
            print("📧 Using Resend API...")
            return await send_otp_resend(email, otp_code, purpose, expires_minutes)
        
        # Priority 2: SendGrid
        elif EMAIL_PROVIDER == "sendgrid":
            print("📧 Using SendGrid API...")
            return await send_otp_sendgrid(email, otp_code, purpose, expires_minutes)
        
        # Priority 3: SMTP (may be blocked on Render Free Tier)
        else:
            print("📧 Using SMTP...")
            return await send_otp_smtp(email, otp_code, purpose, expires_minutes)
            
    except Exception as e:
        print(f"❌ Email sending error: {e}")
        return False

async def send_otp_sendgrid(
    email: str, 
    otp_code: str, 
    purpose: str,
    expires_minutes: int
) -> bool:
    """Send OTP via SendGrid"""
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail, To
        
        if not SENDGRID_API_KEY:
            print("❌ SendGrid API key not configured")
            return False
        
        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        
        subject = get_email_subject(purpose)
        html_content = get_email_html(otp_code, purpose, expires_minutes)
        
        message = Mail(
            from_email=EMAIL_FROM,
            to_emails=To(email),
            subject=subject,
            html_content=html_content
        )
        
        response = sg.send(message)
        print(f"✅ SendGrid response: {response.status_code}")
        return response.status_code == 202
        
    except Exception as e:
        print(f"❌ SendGrid error: {e}")
        return False

async def send_otp_resend(
    email: str,
    otp_code: str,
    purpose: str,
    expires_minutes: int = 10
) -> bool:
    """
    Send OTP via Resend API (RECOMMENDED for Render)
    
    Resend uses HTTPS API instead of SMTP, so it works on Render Free Tier!
    
    Setup:
    1. Sign up at https://resend.com/signup (Free 100 emails/day)
    2. Get API key from Dashboard
    3. Add to Render env: RESEND_API_KEY=re_xxxxxxxxxxxx
    4. Set EMAIL_FROM to your verified domain email (or use onboarding@resend.dev)
    """
    try:
        if not RESEND_API_KEY:
            print("❌ RESEND_API_KEY not configured")
            return False
        
        if not RESEND_AVAILABLE:
            print("❌ Resend package not installed. Run: pip install resend")
            return False
        
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
        print(f"✅ Resend email sent successfully: {response}")
        return True
        
    except Exception as e:
        print(f"❌ Resend error: {e}")
        return False

async def send_otp_smtp(
    email: str, 
    otp_code: str, 
    purpose: str,
    expires_minutes: int
) -> bool:
    """Send OTP via SMTP"""
    try:
        # Re-read environment variables (for runtime changes)
        smtp_user = os.getenv("SMTP_USER")
        smtp_pass = os.getenv("SMTP_PASS")
        
        if not smtp_user or not smtp_pass:
            # Development mode - just log the OTP
            print(f"\n{'='*50}")
            print(f"📧 OTP EMAIL (Development Mode)")
            print(f"To: {email}")
            print(f"Purpose: {purpose}")
            print(f"OTP Code: {otp_code}")
            print(f"Expires in: {expires_minutes} minutes")
            print(f"{'='*50}\n")
            return True
        
        # Production SMTP sending with beautiful HTML format
        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        email_from = os.getenv("EMAIL_FROM", "noreply@appcook.com")
        
        message = MIMEMultipart("alternative")
        message["Subject"] = get_email_subject(purpose)
        message["From"] = email_from
        message["To"] = email
        
        # Create both plain text and HTML content
        plain_content = get_email_plain_text(otp_code, purpose, expires_minutes)
        html_content = get_email_html(otp_code, purpose, expires_minutes)
        
        # Create plain text and HTML parts
        text_part = MIMEText(plain_content, "plain", "utf-8")
        html_part = MIMEText(html_content, "html", "utf-8")
        
        # Attach both parts
        message.attach(text_part)
        message.attach(html_part)
        
        # Create secure connection and send
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.sendmail(email_from, email, message.as_string())
        
        return True
        
    except Exception as e:
        print(f"SMTP error: {e}")
        return False

def get_email_subject(purpose: str) -> str:
    """Get email subject based on purpose"""
    if purpose == "register":
        return "Xác thực tài khoản - Mã OTP"
    elif purpose == "login":
        return "Đăng nhập - Mã OTP"
    else:
        return "Mã xác thực OTP"

def get_email_plain_text(otp_code: str, purpose: str, expires_minutes: int) -> str:
    """Generate plain text email content (to avoid Gmail interference)"""
    
    if purpose == "register":
        title = "XÁC THỰC TÀI KHOẢN"
        description = "Bạn đang tạo tài khoản mới. Vui lòng sử dụng mã OTP bên dưới để hoàn tất đăng ký:"
    else:
        title = "ĐĂNG NHẬP TÀI KHOẢN"
        description = "Bạn đang đăng nhập vào tài khoản. Vui lòng sử dụng mã OTP bên dưới:"
    
    plain_text = f"""
🍳 APP COOK
{title}

Xin chào,

{description}

===================================
     MÃ XÁC THỰC OTP CỦA BẠN:
           {otp_code}
===================================

Mã có hiệu lực trong {expires_minutes} phút

⚠️ LƯU Ý BẢO MẬT:
• Không chia sẻ mã này với bất kỳ ai
• Mã chỉ có hiệu lực trong {expires_minutes} phút  
• Nếu bạn không yêu cầu mã này, vui lòng bỏ qua email

💡 MẸO BẢO MẬT:
App Cook sẽ không bao giờ yêu cầu bạn cung cấp mã OTP 
qua điện thoại hoặc email khác. Chỉ nhập mã này trên 
ứng dụng chính thức của chúng tôi.

---
Email này được gửi tự động từ hệ thống App Cook
Thời gian: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
Hỗ trợ: support@appcook.com
"""
    
    return plain_text.strip()

def get_email_pure_text(otp_code: str, purpose: str, expires_minutes: int) -> str:
    """Generate PURE TEXT email content (no emojis, no special chars)"""
    
    if purpose == "register":
        title = "XAC THUC TAI KHOAN"
        description = "Ban dang tao tai khoan moi. Vui long su dung ma OTP ben duoi de hoan tat dang ky:"
    else:
        title = "DANG NHAP TAI KHOAN"  
        description = "Ban dang dang nhap vao tai khoan. Vui long su dung ma OTP ben duoi:"
    
    # PURE TEXT - no emojis, no special formatting
    pure_text = f"""App Cook - {title}

Xin chao,

{description}

Ma xac thuc OTP cua ban: {otp_code}

Ma co hieu luc trong {expires_minutes} phut.

LUU Y BAO MAT:
- Khong chia se ma nay voi bat ky ai
- Ma chi co hieu luc trong {expires_minutes} phut  
- Neu ban khong yeu cau ma nay, vui long bo qua email

MEO BAO MAT:
App Cook se khong bao gio yeu cau ban cung cap ma OTP 
qua dien thoai hoac email khac. Chi nhap ma nay tren 
ung dung chinh thuc cua chung toi.

---
Email nay duoc gui tu dong tu he thong App Cook
Thoi gian: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
Ho tro: support@appcook.com"""
    
    return pure_text.strip()

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

# Test function
async def test_email_service():
    """Test email service configuration"""
    test_email = "test@example.com"
    test_otp = "123456"
    
    print("Testing email service...")
    result = await send_otp_email(test_email, test_otp, "register", 10)
    print(f"Email test result: {result}")
    
    return result

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_email_service())