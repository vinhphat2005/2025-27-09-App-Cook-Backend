"""
Firebase Authentication Dependencies
Centralized auth logic for all routes
"""
from fastapi import HTTPException, Request
from typing import Dict, Any
import firebase_admin
from firebase_admin import auth as fb_auth


def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Verify Firebase ID token and return decoded user info
    """
    auth_header = request.headers.get("Authorization")
    print(f"🔐 Auth header received: {bool(auth_header)}")
    if not auth_header or not auth_header.startswith("Bearer "):
        print("❌ Missing or invalid bearer token")
        raise HTTPException(status_code=401, detail="Missing bearer token")

    id_token = auth_header.split(" ", 1)[1].strip()
    print(f"🎫 ID token extracted (first 20 chars): {id_token[:20]}...")

    try:
        decoded = fb_auth.verify_id_token(id_token, check_revoked=True)
        print(f"✅ Token verified successfully. User: {decoded.get('email', 'unknown')}")
        return decoded
    except fb_auth.ExpiredIdTokenError:
        print("❌ Token expired")
        raise HTTPException(status_code=401, detail="Token expired")
    except fb_auth.RevokedIdTokenError:
        print("❌ Token revoked")
        raise HTTPException(status_code=401, detail="Token revoked")
    except Exception as e:
        print(f"❌ Token verification failed: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


async def get_user_by_email(user_email: str):
    """
    Helper function to get user from database by email
    """
    from database.mongo import users_collection
    
    user = await users_collection.find_one({"email": user_email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def extract_user_email(decoded: Dict[str, Any]) -> str:
    """
    Extract and validate email from Firebase token
    """
    email = decoded.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email not found in token")
    return email
