from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import credentials, auth
from functools import lru_cache
import os

# Chỉ khởi tạo Firebase Admin một lần
@lru_cache()
def init_firebase():
    if not firebase_admin._apps:  # Kiểm tra đã init chưa
        # Có thể dùng service account key file hoặc environment
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            cred = credentials.ApplicationDefault()
        else:
            cred = credentials.Certificate("path/to/serviceAccountKey.json")  
        firebase_admin.initialize_app(cred)

# Bảo vệ endpoint bằng Bearer token
security = HTTPBearer()

def verify_firebase_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    init_firebase()
    try:
        token = credentials.credentials
        # Thêm clock_skew_seconds để xử lý lệch thời gian
        decoded_token = auth.verify_id_token(
            token, 
            clock_skew_seconds=60  # Chấp nhận lệch 60 giây
        )
        return decoded_token  # chứa 'email', 'uid', v.v.
    except auth.InvalidIdTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Firebase token: {str(e)}"
        )
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase token has expired"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )