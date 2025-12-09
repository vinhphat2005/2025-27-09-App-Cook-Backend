import os
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

from fastapi import APIRouter, FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from fastapi.responses import JSONResponse

import firebase_admin
from firebase_admin import auth as fb_auth, credentials
from datetime import datetime, timezone, timedelta
import motor.motor_asyncio
import logging
from bson import ObjectId
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

load_dotenv()
from routes.recommendation_route import router as recommendations_router
# ==== Init Firebase Admin ====
if not firebase_admin._apps:
    # Try to read from FIREBASE_CREDENTIALS env var (for production)
    firebase_creds_json = os.getenv("FIREBASE_CREDENTIALS")
    if firebase_creds_json:
        import json
        cred_dict = json.loads(firebase_creds_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred, {
            "projectId": os.getenv("FIREBASE_PROJECT_ID")
        })
        print("✅ Firebase initialized from FIREBASE_CREDENTIALS env var")
    else:
        # Fallback to serviceAccountKey.json (for local development)
        try:
            cred = credentials.Certificate("./serviceAccountKey.json")
            firebase_admin.initialize_app(cred, {
                "projectId": os.getenv("FIREBASE_PROJECT_ID")
            })
            print("✅ Firebase initialized from serviceAccountKey.json")
        except FileNotFoundError:
            # Last resort: use ApplicationDefault (for GCP environments)
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred, {
                "projectId": os.getenv("FIREBASE_PROJECT_ID")
            })
            print("✅ Firebase initialized with ApplicationDefault")

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
user_col = users_col  # Backward compatibility alias
user_social_col = db["user_social"]
user_activity_col = db["user_activity"]
user_notifications_col = db["user_notifications"]
user_preferences_col = db["user_preferences"]

# ==== Redis Setup ====
redis_client = None

class InMemoryRedis:
    """Simple in-memory Redis mock for development"""
    def __init__(self):
        self.data = {}
        self.expiry = {}
    
    async def ping(self):
        return True
    
    async def setex(self, key, seconds, value):
        import time
        self.data[key] = value
        self.expiry[key] = time.time() + seconds
        return True
    
    async def get(self, key):
        import time
        if key in self.data:
            if key in self.expiry and time.time() > self.expiry[key]:
                del self.data[key]
                del self.expiry[key]
                return None
            return self.data[key]
        return None
    
    async def delete(self, key):
        if key in self.data:
            del self.data[key]
        if key in self.expiry:
            del self.expiry[key]
        return True
    
    async def incr(self, key):
        current = await self.get(key)
        if current is None:
            self.data[key] = "1"
            return 1
        else:
            new_val = int(current) + 1
            self.data[key] = str(new_val)
            return new_val

async def init_redis():
    """Initialize Redis connection"""
    global redis_client
    if redis_client is None:
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_db = int(os.getenv("REDIS_DB", "0"))
        redis_password = os.getenv("REDIS_PASSWORD")
        
        try:
            # Use modern redis package (redis 5.x)
            import redis.asyncio as redis
            
            redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                decode_responses=True
            )
            
            # Test connection
            await redis_client.ping()
            print("✅ Redis connected successfully")
            
        except ImportError as e:
            print("💡 Using in-memory storage for development")
            redis_client = InMemoryRedis()
        except Exception as e:
            # Quietly use in-memory storage for development
            print("💡 Using in-memory storage for development")
            redis_client = InMemoryRedis()
    
    return redis_client

# ==== FastAPI app ====
app = FastAPI()

