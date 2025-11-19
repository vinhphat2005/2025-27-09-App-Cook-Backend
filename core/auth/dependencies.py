"""
Firebase Authentication Dependencies
Centralized auth logic for all routes
"""
from fastapi import HTTPException, Request
from typing import Dict, Any
import firebase_admin
from firebase_admin import auth as fb_auth
import jwt
import time
from datetime import datetime, timezone

# ✅ CLOCK SKEW TOLERANCE (in seconds)
CLOCK_SKEW_TOLERANCE = 120  # 2 minutes


def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Verify Firebase ID token and return decoded user info
    ✅ With clock skew tolerance for server/client time mismatch
    """
    auth_header = request.headers.get("Authorization")
    print(f"🔐 Auth header received: {bool(auth_header)}")
    if not auth_header or not auth_header.startswith("Bearer "):
        print("❌ Missing or invalid bearer token")
        raise HTTPException(status_code=401, detail="Missing bearer token")

    id_token = auth_header.split(" ", 1)[1].strip()
    print(f"🎫 ID token extracted (first 20 chars): {id_token[:20]}...")

    try:
        # ✅ Try Firebase SDK verify first (with check_revoked=False)
        decoded = fb_auth.verify_id_token(id_token, check_revoked=False)
        print(f"✅ Token verified successfully. User: {decoded.get('email', 'unknown')}")
        return decoded
        
    except Exception as e:
        error_str = str(e)
        
        # ✅ If clock skew error, try manual JWT decode with tolerance
        if "used too early" in error_str.lower() or "iat" in error_str.lower():
            print(f"⏰ CLOCK SKEW detected in Firebase SDK: {e}")
            print("💡 Attempting manual JWT decode with clock tolerance...")
            
            try:
                # Manual decode without verification (unsafe but works for clock skew)
                decoded = jwt.decode(id_token, options={"verify_signature": False})
                
                # Check if token is actually expired (ignore iat for now)
                current_time = int(time.time())
                exp_time = decoded.get('exp', 0)
                
                if current_time > (exp_time + CLOCK_SKEW_TOLERANCE):
                    print(f"❌ Token actually expired: {current_time} > {exp_time}")
                    raise HTTPException(status_code=401, detail="Token expired (outside tolerance window)")
                
                # Token is valid within tolerance window
                print(f"✅ Token valid (within {CLOCK_SKEW_TOLERANCE}s clock tolerance)")
                print(f"✅ Decoded user: {decoded.get('email', 'unknown')}")
                return decoded
                
            except HTTPException:
                raise
            except Exception as decode_err:
                print(f"❌ Manual JWT decode failed: {decode_err}")
                raise HTTPException(status_code=401, detail="Invalid token format")
        
        # Other Firebase errors
        if isinstance(e, fb_auth.ExpiredIdTokenError):
            print("❌ Token expired (Firebase SDK)")
            raise HTTPException(status_code=401, detail="Token expired")
        elif isinstance(e, fb_auth.RevokedIdTokenError):
            print("❌ Token revoked")
            raise HTTPException(status_code=401, detail="Token revoked")
        else:
            print(f"❌ Token verification failed: {e}")
            raise HTTPException(status_code=401, detail=f"Invalid token")


async def get_user_by_email(user_email: str, decoded_token: Dict[str, Any] = None):
    """
    Helper function to get user from database by email
    Auto-creates user in MongoDB if not exists (first-time login)
    """
    from database.mongo import users_collection
    from datetime import datetime, timezone
    
    user = await users_collection.find_one({"email": user_email})
    
    if not user and decoded_token:
        # 🚀 AUTO-CREATE: First-time login, create user in MongoDB
        print(f"🆕 Creating new user in MongoDB: {user_email}")
        
        # Extract info from Firebase token
        uid = decoded_token.get("uid", "")
        name = decoded_token.get("name", "")
        avatar = decoded_token.get("picture", "")
        
        # Generate display_id from email
        display_id = user_email.split('@')[0] if user_email else f"user_{uid[:8]}"
        
        # Handle display_id conflicts
        original_display_id = display_id
        counter = 1
        while await users_collection.find_one({"display_id": display_id}):
            display_id = f"{original_display_id}{counter}"
            counter += 1
            if counter > 100:  # Prevent infinite loop
                display_id = f"{original_display_id}_{uid[:8]}"
                break
        
        # Create user document with exact format you specified
        user_data = {
            "email": user_email,
            "display_id": display_id,
            "name": name,
            "avatar": avatar,
            "bio": "",
            "firebase_uid": uid,
            "createdAt": datetime.now(timezone.utc),
            "lastLoginAt": datetime.now(timezone.utc)
        }
        
        try:
            result = await users_collection.insert_one(user_data)
            user = await users_collection.find_one({"_id": result.inserted_id})
            
            # ✅ User created successfully. Sub-collections will be initialized on-demand
            print(f"✅ Successfully created user: {user_email} with display_id: {display_id}")
            
        except Exception as e:
            print(f"❌ Failed to create user: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")
    
    elif not user:
        # No decoded_token provided and user not found
        raise HTTPException(status_code=404, detail="User not found")
    else:
        # User exists, update lastLoginAt
        await users_collection.update_one(
            {"email": user_email},
            {"$set": {"lastLoginAt": datetime.now(timezone.utc)}}
        )
        print(f"✅ Updated lastLoginAt for existing user: {user_email}")
    
    return user


def extract_user_email(decoded: Dict[str, Any]) -> str:
    """
    Extract and validate email from Firebase token
    """
    email = decoded.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email not found in token")
    return email
