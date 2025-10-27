"""
OTP Email Verification Routes
Tích hợp vào backend FastAPI hiện tại
"""
from pydantic import BaseModel, EmailStr
from typing import Literal, Optional
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta
import random
import string
import json

from email_service import send_otp_email  # Service gửi email
from core.auth.dependencies import get_current_user

# Router cho OTP
otp_router = APIRouter(prefix="/api/otp", tags=["OTP"])

# Import redis_client from main_async (will be set during startup)
def get_redis_client():
    """Get Redis client from main_async"""
    from main_async import redis_client
    return redis_client

# ==================== PYDANTIC MODELS ====================

class OTPSendRequest(BaseModel):
    email: EmailStr
    purpose: Literal["register", "login"]

class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str
    otp_id: str

class OTPResendRequest(BaseModel):
    email: EmailStr
    otp_id: str

class OTPResponse(BaseModel):
    success: bool
    message: str
    otp_id: Optional[str] = None
    expires_in: Optional[int] = None

class OTPVerifyResponse(BaseModel):
    success: bool
    message: str
    firebase_token: Optional[str] = None

# ==================== CONSTANTS ====================

OTP_EXPIRY_MINUTES = 10
MAX_OTP_ATTEMPTS = 3
OTP_LENGTH = 6

# ==================== HELPER FUNCTIONS ====================

def generate_otp() -> str:
    """Generate 6-digit OTP"""
    return ''.join(random.choices(string.digits, k=OTP_LENGTH))

def generate_otp_id() -> str:
    """Generate unique OTP session ID"""
    timestamp = str(int(datetime.now().timestamp()))
    random_part = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"otp_{timestamp}_{random_part}"

async def validate_email_advanced(email: str) -> dict:
    """
    Advanced email validation
    Returns: {"valid": bool, "reason": str}
    """
    # Basic format validation đã được Pydantic EmailStr handle
    
    # Check disposable email domains
    disposable_domains = {
        "10minutemail.com", "tempmail.org", "guerrillamail.com",
        "mailinator.com", "yopmail.com", "temp-mail.org",
        "throwaway.email", "10minuteemail.com", "temp-mail.io"
    }
    
    domain = email.split('@')[1].lower()
    
    if domain in disposable_domains:
        return {"valid": False, "reason": "Email tạm thời không được phép"}
    
    # Check common typos
    domain_corrections = {
        "gmai.com": "gmail.com",
        "gmial.com": "gmail.com", 
        "gmail.co": "gmail.com",
        "yahooo.com": "yahoo.com",
        "hotmial.com": "hotmail.com",
    }
    
    if domain in domain_corrections:
        suggested = email.replace(domain, domain_corrections[domain])
        return {"valid": False, "reason": f"Có phải bạn muốn dùng {suggested}?"}
    
    return {"valid": True, "reason": ""}

async def store_otp_redis(otp_id: str, otp_data: dict) -> bool:
    """Store OTP data in Redis with expiry"""
    try:
        redis = get_redis_client()
        key = f"otp:{otp_id}"
        value = json.dumps(otp_data, default=str)
        expiry_seconds = OTP_EXPIRY_MINUTES * 60
        
        await redis.setex(key, expiry_seconds, value)
        return True
    except Exception as e:
        print(f"Redis store error: {e}")
        return False

async def get_otp_redis(otp_id: str) -> Optional[dict]:
    """Get OTP data from Redis"""
    try:
        redis = get_redis_client()
        key = f"otp:{otp_id}"
        value = await redis.get(key)
        if value:
            return json.loads(value)
        return None
    except Exception as e:
        print(f"Redis get error: {e}")
        return None

async def delete_otp_redis(otp_id: str) -> bool:
    """Delete OTP from Redis"""
    try:
        redis = get_redis_client()
        key = f"otp:{otp_id}"
        await redis.delete(key)
        return True
    except Exception as e:
        print(f"Redis delete error: {e}")
        return False

# ==================== RATE LIMITING ====================

