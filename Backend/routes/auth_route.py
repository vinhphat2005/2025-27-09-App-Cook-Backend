from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
from database.mongo import users_collection
import os

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Cấu hình JWT
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-here")  # Đổi trong production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    # Tìm user trong database
    user = await users_collection.find_one({"email": form_data.username})
    if not user:
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")
    
    # Kiểm tra mật khẩu
    if not pwd_context.verify(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")
    
    # Tạo access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["email"]}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {
            "email": user["email"],
            "display_id": user["display_id"],
            "id": str(user["_id"])
        }
    }

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
