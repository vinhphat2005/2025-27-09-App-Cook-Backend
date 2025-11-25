"""
OTP Authentication Routes - New Flow
1. Login: email + password → verify credentials → send OTP → verify OTP → login success
2. Register: check email exists → send OTP → verify OTP → create account
"""
from pydantic import BaseModel, EmailStr
from typing import Literal, Optional
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta
import random
import string
import json
from firebase_admin import auth as fb_auth
from firebase_admin.auth import UserNotFoundError
import bcrypt

from email_service import send_otp_email

# Router cho OTP Authentication
auth_router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Import functions will be defined dynamically to avoid circular imports
def get_redis_client():
    """Get Redis client from main_async"""
    from main_async import redis_client
    return redis_client

def get_users_col():
    """Get users collection from main_async"""
    from main_async import users_col
    return users_col

# ==================== PYDANTIC MODELS ====================

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginOTPRequest(BaseModel):
    email: EmailStr
    otp_code: str
    otp_id: str

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str = ""

class RegisterOTPRequest(BaseModel):
    email: EmailStr
    otp_code: str
    otp_id: str
    password: str
    name: str = ""

class OTPResponse(BaseModel):
    success: bool
    message: str
    otp_id: Optional[str] = None
    expires_in: Optional[int] = None
    requires_otp: Optional[bool] = None

class AuthResponse(BaseModel):
    success: bool
    message: str
    firebase_token: Optional[str] = None
    user_data: Optional[dict] = None

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
    return f"auth_{timestamp}_{random_part}"

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

async def check_email_exists_firebase(email: str) -> bool:
    """Check if email exists in Firebase Auth"""
    try:
        fb_auth.get_user_by_email(email)
        return True
    except UserNotFoundError:
        return False
    except Exception as e:
        print(f"Firebase check error: {e}")
        return False

async def check_email_exists_mongodb(email: str) -> bool:
    """Check if email exists in MongoDB"""
    try:
        users_col = get_users_col()
        user = await users_col.find_one({"email": email})
        return user is not None
    except Exception as e:
        print(f"MongoDB check error: {e}")
        return False

async def store_auth_session(session_id: str, session_data: dict) -> bool:
    """Store authentication session in Redis"""
    try:
        redis = get_redis_client()
        key = f"auth_session:{session_id}"
        value = json.dumps(session_data, default=str)
        expiry_seconds = OTP_EXPIRY_MINUTES * 60
        
        await redis.setex(key, expiry_seconds, value)
        return True
    except Exception as e:
        print(f"Redis store error: {e}")
        return False

async def get_auth_session(session_id: str) -> Optional[dict]:
    """Get authentication session from Redis"""
    try:
        redis = get_redis_client()
        key = f"auth_session:{session_id}"
        value = await redis.get(key)
        if value:
            return json.loads(value)
        return None
    except Exception as e:
        print(f"Redis get error: {e}")
        return None

async def delete_auth_session(session_id: str) -> bool:
    """Delete authentication session from Redis"""
    try:
        redis = get_redis_client()
        key = f"auth_session:{session_id}"
        await redis.delete(key)
        return True
    except Exception as e:
        print(f"Redis delete error: {e}")
        return False

async def check_rate_limit(email: str, action: str) -> bool:
    """Check rate limiting for authentication actions"""
    key = f"rate_limit:{action}:{email}"
    try:
        redis = get_redis_client()
        count = await redis.get(key)
        if count is None:
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

# ==================== AUTHENTICATION ROUTES ====================