async def check_rate_limit(email: str, action: str) -> bool:
    """
    Check rate limiting for OTP actions
    Returns True if allowed, False if rate limited
    """
    key = f"rate_limit:{action}:{email}"
    try:
        redis = get_redis_client()
        count = await redis.get(key)
        if count is None:
            # First request
            await redis.setex(key, 60, "1")  # 1 minute window
            return True
        
        current_count = int(count)
        if current_count >= 5:  # Max 5 requests per minute
            return False
        
        await redis.incr(key)
        return True
    except Exception as e:
        print(f"Rate limit check error: {e}")
        return True  # Allow on error

# ==================== OTP ROUTES ====================

@otp_router.post("/send", response_model=OTPResponse)
async def send_otp_email_route(request: OTPSendRequest):
    """
    Gửi OTP qua email
    """
    try:
        # Import here to avoid circular import
        from main_async import users_col
        
        # Rate limiting
        if not await check_rate_limit(request.email, "send_otp"):
            raise HTTPException(
                status_code=429, 
                detail="Quá nhiều yêu cầu. Vui lòng thử lại sau."
            )
        
        # Advanced email validation
        validation = await validate_email_advanced(request.email)
        if not validation["valid"]:
            raise HTTPException(status_code=400, detail=validation["reason"])
        
        # Check if user exists for register purpose
        if request.purpose == "register":
            existing_user = await users_col.find_one({"email": request.email})
            if existing_user:
                raise HTTPException(
                    status_code=400,
                    detail="Email đã được sử dụng. Vui lòng đăng nhập."
                )
        elif request.purpose == "login":
            # For login, user should exist
            existing_user = await users_col.find_one({"email": request.email})
            if not existing_user:
                raise HTTPException(
                    status_code=404,
                    detail="Tài khoản không tồn tại. Vui lòng đăng ký."
                )
        
        # Generate OTP and session ID
        otp_code = generate_otp()
        otp_id = generate_otp_id()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)
        
        # Store OTP data
        otp_data = {
            "otp": otp_code,
            "email": request.email,
            "purpose": request.purpose,
            "expires_at": expires_at.isoformat(),
            "attempts": 0,
            "max_attempts": MAX_OTP_ATTEMPTS,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        if not await store_otp_redis(otp_id, otp_data):
            raise HTTPException(
                status_code=500,
                detail="Không thể lưu OTP. Vui lòng thử lại."
            )
        
        # Send email
        email_sent = await send_otp_email(
            email=request.email,
            otp_code=otp_code,
            purpose=request.purpose,
            expires_minutes=OTP_EXPIRY_MINUTES
        )
        
        if not email_sent:
            # Clean up on email failure
            await delete_otp_redis(otp_id)
            raise HTTPException(
                status_code=500,
                detail="Không thể gửi email. Vui lòng thử lại."
            )
        
        return OTPResponse(
            success=True,
            message="OTP đã được gửi đến email của bạn",
            otp_id=otp_id,
            expires_in=OTP_EXPIRY_MINUTES * 60
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Send OTP error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Có lỗi xảy ra khi gửi OTP"
        )

@otp_router.post("/verify", response_model=OTPVerifyResponse)
async def verify_otp_route(request: OTPVerifyRequest):
    """
    Xác thực OTP
    """
    try:
        # Get OTP data
        otp_data = await get_otp_redis(request.otp_id)
        if not otp_data:
            raise HTTPException(
                status_code=400,
                detail="Mã OTP không tồn tại hoặc đã hết hạn"
            )
        
        # Check email match
        if otp_data["email"] != request.email:
            raise HTTPException(
                status_code=400,
                detail="Email không khớp với OTP"
            )
        
        # Check expiry
        expires_at = datetime.fromisoformat(otp_data["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            await delete_otp_redis(request.otp_id)
            raise HTTPException(
                status_code=400,
                detail="Mã OTP đã hết hạn"
            )
        
        # Check attempts
        if otp_data["attempts"] >= otp_data["max_attempts"]:
            await delete_otp_redis(request.otp_id)
            raise HTTPException(
                status_code=400,
                detail="Đã vượt quá số lần thử tối đa"
            )
        
        # Verify OTP
        if otp_data["otp"] != request.otp:
            # Increment attempts
            otp_data["attempts"] += 1
            await store_otp_redis(request.otp_id, otp_data)
            
            remaining = otp_data["max_attempts"] - otp_data["attempts"]
            if remaining <= 0:
                await delete_otp_redis(request.otp_id)
                raise HTTPException(
                    status_code=400,
                    detail="Mã OTP không đúng. Đã hết lượt thử."
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Mã OTP không đúng. Còn {remaining} lần thử"
                )
        
        # OTP verified successfully
        await delete_otp_redis(request.otp_id)
        
        # For register purpose, we'll return success and let frontend create Firebase account
        # For login purpose, we could generate a custom Firebase token here
        
        firebase_token = None
        if otp_data["purpose"] == "login":
            # TODO: Generate Firebase custom token for passwordless login
            # This requires Firebase Admin SDK setup
            firebase_token = "custom_token_placeholder"
        
        return OTPVerifyResponse(
            success=True,
            message="Xác thực OTP thành công",
            firebase_token=firebase_token
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Verify OTP error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Có lỗi xảy ra khi xác thực OTP"
        )

@otp_router.post("/resend", response_model=OTPResponse)
async def resend_otp_route(request: OTPResendRequest):
    """
    Gửi lại OTP
    """
    try:
        # Rate limiting
        if not await check_rate_limit(request.email, "resend_otp"):
            raise HTTPException(
                status_code=429,
                detail="Quá nhiều yêu cầu. Vui lòng thử lại sau."
            )
        
        # Get existing OTP data
        otp_data = await get_otp_redis(request.otp_id)
        if not otp_data:
            raise HTTPException(
                status_code=400,
                detail="Phiên OTP không tồn tại. Vui lòng yêu cầu OTP mới."
            )
        
        # Check email match
        if otp_data["email"] != request.email:
            raise HTTPException(
                status_code=400,
                detail="Email không khớp với phiên OTP"
            )
        
        # Generate new OTP
        new_otp = generate_otp()
        new_expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)
        
        # Update OTP data
        otp_data.update({
            "otp": new_otp,
            "expires_at": new_expires_at.isoformat(),
            "attempts": 0,  # Reset attempts
            "resent_at": datetime.now(timezone.utc).isoformat()
        })
        
        # Store updated data
        if not await store_otp_redis(request.otp_id, otp_data):
            raise HTTPException(
                status_code=500,
                detail="Không thể cập nhật OTP. Vui lòng thử lại."
            )
        
        # Send new email
        email_sent = await send_otp_email(
            email=request.email,
            otp_code=new_otp,
            purpose=otp_data["purpose"],
            expires_minutes=OTP_EXPIRY_MINUTES
        )
        
        if not email_sent:
            raise HTTPException(
                status_code=500,
                detail="Không thể gửi email. Vui lòng thử lại."
            )
        
        return OTPResponse(
            success=True,
            message="OTP mới đã được gửi",
            otp_id=request.otp_id,
            expires_in=OTP_EXPIRY_MINUTES * 60
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Resend OTP error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Có lỗi xảy ra khi gửi lại OTP"
        )

# ==================== HEALTH CHECK ====================

@otp_router.get("/health")
async def otp_health_check():
    """Health check cho OTP service"""
    try:
        # Test Redis connection
        redis = get_redis_client()
        await redis.ping()
        redis_status = "connected"
    except:
        redis_status = "disconnected"
    
    return {
        "service": "OTP Email Verification",
        "status": "healthy",
        "redis": redis_status,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@otp_router.get("/debug/{otp_id}")
async def debug_otp(otp_id: str):
    """Debug endpoint - kiểm tra OTP có tồn tại không"""
    try:
        otp_data = await get_otp_redis(otp_id)
        if otp_data:
            # Ẩn OTP code thật để bảo mật
            debug_data = otp_data.copy()
            debug_data["otp"] = "***HIDDEN***"
            return {
                "found": True,
                "data": debug_data
            }
        else:
            return {
                "found": False,
                "message": "OTP không tồn tại hoặc đã hết hạn"
            }
    except Exception as e:
        return {
            "error": str(e)
        }