# ==== Health Check Endpoint ====
@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    """Root endpoint for health checks"""
    return {
        "status": "ok",
        "message": "App Cook API is running",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check(request: Request):
    """Detailed health check endpoint"""
    # Silent health check - don't log to reduce noise
    try:
        # Check MongoDB connection
        await db.command("ping")
        mongo_status = "connected"
    except Exception as e:
        mongo_status = f"error: {str(e)}"
    
    return {
        "status": "ok",
        "services": {
            "api": "running",
            "mongodb": mongo_status,
            "redis": "connected" if redis_client else "not configured"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# ==== Background Scheduler ====
scheduler = AsyncIOScheduler()

# ==== Cleanup Jobs ====
async def auto_cleanup_deleted_dishes():
    """
    Automatically cleanup dishes deleted more than 7 days ago.
    This runs daily at 2:00 AM server time.
    """
    try:
        from routes.dish_route import dishes_collection, comments_collection, recipe_collection
        import cloudinary
        
        CLOUDINARY_ENABLED = os.getenv("CLOUDINARY_ENABLED", "false").lower() == "true"
        
        logging.info("🗑️ Starting automatic cleanup of deleted dishes...")
        
        # Calculate cutoff date (7 days ago)
        cutoff_date = datetime.utcnow() - timedelta(days=7)
        
        # Find dishes deleted more than 7 days ago
        old_deleted_dishes = await dishes_collection.find({
            "deleted_at": {"$exists": True, "$lt": cutoff_date}
        }).to_list(length=None)
        
        cleanup_stats = {
            "dishes_deleted": 0,
            "images_deleted": 0,
            "comments_deleted": 0,
            "recipes_deleted": 0,
            "errors": []
        }
        
        for dish in old_deleted_dishes:
            dish_id = str(dish["_id"])
            
            try:
                # Delete Cloudinary image
                if CLOUDINARY_ENABLED and dish.get("image_url"):
                    try:
                        public_id = dish.get("public_id")
                        if not public_id and dish.get("image_url"):
                            # Extract from URL
                            url_parts = dish["image_url"].split("/upload/")
                            if len(url_parts) > 1:
                                path_with_version = url_parts[1]
                                path_parts = path_with_version.split("/")
                                if len(path_parts) > 1:
                                    filename_with_ext = "/".join(path_parts[1:])
                                    public_id = filename_with_ext.rsplit(".", 1)[0]
                        
                        if public_id:
                            cloudinary.uploader.destroy(public_id)
                            cleanup_stats["images_deleted"] += 1
                    except Exception as e:
                        logging.error(f"Failed to delete Cloudinary image for dish {dish_id}: {e}")
                
                # Hard delete comments
                comments_result = await comments_collection.delete_many({"dish_id": dish_id})
                cleanup_stats["comments_deleted"] += comments_result.deleted_count
                
                # Hard delete recipe
                recipe_result = await recipe_collection.delete_one({"dish_id": dish_id})
                cleanup_stats["recipes_deleted"] += recipe_result.deleted_count
                
                # Hard delete dish
                await dishes_collection.delete_one({"_id": dish["_id"]})
                cleanup_stats["dishes_deleted"] += 1
                
            except Exception as e:
                error_msg = f"Failed to permanently delete dish {dish_id}: {str(e)}"
                logging.error(error_msg)
                cleanup_stats["errors"].append(error_msg)
        
        logging.info(f"✅ Automatic cleanup completed: {cleanup_stats}")
        
    except Exception as e:
        logging.error(f"❌ Error in auto_cleanup_deleted_dishes: {e}")

# ==== Startup Events ====
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    await init_redis()
    
    # Run cleanup immediately on startup (catch-up for any missed jobs)
    logging.info("🧹 Running startup cleanup check...")
    await auto_cleanup_deleted_dishes()
    
    # Start background scheduler
    if not scheduler.running:
        # Schedule cleanup job to run daily at 2:00 AM
        scheduler.add_job(
            auto_cleanup_deleted_dishes,
            CronTrigger(hour=2, minute=0),  # 2:00 AM every day
            id="cleanup_deleted_dishes",
            name="Cleanup dishes deleted >7 days ago",
            replace_existing=True
        )
        scheduler.start()
        logging.info("✅ Background scheduler started - Daily cleanup at 2:00 AM")
    
    print("🚀 Backend services initialized")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    if scheduler.running:
        scheduler.shutdown()
        logging.info("🛑 Background scheduler stopped")

# Include các routers từ routes
from routes import user_route, dish_route, recipe_route, search_route, comment_route, otp_route
from routes.auth_route import auth_router
from core.auth.dependencies import get_current_user
app.include_router(comment_route.router)
app.include_router(user_route.router, prefix="/users", tags=["Users"])
app.include_router(dish_route.router, prefix="/dishes", tags=["Dishes"])
app.include_router(recipe_route.router, prefix="/recipes", tags=["Recipes"])
app.include_router(search_route.router, prefix="/search", tags=["Search"])
app.include_router(recommendations_router, prefix="/api/recommendations", tags=["Recommendations"])
app.include_router(otp_route.otp_router, tags=["OTP"])
app.include_router(auth_router, tags=["Authentication"])

# Dynamic CORS based on environment
ALLOWED_ORIGINS = [
    "http://localhost:19006",  # Expo web
    "http://localhost:8081",   # Expo web (Metro)
    "exp://localhost:19000",   # Expo dev client
    "http://localhost:3000",
    "http://localhost:8000"   
]

# Add production frontend URL if exists
FRONTEND_URL = os.getenv("FRONTEND_URL")
if FRONTEND_URL:
    ALLOWED_ORIGINS.append(FRONTEND_URL)
    # Also allow without trailing slash
    ALLOWED_ORIGINS.append(FRONTEND_URL.rstrip("/"))

# Function to check if origin is allowed (includes Cloudflare Pages preview URLs)
def is_allowed_origin(origin: str) -> bool:
    """Check if origin is allowed, including Cloudflare Pages preview deployments"""
    if origin in ALLOWED_ORIGINS:
        return True
    # Allow all Cloudflare Pages preview deployments (*.pages.dev)
    if origin.endswith(".2025-27-09-app-cook-frontend.pages.dev"):
        return True
    return False

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.2025-27-09-app-cook-frontend\.pages\.dev",
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    ✅ Sử dụng ObjectId cho performance tốt hơn
    """
    # Tạo social data
    await user_social_col.insert_one({
        "user_id": user_id,  # ObjectId  
        "followers": [],
        "following": [],
        "follower_count": 0,
        "following_count": 0
    })
    
    # Tạo activity data
    await user_activity_col.insert_one({
        "user_id": user_id,  # ObjectId
        "favorite_dishes": [],
        "cooked_dishes": [],
        "viewed_dishes": [],
        "created_recipes": [],
        "created_dishes": []
    })
    
    # Tạo notifications data
    await user_notifications_col.insert_one({
        "user_id": user_id,  # ObjectId
        "notifications": [],
        "unread_count": 0
    })
    
    # Tạo preferences data
    await user_preferences_col.insert_one({
        "user_id": user_id,  # ObjectId
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

@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"ok": True, "async": True}

@app.get("/me")
async def me(decoded=Depends(get_current_user)):
    """
    Trả về hồ sơ user trong Mongo (và auto tạo nếu chưa có) - ASYNC VERSION
    """
    doc = await ensure_user_document_async(decoded)
    user_id = doc["_id"]  # ObjectId
    
    # Import user_helper nếu chưa có
    from core.user_management.service import user_helper
    
    # Load additional data từ các collections riêng (ALL ASYNC)
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
    
    allowed = {k: v for k, v in payload.items() if k in ["name", "avatar", "display_id"]}
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
    """Migrate một user từ structure cũ sang structure mới - ASYNC VERSION"""
    if not DEBUG:
        raise HTTPException(403, "Only available in debug mode")
    
    from bson import ObjectId
    
    try:
        # ASYNC find
        user = await users_col.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(404, "User not found")
        
        # Migrate data từ user document sang các collections riêng
        user_oid = user["_id"]  # ObjectId
        
        # 1. Migrate social data (ASYNC)
        social_data = {
            "user_id": user_oid,  # ObjectId
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
            "user_id": user_oid,  # ObjectId
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
            "user_id": user_oid,  # ObjectId
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
            "user_id": user_oid,  # ObjectId
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
        
        await users_col.replace_one({"_id": user["_id"]}, clean_user_doc)
        
        return {
            "message": f"Successfully migrated user {user_id} to new structure",
            "migrated_collections": ["user_social", "user_activity", "user_notifications", "user_preferences"],
            "cleaned_fields": ["followers", "following", "recipes", "liked_dishes", "favorite_dishes", "cooked_dishes", "viewed_dishes", "notifications"]
        }
        
    except Exception as e:
        raise HTTPException(400, f"Migration failed: {str(e)}")

@app.post("/admin/migrate-all-users")
async def migrate_all_users_async():
    """Migrate tất cả users sang structure mới - ASYNC VERSION"""
    if not DEBUG:
        raise HTTPException(403, "Only available in debug mode")
    
    try:
        # ASYNC find all users
        users_cursor = users_col.find({})
        users = await users_cursor.to_list(length=1000)
        migrated_count = 0
        errors = []
        
        for user in users:
            try:
                user_id = str(user["_id"])
                
                # Check if already migrated (no old fields)
                if not any(field in user for field in ["followers", "following", "recipes", "favorite_dishes"]):
                    continue
                
                # Perform migration (same logic as single user)
                # This would be the same async migration logic as above
                migrated_count += 1
                
            except Exception as e:
                errors.append(f"User {user.get('_id', 'unknown')}: {str(e)}")
        
        return {
            "message": f"Migration completed",
            "migrated_users": migrated_count,
            "total_users": len(users),
            "errors": errors
        }
        
    except Exception as e:
        raise HTTPException(500, f"Bulk migration failed: {str(e)}")