@auth_router.post("/login", response_model=OTPResponse)
async def login_step1(request: LoginRequest):
    """
    Step 1: Verify email + password, then send OTP
    """
    try:
        # Rate limiting
        if not await check_rate_limit(request.email, "login"):
            raise HTTPException(
                status_code=429,
                detail="Quá nhiều lần thử đăng nhập. Vui lòng thử lại sau."
            )
        
        users_col = get_users_col()
        
        # Check if user exists in MongoDB
        user = await users_col.find_one({"email": request.email})
        if not user:
            raise HTTPException(
                status_code=404,
                detail="Tài khoản không tồn tại. Vui lòng đăng ký."
            )
        
        # Verify password
        stored_password_hash = user.get("password_hash")
        if not stored_password_hash or not verify_password(request.password, stored_password_hash):
            raise HTTPException(
                status_code=401,
                detail="Email hoặc mật khẩu không đúng."
            )
        
        # Generate OTP and session
        otp_code = generate_otp()
        session_id = generate_otp_id()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)
        
        # Store authentication session
        session_data = {
            "type": "login",
            "email": request.email,
            "user_id": str(user["_id"]),
            "otp": otp_code,
            "expires_at": expires_at.isoformat(),
            "attempts": 0,
            "max_attempts": MAX_OTP_ATTEMPTS,
            "verified": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        if not await store_auth_session(session_id, session_data):
            raise HTTPException(
                status_code=500,
                detail="Không thể tạo phiên đăng nhập. Vui lòng thử lại."
            )
        
        # Send OTP email
        email_sent = await send_otp_email(
            email=request.email,
            otp_code=otp_code,
            purpose="login",
            expires_minutes=OTP_EXPIRY_MINUTES
        )
        
        if not email_sent:
            await delete_auth_session(session_id)
            raise HTTPException(
                status_code=500,
                detail="Không thể gửi mã OTP. Vui lòng thử lại."
            )
        
        return OTPResponse(
            success=True,
            message="Mật khẩu chính xác. Mã OTP đã được gửi đến email của bạn.",
            otp_id=session_id,
            expires_in=OTP_EXPIRY_MINUTES * 60,
            requires_otp=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Login step 1 error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Có lỗi xảy ra khi đăng nhập"
        )

@auth_router.post("/login/verify-otp", response_model=AuthResponse)
async def login_step2(request: LoginOTPRequest):
    """
    Step 2: Verify OTP and complete login
    """
    try:
        # Get authentication session
        session_data = await get_auth_session(request.otp_id)
        if not session_data:
            raise HTTPException(
                status_code=400,
                detail="Phiên đăng nhập không tồn tại hoặc đã hết hạn"
            )
        
        # Verify session type and email
        if session_data["type"] != "login" or session_data["email"] != request.email:
            raise HTTPException(
                status_code=400,
                detail="Thông tin đăng nhập không hợp lệ"
            )
        
        # Check expiry
        expires_at = datetime.fromisoformat(session_data["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            await delete_auth_session(request.otp_id)
            raise HTTPException(
                status_code=400,
                detail="Mã OTP đã hết hạn. Vui lòng đăng nhập lại."
            )
        
        # Check attempts
        if session_data["attempts"] >= session_data["max_attempts"]:
            await delete_auth_session(request.otp_id)
            raise HTTPException(
                status_code=400,
                detail="Đã vượt quá số lần thử tối đa"
            )
        
        # Verify OTP
        if session_data["otp"] != request.otp_code:
            session_data["attempts"] += 1
            await store_auth_session(request.otp_id, session_data)
            
            remaining = session_data["max_attempts"] - session_data["attempts"]
            if remaining <= 0:
                await delete_auth_session(request.otp_id)
                raise HTTPException(
                    status_code=400,
                    detail="Mã OTP không đúng. Đã hết lượt thử."
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Mã OTP không đúng. Còn {remaining} lần thử"
                )
        
        # OTP verified successfully - create Firebase custom token
        users_col = get_users_col()
        user = await users_col.find_one({"email": request.email})
        
        if not user:
            raise HTTPException(status_code=404, detail="Người dùng không tồn tại")
        
        # Create Firebase custom token
        firebase_uid = user.get("firebase_uid")
        if not firebase_uid:
            # Create Firebase user if doesn't exist
            try:
                firebase_user_record = fb_auth.create_user(
                    email=request.email,
                    email_verified=True
                )
                firebase_uid = firebase_user_record.uid
                
                # Update user with Firebase UID
                await users_col.update_one(
                    {"_id": user["_id"]},
                    {"$set": {"firebase_uid": firebase_uid}}
                )
            except Exception as e:
                print(f"Firebase user creation error: {e}")
                raise HTTPException(
                    status_code=500,
                    detail="Không thể tạo phiên đăng nhập"
                )
        
        # Generate custom token
        try:
            print(f"[DEBUG] Creating custom token for firebase_uid: {firebase_uid}")
            custom_token = fb_auth.create_custom_token(firebase_uid)
            custom_token_str = custom_token.decode('utf-8')
            print(f"[DEBUG] Custom token created successfully")
        except Exception as e:
            print(f"Custom token creation error: {e}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail="Không thể tạo token đăng nhập"
            )
        
        # Update last login time
        await users_col.update_one(
            {"_id": user["_id"]},
            {"$set": {"lastLoginAt": datetime.now(timezone.utc)}}
        )
        
        # Clean up session
        await delete_auth_session(request.otp_id)
        
        # Prepare user data (exclude sensitive info)
        user_data = {
            "id": str(user["_id"]),
            "email": user["email"],
            "name": user.get("name", ""),
            "display_id": user.get("display_id", ""),
            "avatar": user.get("avatar", ""),
            "bio": user.get("bio", ""),
        }
        
        return AuthResponse(
            success=True,
            message="Đăng nhập thành công",
            firebase_token=custom_token_str,
            user_data=user_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Login step 2 error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Có lỗi xảy ra khi xác thực OTP"
        )

@auth_router.post("/register", response_model=OTPResponse)
async def register_step1(request: RegisterRequest):
    """
    Step 1: Check email availability and send OTP for registration
    """
    try:
        # Rate limiting
        if not await check_rate_limit(request.email, "register"):
            raise HTTPException(
                status_code=429,
                detail="Quá nhiều yêu cầu đăng ký. Vui lòng thử lại sau."
            )
        
        # Check if email exists in MongoDB
        if await check_email_exists_mongodb(request.email):
            raise HTTPException(
                status_code=400,
                detail="Email đã được sử dụng trong hệ thống. Vui lòng đăng nhập."
            )
        
        # Check if email exists in Firebase
        if await check_email_exists_firebase(request.email):
            raise HTTPException(
                status_code=400,
                detail="Email đã được đăng ký. Vui lòng đăng nhập."
            )
        
        # Generate OTP and session
        otp_code = generate_otp()
        session_id = generate_otp_id()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)
        
        # Store registration session
        session_data = {
            "type": "register",
            "email": request.email,
            "password": request.password,  # Will be hashed when creating user
            "name": request.name,
            "otp": otp_code,
            "expires_at": expires_at.isoformat(),
            "attempts": 0,
            "max_attempts": MAX_OTP_ATTEMPTS,
            "verified": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        if not await store_auth_session(session_id, session_data):
            raise HTTPException(
                status_code=500,
                detail="Không thể tạo phiên đăng ký. Vui lòng thử lại."
            )
        
        # Send OTP email
        email_sent = await send_otp_email(
            email=request.email,
            otp_code=otp_code,
            purpose="register",
            expires_minutes=OTP_EXPIRY_MINUTES
        )
        
        if not email_sent:
            await delete_auth_session(session_id)
            raise HTTPException(
                status_code=500,
                detail="Không thể gửi mã OTP. Vui lòng thử lại."
            )
        
        return OTPResponse(
            success=True,
            message="Email hợp lệ. Mã OTP đã được gửi đến email của bạn.",
            otp_id=session_id,
            expires_in=OTP_EXPIRY_MINUTES * 60,
            requires_otp=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Register step 1 error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Có lỗi xảy ra khi đăng ký"
        )

@auth_router.post("/register/verify-otp", response_model=AuthResponse)
async def register_step2(request: RegisterOTPRequest):
    """
    Step 2: Verify OTP and create account
    """
    try:
        # Get registration session
        session_data = await get_auth_session(request.otp_id)
        if not session_data:
            raise HTTPException(
                status_code=400,
                detail="Phiên đăng ký không tồn tại hoặc đã hết hạn"
            )
        
        # Verify session type and email
        if session_data["type"] != "register" or session_data["email"] != request.email:
            raise HTTPException(
                status_code=400,
                detail="Thông tin đăng ký không hợp lệ"
            )
        
        # Check expiry
        expires_at = datetime.fromisoformat(session_data["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            await delete_auth_session(request.otp_id)
            raise HTTPException(
                status_code=400,
                detail="Mã OTP đã hết hạn. Vui lòng đăng ký lại."
            )
        
        # Check attempts
        if session_data["attempts"] >= session_data["max_attempts"]:
            await delete_auth_session(request.otp_id)
            raise HTTPException(
                status_code=400,
                detail="Đã vượt quá số lần thử tối đa"
            )
        
        # Verify OTP
        if session_data["otp"] != request.otp_code:
            session_data["attempts"] += 1
            await store_auth_session(request.otp_id, session_data)
            
            remaining = session_data["max_attempts"] - session_data["attempts"]
            if remaining <= 0:
                await delete_auth_session(request.otp_id)
                raise HTTPException(
                    status_code=400,
                    detail="Mã OTP không đúng. Đã hết lượt thử."
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Mã OTP không đúng. Còn {remaining} lần thử"
                )
        
        # OTP verified - check email availability again (double check)
        if await check_email_exists_mongodb(request.email) or await check_email_exists_firebase(request.email):
            await delete_auth_session(request.otp_id)
            raise HTTPException(
                status_code=400,
                detail="Email đã được sử dụng trong lúc đăng ký. Vui lòng thử email khác."
            )
        
        # Create Firebase user
        try:
            firebase_user_record = fb_auth.create_user(
                email=request.email,
                password=request.password,
                email_verified=True,
                display_name=request.name or session_data.get("name", "")
            )
            firebase_uid = firebase_user_record.uid
        except Exception as e:
            print(f"Firebase user creation error: {e}")
            await delete_auth_session(request.otp_id)
            raise HTTPException(
                status_code=500,
                detail="Không thể tạo tài khoản Firebase"
            )
        
        # Create MongoDB user
        users_col = get_users_col()
        display_id = request.email.split('@')[0]
        password_hash = hash_password(request.password)
        
        new_user = {
            "email": request.email,
            "password_hash": password_hash,
            "name": request.name or session_data.get("name", ""),
            "display_id": display_id,
            "avatar": "",
            "bio": "",
            "firebase_uid": firebase_uid,
            "createdAt": datetime.now(timezone.utc),
            "lastLoginAt": datetime.now(timezone.utc)
        }
        
        try:
            result = await users_col.insert_one(new_user)
            user_id = str(result.inserted_id)
        except Exception as e:
            # If MongoDB creation fails, delete Firebase user
            try:
                fb_auth.delete_user(firebase_uid)
            except:
                pass
            print(f"MongoDB user creation error: {e}")
            await delete_auth_session(request.otp_id)
            raise HTTPException(
                status_code=500,
                detail="Không thể tạo tài khoản trong hệ thống"
            )
        
        # Create custom token for immediate login
        try:
            custom_token = fb_auth.create_custom_token(firebase_uid)
            custom_token_str = custom_token.decode('utf-8')
        except Exception as e:
            print(f"Custom token creation error: {e}")
            custom_token_str = None
        
        # Clean up session
        await delete_auth_session(request.otp_id)
        
        # Prepare user data
        user_data = {
            "id": user_id,
            "email": request.email,
            "name": request.name or session_data.get("name", ""),
            "display_id": display_id,
            "avatar": "",
            "bio": "",
        }
        
        return AuthResponse(
            success=True,
            message="Đăng ký thành công! Tài khoản của bạn đã được tạo.",
            firebase_token=custom_token_str,
            user_data=user_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Register step 2 error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Có lỗi xảy ra khi tạo tài khoản"
        )

# ==================== UTILITY ROUTES ====================

@auth_router.post("/check-email")
async def check_email_availability(request: dict):
    """Check if email is available for registration"""
    try:
        email = request.get("email")
        if not email:
            raise HTTPException(400, "Email is required")
        
        # Check both Firebase and MongoDB
        firebase_exists = await check_email_exists_firebase(email)
        mongodb_exists = await check_email_exists_mongodb(email)
        
        is_available = not (firebase_exists or mongodb_exists)
        
        if is_available:
            return {
                "available": True,
                "message": "Email có thể sử dụng để đăng ký"
            }
        else:
            return {
                "available": False,
                "message": "Email đã được sử dụng. Vui lòng đăng nhập hoặc sử dụng email khác."
            }
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Check email error: {e}")
        raise HTTPException(500, "Có lỗi xảy ra khi kiểm tra email")

@auth_router.post("/resend-otp")
async def resend_otp(request: dict):
    """Resend OTP for existing session"""
    try:
        session_id = request.get("otp_id")
        email = request.get("email")
        
        if not session_id or not email:
            raise HTTPException(400, "Thiếu thông tin session ID hoặc email")
        
        # Rate limiting
        if not await check_rate_limit(email, "resend_otp"):
            raise HTTPException(429, "Quá nhiều yêu cầu gửi lại OTP")
        
        # Get session
        session_data = await get_auth_session(session_id)
        if not session_data:
            raise HTTPException(400, "Phiên không tồn tại hoặc đã hết hạn")
        
        if session_data["email"] != email:
            raise HTTPException(400, "Email không khớp với phiên")
        
        # Generate new OTP
        new_otp = generate_otp()
        new_expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)
        
        session_data.update({
            "otp": new_otp,
            "expires_at": new_expires_at.isoformat(),
            "attempts": 0,  # Reset attempts
            "resent_at": datetime.now(timezone.utc).isoformat()
        })
        
        if not await store_auth_session(session_id, session_data):
            raise HTTPException(500, "Không thể cập nhật phiên")
        
        # Send new OTP
        email_sent = await send_otp_email(
            email=email,
            otp_code=new_otp,
            purpose=session_data["type"],
            expires_minutes=OTP_EXPIRY_MINUTES
        )
        
        if not email_sent:
            raise HTTPException(500, "Không thể gửi email")
        
        return OTPResponse(
            success=True,
            message="OTP mới đã được gửi",
            otp_id=session_id,
            expires_in=OTP_EXPIRY_MINUTES * 60
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Resend OTP error: {e}")
        raise HTTPException(500, "Có lỗi xảy ra khi gửi lại OTP")

@auth_router.get("/health")
async def auth_health_check():
    """Health check for authentication service"""
    try:
        redis = get_redis_client()
        await redis.ping()
        redis_status = "connected"
    except:
        redis_status = "disconnected"
    
    return {
        "service": "OTP Authentication",
        "status": "healthy",
        "redis": redis_status,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
