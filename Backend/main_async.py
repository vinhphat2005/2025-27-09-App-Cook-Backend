import os
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from fastapi.responses import JSONResponse

import firebase_admin
from firebase_admin import auth as fb_auth, credentials
from datetime import datetime, timezone
import motor.motor_asyncio
import logging
from bson import ObjectId

load_dotenv()

# ==== Init Firebase Admin ====
if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {
        "projectId": os.getenv("FIREBASE_PROJECT_ID")
    })

# ==== Init MongoDB (ASYNC ONLY) ====
MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DATABASE_NAME", "cook_app")

# ASYNC MongoDB client (Motor)
client = motor.motor_asyncio.AsyncIOMotorClient(
    MONGODB_URI,
    tls=True,
    serverSelectionTimeoutMS=30000,
)

db = client[DB_NAME]

# ASYNC collections
users_col = db["users"]
user_social_col = db["user_social"]
user_activity_col = db["user_activity"]
user_notifications_col = db["user_notifications"]
user_preferences_col = db["user_preferences"]

# ==== FastAPI app ====
app = FastAPI()

# Include các routers từ routes
from routes import user_route, dish_route, recipe_route, search_route,comment_route
from routes.comment_route import ensure_indexes as ensure_comment_indexes
from utils.recipe_handlers import ensure_recipe_indexes
from core.auth.dependencies import get_current_user
app.include_router(comment_route.router)
app.include_router(user_route.router, prefix="/users", tags=["Users"])
app.include_router(dish_route.router, prefix="/dishes", tags=["Dishes"])
app.include_router(recipe_route.router, prefix="/recipes", tags=["Recipes"])
app.include_router(search_route.router, prefix="/search", tags=["Search"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:19006",  # Expo web
        "exp://localhost:19000",   # Expo dev client
        "http://localhost:3000",
        "http://localhost:8000"   
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==== Startup: Create indexes for performance ====
@app.on_event("startup")
async def create_indexes():
    """
    Create MongoDB indexes on startup for optimal performance
    ✅ Ensures queries are fast and data integrity
    """
    try:
        # Users collection indexes
        await users_col.create_index("email", unique=True)
        await users_col.create_index("display_id", unique=True, sparse=True)
        await users_col.create_index("firebase_uid")
        
        # User-related collections indexes (all use ObjectId for user_id)
        await user_social_col.create_index("user_id", unique=True)
        await user_activity_col.create_index("user_id", unique=True)
        await user_notifications_col.create_index("user_id", unique=True)
        await user_preferences_col.create_index("user_id", unique=True)
        
        # Comments collection indexes
        await ensure_comment_indexes()
        
        # Recipe collection indexes
        await ensure_recipe_indexes()
        
        logger.info("✅ MongoDB indexes created successfully")
    except Exception as e:
        logger.warning(f"⚠️ Index creation failed (may already exist): {e}")

# ==== ASYNC Helper: ensure user exists in Mongo ====
async def ensure_user_document_async(decoded: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure user exists in MongoDB, create if not exists.
    Uses upsert to prevent race conditions.
    Returns user document with ObjectId.
    """
    uid = decoded["uid"]
    email = decoded.get("email", "")
    name = decoded.get("name", "")
    avatar = decoded.get("picture", "")
    
    display_id = email.split('@')[0] if email else f"user_{uid[:8]}"
    now = datetime.now(timezone.utc)
    
    # ✅ FIX: Dùng upsert để tránh race condition
    result = await users_col.update_one(
        {"email": email},
        {
            "$setOnInsert": {
                "email": email,
                "display_id": display_id,
                "name": name,
                "avatar": avatar,
                "bio": "",
                "createdAt": now,
                "firebase_uid": uid,
            },
            "$set": {"lastLoginAt": now}
        },
        upsert=True
    )
    
    # Lấy user document
    user = await users_col.find_one({"email": email})
    
    # Nếu user mới được tạo, init collections phụ
    if result.upserted_id:
        await init_user_collections_async(user["_id"])
    
    return user

async def init_user_collections_async(user_id: ObjectId):
    """
    Khởi tạo các collections phụ cho user mới (ASYNC)
    
    """
    # Tạo social data
    await user_social_col.insert_one({
        "user_id": user_id,  
        "followers": [],
        "following": [],
        "follower_count": 0,
        "following_count": 0
    })
    
    # Tạo activity data
    await user_activity_col.insert_one({
        "user_id": user_id,  
        "favorite_dishes": [],
        "cooked_dishes": [],
        "viewed_dishes": [],
        "created_recipes": [],
        "created_dishes": []
    })
    
    # Tạo notifications data
    await user_notifications_col.insert_one({
        "user_id": user_id, 
        "notifications": [],
        "unread_count": 0
    })
    
    # Tạo preferences data
    await user_preferences_col.insert_one({
        "user_id": user_id,  
        "reminders": [],
        "dietary_restrictions": [],
        "cuisine_preferences": [],
        "difficulty_preference": "all"
    })


# ==== Logging middleware ====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response: {response.status_code}")
    return response

# ==== Routes (ALL ASYNC) ====

@app.get("/health")
async def health():
    """Health check with MongoDB connectivity test"""
    try:
        # Ping MongoDB to check connection
        await client.admin.command('ping')
        return {"ok": True, "async": True, "db": "connected"}
    except Exception as e:
        return {"ok": False, "async": True, "db": "disconnected", "error": str(e)}

@app.get("/me")
async def me(decoded=Depends(get_current_user)):
    """
    Trả về hồ sơ user trong Mongo (và auto tạo nếu chưa có) - ASYNC VERSION

    """
    doc = await ensure_user_document_async(decoded)
    user_id = doc["_id"]  
    
    # Import user_helper nếu chưa có
    from core.user_management.service import user_helper
    
    # Load additional data từ các collections riêng 
    social_data = await user_social_col.find_one({"user_id": user_id})
    activity_data = await user_activity_col.find_one({"user_id": user_id})
    notifications_data = await user_notifications_col.find_one({"user_id": user_id})
    preferences_data = await user_preferences_col.find_one({"user_id": user_id})
    
    return {
        "user": user_helper(doc),
        "social": social_data or {"followers": [], "following": [], "follower_count": 0, "following_count": 0},
        "activity": activity_data or {"favorite_dishes": [], "cooked_dishes": [], "viewed_dishes": []},
        "notifications": notifications_data or {"notifications": [], "unread_count": 0},
        "preferences": preferences_data or {"reminders": [], "dietary_restrictions": []},
        "firebase": {"uid": decoded["uid"], "email": decoded.get("email")}
    }

@app.get("/data/private")
async def private_data(decoded=Depends(get_current_user)):
    """
    Ví dụ 1 endpoint cần auth để lấy data theo uid - ASYNC VERSION
    """
    uid = decoded["uid"]
    # Ví dụ: lấy list đơn hàng của user theo uid (ASYNC)
    orders_cursor = db["orders"].find({"uid": uid}, {"_id": 0})
    orders = await orders_cursor.to_list(length=100)
    return {"uid": uid, "orders": orders}

@app.post("/profile/update")
async def update_profile(payload: Dict[str, Any], decoded=Depends(get_current_user)):
    """
    Update hồ sơ người dùng - chỉ update fields cần thiết - ASYNC VERSION
    
    """
    email = decoded.get("email")
    if not email:
        raise HTTPException(400, "No email in token")
    
    
    if "display_id" in payload:
        display_id = payload["display_id"]
        # Validate format: alphanumeric + underscore, 3-30 chars
        import re
        if not re.match(r'^[a-zA-Z0-9_]{3,30}$', display_id):
            raise HTTPException(400, "display_id must be 3-30 alphanumeric chars or underscores")
        
        # Check uniqueness
        existing = await users_col.find_one({"display_id": display_id, "email": {"$ne": email}})
        if existing:
            raise HTTPException(400, "display_id already taken")
    
    allowed = {k: v for k, v in payload.items() if k in ["name", "avatar", "display_id", "bio"]}
    if not allowed:
        raise HTTPException(400, "No valid fields")
    
    # ASYNC update
    await users_col.update_one({"email": email}, {"$set": allowed})
    return {"ok": True, "updated_fields": list(allowed.keys())}


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.exception("Unhandled error")  # vẫn log full stacktrace
    detail = str(exc) if os.getenv("DEBUG","False").lower() == "true" else "Internal server error"
    return JSONResponse(status_code=500, content={"detail": detail})


# ==== ASYNC Admin endpoints ====
@app.post("/admin/reorganize-user/{user_id}")
async def reorganize_single_user_async(user_id: str):
    """
    Migrate một user từ structure cũ sang structure mới - ASYNC VERSION
    
    """
    if not DEBUG:
        raise HTTPException(403, "Only available in debug mode")
    
    try:
      
        user_oid = ObjectId(user_id)
        
        # ASYNC find
        user = await users_col.find_one({"_id": user_oid})
        if not user:
            raise HTTPException(404, "User not found")
        
        # Migrate data từ user document sang các collections riêng
        
        # 1. Migrate social data (ASYNC)
        social_data = {
            "user_id": user_oid, 
            "followers": user.get("followers", []),
            "following": user.get("following", []),
            "follower_count": len(user.get("followers", [])),
            "following_count": len(user.get("following", []))
        }
        await user_social_col.update_one(
            {"user_id": user_oid},
            {"$set": social_data},
            upsert=True
        )
        
        # 2. Migrate activity data (ASYNC)
        activity_data = {
            "user_id": user_oid,  
            "favorite_dishes": user.get("favorite_dishes", []),
            "cooked_dishes": user.get("cooked_dishes", []),
            "viewed_dishes": user.get("viewed_dishes", []),
            "created_recipes": user.get("recipes", []),
            "created_dishes": user.get("liked_dishes", [])
        }
        await user_activity_col.update_one(
            {"user_id": user_oid},
            {"$set": activity_data},
            upsert=True
        )
        
        # 3. Migrate notifications data (ASYNC)
        notifications_data = {
            "user_id": user_oid, 
            "notifications": user.get("notifications", []),
            "unread_count": len([n for n in user.get("notifications", []) if isinstance(n, dict) and not n.get("read", True)])
        }
        await user_notifications_col.update_one(
            {"user_id": user_oid},
            {"$set": notifications_data},
            upsert=True
        )
        
        # 4. Create preferences data (ASYNC)
        preferences_data = {
            "user_id": user_oid,  
            "reminders": [],
            "dietary_restrictions": [],
            "cuisine_preferences": [],
            "difficulty_preference": "all"
        }
        await user_preferences_col.update_one(
            {"user_id": user_oid},
            {"$set": preferences_data},
            upsert=True
        )
        
        # 5. Clean up user document - chỉ giữ basic info (ASYNC)
        clean_user_doc = {
            "email": user.get("email", ""),
            "display_id": user.get("display_id", ""),
            "name": user.get("name", ""),
            "avatar": user.get("avatar", ""),
            "bio": user.get("bio", ""),
            "createdAt": user.get("createdAt", datetime.now(timezone.utc)),
            "lastLoginAt": user.get("lastLoginAt", datetime.now(timezone.utc)),
            "firebase_uid": user.get("firebase_uid", ""),
        }
        
        await users_col.replace_one({"_id": user_oid}, clean_user_doc)
        
        return {
            "message": f"Successfully migrated user {user_id} to new structure",
            "migrated_collections": ["user_social", "user_activity", "user_notifications", "user_preferences"],
            "cleaned_fields": ["followers", "following", "recipes", "liked_dishes", "favorite_dishes", "cooked_dishes", "viewed_dishes", "notifications"]
        }
        
    except Exception as e:
        raise HTTPException(400, f"Migration failed: {str(e)}")

@app.post("/admin/migrate-all-users")
async def migrate_all_users_async():
    """
    Migrate tất cả users sang structure mới - ASYNC VERSION
    
    """
    if not DEBUG:
        raise HTTPException(403, "Only available in debug mode")
    
    try:
        
        users_cursor = users_col.find({})
        users = await users_cursor.to_list(length=None)
        migrated_count = 0
        errors = []
        
        for user in users:
            try:
                user_oid = user["_id"] 
                
                # Check if already migrated (no old fields)
                if not any(field in user for field in ["followers", "following", "recipes", "favorite_dishes"]):
                    continue
                
                # ✅ COMPLETE MIGRATION LOGIC
                
                # 1. Migrate social data
                social_data = {
                    "user_id": user_oid,
                    "followers": user.get("followers", []),
                    "following": user.get("following", []),
                    "follower_count": len(user.get("followers", [])),
                    "following_count": len(user.get("following", []))
                }
                await user_social_col.update_one(
                    {"user_id": user_oid},
                    {"$set": social_data},
                    upsert=True
                )
                
                # 2. Migrate activity data
                activity_data = {
                    "user_id": user_oid, 
                    "favorite_dishes": user.get("favorite_dishes", []),
                    "cooked_dishes": user.get("cooked_dishes", []),
                    "viewed_dishes": user.get("viewed_dishes", []),
                    "created_recipes": user.get("recipes", []),
                    "created_dishes": user.get("liked_dishes", [])
                }
                await user_activity_col.update_one(
                    {"user_id": user_oid},
                    {"$set": activity_data},
                    upsert=True
                )
                
                # 3. Migrate notifications
                notifications_data = {
                    "user_id": user_oid,  
                    "notifications": user.get("notifications", []),
                    "unread_count": len([n for n in user.get("notifications", []) if isinstance(n, dict) and not n.get("read", True)])
                }
                await user_notifications_col.update_one(
                    {"user_id": user_oid},
                    {"$set": notifications_data},
                    upsert=True
                )
                
                # 4. Create preferences
                preferences_data = {
                    "user_id": user_oid,
                    "reminders": [],
                    "dietary_restrictions": [],
                    "cuisine_preferences": [],
                    "difficulty_preference": "all"
                }
                await user_preferences_col.update_one(
                    {"user_id": user_oid},
                    {"$set": preferences_data},
                    upsert=True
                )
                
                # 5. Clean up user document
                clean_user_doc = {
                    "email": user.get("email", ""),
                    "display_id": user.get("display_id", ""),
                    "name": user.get("name", ""),
                    "avatar": user.get("avatar", ""),
                    "bio": user.get("bio", ""),
                    "createdAt": user.get("createdAt", datetime.now(timezone.utc)),
                    "lastLoginAt": user.get("lastLoginAt", datetime.now(timezone.utc)),
                    "firebase_uid": user.get("firebase_uid", ""),
                }
                await users_col.replace_one({"_id": user_oid}, clean_user_doc)
                
                migrated_count += 1
                
            except Exception as e:
                errors.append(f"User {user.get('_id', 'unknown')}: {str(e)}")
        
        return {
            "message": f"Migration completed",
            "migrated_users": migrated_count,
            "total_users": len(users),
            "skipped": len(users) - migrated_count - len(errors),
            "errors": errors
        }
        
    except Exception as e:
        raise HTTPException(500, f"Bulk migration failed: {str(e)}")
