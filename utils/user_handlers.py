"""
User Route Handlers - Extracted from routes/user/
All user-related route handlers consolidated here
"""
from fastapi import HTTPException, Body
from core.user_management.service import UserDataService, user_helper
from core.auth.dependencies import extract_user_email, get_user_by_email
from models.user_model import UserOut
from bson import ObjectId
from typing import Dict, Any, List
from datetime import datetime, timezone, timedelta

from database.mongo import (
    users_collection,
    user_social_collection, 
    user_activity_collection,
    user_notifications_collection,
    user_preferences_collection,
    dishes_collection
)


async def is_admin(decoded) -> bool:
    """
    Shared async helper to check if a user is admin.
    Checks (in order):
      - custom claims in decoded token (admin)
      - ADMIN_EMAILS env var
      - role=='admin' in users_collection

    Returns True if admin, False otherwise.
    
    ⚠️ SECURITY: DEBUG mode does NOT grant admin access!
    """
    import os, logging
    
    # ❌ REMOVED: DEBUG mode granting admin to everyone (SECURITY RISK!)
    # if os.getenv("DEBUG", "False").lower() == "true":
    #     return True

    # 1) Token claims
    try:
        if decoded:
            if decoded.get("admin"):
                return True
            claims = decoded.get("claims") or decoded.get("__claims__") or {}
            if isinstance(claims, dict) and claims.get("admin"):
                return True
            firebase_meta = decoded.get("firebase") or {}
            if isinstance(firebase_meta, dict) and firebase_meta.get("admin"):
                return True
    except Exception:
        pass

    # 2) ADMIN_EMAILS
    try:
        user_email = extract_user_email(decoded)
        admin_emails = os.getenv("ADMIN_EMAILS", "").split(",")
        admin_emails = [e.strip() for e in admin_emails if e.strip()]
        if user_email and user_email in admin_emails:
            return True
    except Exception:
        pass

    # 3) DB role
    try:
        if user_email:
            user_doc = await users_collection.find_one({"email": user_email})
            if user_doc and user_doc.get("role") == "admin":
                return True
    except Exception:
        logging.exception("Failed to check user role for admin access")

    return False


# ==================== PROFILE HANDLERS ====================

async def create_user_handler(decoded):
    """
    Tạo user mới từ Firebase token (tự động được gọi khi login lần đầu)
    Hỗ trợ Google OAuth - nhận name và picture từ token
    """
    email = decoded.get("email")
    uid = decoded.get("uid")
    
    # Google OAuth trả về các field này
    name = decoded.get("name", "")
    avatar = decoded.get("picture", "")  # URL avatar từ Google
    
    if not email:
        raise HTTPException(status_code=400, detail="Email required from Firebase token")

    # Kiểm tra user đã tồn tại chưa
    existing_user = await users_collection.find_one({"email": email})
    if existing_user:
        print(f"ℹ️  User already exists: {email}")
        return user_helper(existing_user)

    # Tạo display_id từ email
    display_id = email.split('@')[0]
    original_display_id = display_id
    
    # ✅ Try to create user với display_id, handle DuplicateKeyError nếu conflict
    from pymongo.errors import DuplicateKeyError
    
    counter = 1
    max_attempts = 100  # Tránh infinite loop
    
    while counter <= max_attempts:
        try:
            # Tạo user mới
            user_data = {
                "email": email,
                "display_id": display_id,
                "name": name,
                "avatar": avatar,
                "bio": "",
                "firebase_uid": uid,
                "createdAt": datetime.now(timezone.utc),
                "lastLoginAt": datetime.now(timezone.utc),
            }

            result = await users_collection.insert_one(user_data)
            new_user = await users_collection.find_one({"_id": result.inserted_id})
            
            # ✅ Success - break out of loop
            break
            
        except DuplicateKeyError as e:
            # ✅ display_id conflict - try next number
            if "display_id" in str(e):
                display_id = f"{original_display_id}{counter}"
                counter += 1
                continue
            else:
                # Other duplicate key error (email, etc.)
                raise e
    else:
        # Reached max_attempts
        raise HTTPException(500, f"Could not generate unique display_id after {max_attempts} attempts")
    
    # Khởi tạo các collections phụ cho user - ✅ Pass ObjectId
    await UserDataService.init_user_data(new_user["_id"])

    print(f"✅ Created new user: {email} with display_id: {display_id}")
    return user_helper(new_user)


async def get_user_handler(user_id: str):
    """
    Lấy thông tin user theo ID (public)
    """
    try:
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user_helper(user)


async def get_me_handler(decoded):
    """
    Lấy thông tin người dùng hiện tại (tự động tạo nếu chưa có)
    """
    email = extract_user_email(decoded)
    
    # Thử tìm user trước - async call
    user = await users_collection.find_one({"email": email})

    if not user:
        # Tự động tạo user mới nếu chưa tồn tại (first-time login)
        uid = decoded.get("uid")
        name = decoded.get("name", "")
        avatar = decoded.get("picture", "")
        
        # Tạo display_id từ email
        display_id = email.split('@')[0] if email else f"user_{uid[:8]}"
        
        # Kiểm tra display_id trùng - async call
        counter = 1
        original_display_id = display_id
        while await users_collection.find_one({"display_id": display_id}):
            display_id = f"{original_display_id}{counter}"
            counter += 1

        # Tạo user mới
        user_data = {
            "email": email,
            "display_id": display_id,
            "name": name,
            "avatar": avatar,
            "bio": "",
            "firebase_uid": uid,
            "createdAt": datetime.now(timezone.utc),
            "lastLoginAt": datetime.now(timezone.utc),
        }

        # async call
        result = await users_collection.insert_one(user_data)
        user = await users_collection.find_one({"_id": result.inserted_id})
        
        # Khởi tạo các collections phụ cho user mới - ✅ Pass ObjectId
        await UserDataService.init_user_data(user["_id"])
    else:
        # Cập nhật lastLoginAt cho user đã tồn tại - async call
        await users_collection.update_one(
            {"email": email}, 
            {"$set": {"lastLoginAt": datetime.now(timezone.utc)}}
        )
    
    return user_helper(user)
async def update_me_handler(user_update: dict, decoded):
    """
    Cập nhật thông tin cá nhân
    """
    email = extract_user_email(decoded)
    user = await users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Loại bỏ các field không được phép edit
    user_update.pop("email", None)
    user_update.pop("hashed_password", None)
    user_update.pop("firebase_uid", None)
    
    # Kiểm tra display_id trùng
    if "display_id" in user_update:
        existing = await users_collection.find_one({"display_id": user_update["display_id"]})
        if existing and existing["_id"] != user["_id"]:
            raise HTTPException(status_code=400, detail="Display ID already taken")
    
    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": user_update}
    )
    updated_user = await users_collection.find_one({"_id": user["_id"]})
    return user_helper(updated_user)


async def search_users_handler(q: str, decoded):
    """
    Tìm kiếm người dùng theo display_id
    """
    email = extract_user_email(decoded)
    current_user = await users_collection.find_one({"email": email})
    
    query = {
        "display_id": {"$regex": q, "$options": "i"},
        "_id": {"$ne": current_user["_id"]}  
    }
    users = await users_collection.find(query).to_list(length=20)
    return [user_helper(u) for u in users]


# ==================== SOCIAL HANDLERS ====================

async def get_my_social_handler(decoded):
    """
    Lấy thông tin social của user hiện tại
    """
    email = extract_user_email(decoded)
    user = await users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # ✅ Pass ObjectId directly
    social_data = await UserDataService.get_user_social(user["_id"])
    return social_data.dict() if social_data else {
        "followers": [], "following": [], "follower_count": 0, "following_count": 0
    }


async def follow_user_handler(user_id: str, decoded):
    """
    Theo dõi người dùng khác
    """
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID")

    email = extract_user_email(decoded)
    user_to_follow = await users_collection.find_one({"_id": ObjectId(user_id)})
    current_user = await users_collection.find_one({"email": email})

    if not user_to_follow or not current_user:
        raise HTTPException(status_code=404, detail="User not found")

    if current_user["_id"] == user_to_follow["_id"]:
        raise HTTPException(status_code=400, detail="You cannot follow yourself")
    
    # ✅ Pass ObjectId directly  
    result = await UserDataService.follow_user(current_user["_id"], user_id)   
 
    # Gửi thông báo milestone nếu cần
    # ✅ Convert user_id string to ObjectId for query
    social_data = await UserDataService.get_user_social(ObjectId(user_id))
    if social_data and social_data.follower_count % 5 == 0:
        # TODO: Implement milestone notification
        pass
    
    return {"msg": f"You are now following {user_to_follow['display_id']}"}


async def get_user_dishes_handler(user_id: str):
    """
    Xem danh sách món ăn đã tạo của người dùng khác
    """
    dishes = await dishes_collection.find({"creator_id": user_id}).to_list(length=20)
    return dishes


# ==================== ACTIVITY HANDLERS ====================

MAX_HISTORY = 50

async def get_my_activity_handler(decoded):
    """
    Lấy activity history của user hiện tại
    """
    email = extract_user_email(decoded)
    user = await users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # ✅ Pass ObjectId directly
    activity_data = await UserDataService.get_user_activity(user["_id"])
    return activity_data.dict() if activity_data else {
        "favorite_dishes": [], "cooked_dishes": [], "viewed_dishes": [], 
        "created_recipes": [], "created_dishes": []
    }


async def add_cooked_dish_handler(dish_id: str, decoded):
    """
    Thêm món vào lịch sử đã nấu
    """
    email = extract_user_email(decoded)
    user = await users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # ✅ Pass ObjectId directly
    result = await UserDataService.add_to_cooked(user["_id"], dish_id, MAX_HISTORY)
    return result


async def add_viewed_dish_handler(dish_id: str, decoded):
    """
    Thêm món vào lịch sử đã xem - ✅ Use user_activity_collection với viewed_dishes_and_users
    """
    if not ObjectId.is_valid(dish_id):
        raise HTTPException(status_code=400, detail="Invalid dish ID")
    
    dish = await dishes_collection.find_one({"_id": ObjectId(dish_id)})
    if not dish:
        raise HTTPException(status_code=404, detail="Dish not found")
    
    email = extract_user_email(decoded)
    user = await users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_oid = user["_id"]  # ✅ ObjectId
    now = datetime.now(timezone.utc)  # ✅ Timezone-aware

    # ✅ Use same format as router: {type, id, name, image, ts}
    viewed_entry = {
        "type": "dish",
        "id": dish_id,
        "name": dish.get("name", ""),
        "image": dish.get("image_b64", ""),
        "ts": now,
    }
    
    # ✅ Use user_activity_collection with viewed_dishes_and_users field
    # 1) Xóa entry cũ nếu có (cùng type + id)
    await user_activity_collection.update_one(
        {"user_id": user_oid},
        {"$pull": {"viewed_dishes_and_users": {"type": "dish", "id": dish_id}}},
        upsert=True
    )
    
    # 2) Thêm entry mới vào đầu list
    await user_activity_collection.update_one(
        {"user_id": user_oid},
        {
            "$push": {
                "viewed_dishes_and_users": {
                    "$each": [viewed_entry],
                    "$position": 0,  # Thêm vào đầu
                    "$slice": 50     # Giữ tối đa 50 items
                }
            },
            "$set": {"updated_at": now}
        },
        upsert=True
    )
    
    return {"message": "Dish added to view history", "dish_id": dish_id}

# Trong user_handlers.py (handler function)
async def get_viewed_dishes_handler(limit: int, decoded):
    """
    Lấy lịch sử món đã xem - ✅ Use user_activity_collection với viewed_dishes_and_users
    """
    try:
        email = extract_user_email(decoded)
        user = await users_collection.find_one({"email": email})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_oid = user["_id"]  # ✅ ObjectId
        
        # ✅ Get from user_activity_collection với viewed_dishes_and_users field
        activity_doc = await user_activity_collection.find_one(
            {"user_id": user_oid},
            {"_id": 0, "viewed_dishes_and_users": 1}
        )
        
        viewed_items = (activity_doc or {}).get("viewed_dishes_and_users", [])[:limit]
        
        # ✅ Filter chỉ dishes (not users) và lấy thông tin chi tiết
        dish_details = []
        for item in viewed_items:
            if item.get("type") == "dish":
                dish_id = item.get("id")
                if dish_id and ObjectId.is_valid(dish_id):
                    dish = await dishes_collection.find_one({"_id": ObjectId(dish_id)})
                    if dish:
                        dish_details.append({
                            "id": str(dish["_id"]),
                            "name": dish.get("name", ""),
                            "image_b64": dish.get("image_b64"),
                            "image_mime": dish.get("image_mime"),
                            "cooking_time": dish.get("cooking_time", 0),
                            "average_rating": dish.get("average_rating", 0.0),
                            "viewed_at": item.get("ts")  # ✅ Use 'ts' field from new format
                })
        
        return {
            "viewed_dishes": dish_details,
            "total": len(dish_details)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def notify_favorite_handler(dish_id: str):
    """
    Gửi thông báo khi có người thả tim món ăn 
    """
    dish = await dishes_collection.find_one({"_id": ObjectId(dish_id)})
    if not dish:
        raise HTTPException(status_code=404, detail="Dish not found")
    
    creator_id = dish.get("creator_id")
    if not creator_id:
        return {"msg": "No creator for this dish"}
    
    # ✅ OPTIMIZED: Count favorites efficiently using aggregation
    favorite_count = await user_activity_collection.count_documents({
        "favorite_dishes": dish_id
    })
    
    # Gửi thông báo milestone
    if favorite_count > 0 and favorite_count % 5 == 0:
        await user_notifications_collection.update_one(
            {"user_id": creator_id},
            {
                "$push": {"notifications": {
                    "type": "milestone",
                    "message": f"Món ăn '{dish['name']}' của bạn đã nhận được {favorite_count} lượt thả tim!",
                    "created_at": "now",
                    "read": False
                }},
                "$inc": {"unread_count": 1}
            },
            upsert=True
        )
    return {"msg": "Notification sent if milestone reached"}


# ==================== PREFERENCES HANDLERS ====================

async def get_my_notifications_handler(decoded):
    """
    Lấy thông báo của user hiện tại
    """
    email = extract_user_email(decoded)
    user = await users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # ✅ Pass ObjectId directly
    notif_data = await UserDataService.get_user_notifications(user["_id"])
    return notif_data.dict() if notif_data else {"notifications": [], "unread_count": 0}


async def set_reminders_handler(reminders: List[str], decoded):
    """
    Đặt thời gian nhắc nhở
    """
    email = extract_user_email(decoded)
    user = await users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ✅ Use ObjectId directly
    await user_preferences_collection.update_one(
        {"user_id": user["_id"]},
        {"$set": {"reminders": reminders}},
        upsert=True
    )
    return {"msg": "Reminders set successfully"}


async def get_reminders_handler(decoded):
    """
    Lấy danh sách thời gian nhắc nhở
    """
    email = extract_user_email(decoded)
    user = await users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # ✅ Use ObjectId directly
    preferences = await user_preferences_collection.find_one({"user_id": user["_id"]})
    return preferences.get("reminders", []) if preferences else []

async def get_my_favorites_handler(decoded):
    """
    Trả về danh sách món ăn yêu thích của user hiện tại.
    """
    user_email = decoded.get("email")
    user = await users_collection.find_one({"email": user_email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    favorite_ids = user.get("favorite_dishes", [])
    if not isinstance(favorite_ids, list):
        favorite_ids = []

    dishes = []
    if favorite_ids:
        try:
            object_ids = [ObjectId(did) for did in favorite_ids if ObjectId.is_valid(did)]
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid dish ID format")

        cursor = dishes_collection.find({"_id": {"$in": object_ids}})
        async for dish in cursor:
            dish["id"] = str(dish["_id"])
            dish["_id"] = str(dish["_id"])
            dishes.append(dish)

    return dishes


# ==================== ADMIN HANDLERS ====================

async def cleanup_dishes_handler(decoded):
    """
    Admin: Cleanup invalid dishes and migrate image fields
    """
    if not await is_admin(decoded):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    res = await dishes_collection.delete_many({
        "$or": [
            {"name": {"$exists": False}},
            {"name": ""},
            {"name": None}
        ]
    })
    
    migration_res = await dishes_collection.update_many(
        {},
        {"$unset": {"image_b64": "", "image_mime": ""}}
    )
    
    # Import recipe_collection nếu cần
    from database.mongo import recipe_collection
    
    recipe_migration_res = await recipe_collection.update_many(
        {},
        {"$unset": {"image_b64": "", "image_mime": ""}}
    )
    
    return {
        "deleted_count": res.deleted_count, 
        "dishes_migrated": migration_res.modified_count,
        "recipes_migrated": recipe_migration_res.modified_count,
        "message": "Cleanup and migration completed"
    }


async def permanent_delete_old_dishes_handler(decoded):
    """
    Admin: Permanently delete dishes that have been soft-deleted for >7 days
    """
    if not await is_admin(decoded):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    import logging
    
    # Calculate cutoff date (7 days ago)
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)
    
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
    
    # Import collections needed
    from database.mongo import recipe_collection, comments_collection
    
    for dish in old_deleted_dishes:
        dish_id = str(dish["_id"])
        
        try:
            # 1. Delete Cloudinary image if exists
            if dish.get("cloudinary_public_id"):
                try:
                    import cloudinary
                    cloudinary.uploader.destroy(dish["cloudinary_public_id"])
                    cleanup_stats["images_deleted"] += 1
                except Exception as e:
                    cleanup_stats["errors"].append(f"Failed to delete image for dish {dish_id}: {str(e)}")
            
            # 2. Delete associated comments
            comments_result = await comments_collection.delete_many({"dish_id": dish_id})
            cleanup_stats["comments_deleted"] += comments_result.deleted_count
            
            # 3. Delete associated recipe if exists
            if dish.get("recipe_id"):
                recipe_result = await recipe_collection.delete_one({"_id": ObjectId(dish["recipe_id"])})
                if recipe_result.deleted_count > 0:
                    cleanup_stats["recipes_deleted"] += 1
            
            # 4. Remove from user activities
            await user_activity_collection.update_many(
                {},
                {
                    "$pull": {
                        "favorite_dishes": dish_id,
                        "cooked_dishes": dish_id,
                        "viewed_dishes": dish_id,
                        "created_dishes": dish_id
                    }
                }
            )
            
            # 5. Finally delete the dish itself
            await dishes_collection.delete_one({"_id": dish["_id"]})
            cleanup_stats["dishes_deleted"] += 1
            
        except Exception as e:
            cleanup_stats["errors"].append(f"Failed to delete dish {dish_id}: {str(e)}")
            logging.error(f"Error deleting dish {dish_id}: {str(e)}")
    
    logging.info(f"Admin cleanup completed: {cleanup_stats}")
    return {
        "success": True,
        "cleanup_stats": cleanup_stats,
        "cutoff_date": cutoff_date.isoformat()
    }


async def migrate_difficulty_to_dishes_handler(decoded):
    """
    Admin: Migrate difficulty field from recipes to dishes
    """
    if not await is_admin(decoded):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    from database.mongo import recipe_collection
    
    migrated_count = 0
    
    dishes_cursor = dishes_collection.find({
        "recipe_id": {"$exists": True, "$ne": None},
        "difficulty": {"$exists": False}
    })
    
    async for dish in dishes_cursor:
        recipe_id = dish.get("recipe_id")
        if recipe_id and ObjectId.is_valid(recipe_id):
            recipe = await recipe_collection.find_one({"_id": ObjectId(recipe_id)})
            if recipe and recipe.get("difficulty"):
                await dishes_collection.update_one(
                    {"_id": dish["_id"]},
                    {"$set": {"difficulty": recipe["difficulty"]}}
                )
                migrated_count += 1
    
    return {
        "migrated_count": migrated_count,
        "message": f"Successfully migrated difficulty for {migrated_count} dishes"
    }


async def migrate_existing_images_handler(decoded):
    """
    Admin: Migrate existing base64 images to Cloudinary
    """
    if not await is_admin(decoded):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    import base64
    import cloudinary
    from database.mongo import recipe_collection
    
    migrated_dishes = 0
    migrated_recipes = 0
    
    # Migrate dishes
    dishes_cursor = dishes_collection.find({"image_b64": {"$exists": True, "$ne": None}})
    async for dish in dishes_cursor:
        try:
            image_b64 = dish.get("image_b64")
            image_mime = dish.get("image_mime", "image/jpeg")
            
            if image_b64:
                image_data = base64.b64decode(image_b64)
                upload_result = cloudinary.uploader.upload(
                    image_data,
                    folder="dishes",
                    resource_type="image"
                )
                
                await dishes_collection.update_one(
                    {"_id": dish["_id"]},
                    {
                        "$set": {
                            "image_url": upload_result["secure_url"],
                            "cloudinary_public_id": upload_result["public_id"]
                        },
                        "$unset": {"image_b64": "", "image_mime": ""}
                    }
                )
                migrated_dishes += 1
        except Exception as e:
            print(f"Failed to migrate dish image: {str(e)}")
    
    # Migrate recipes
    recipes_cursor = recipe_collection.find({"image_b64": {"$exists": True, "$ne": None}})
    async for recipe in recipes_cursor:
        try:
            image_b64 = recipe.get("image_b64")
            image_mime = recipe.get("image_mime", "image/jpeg")
            
            if image_b64:
                image_data = base64.b64decode(image_b64)
                upload_result = cloudinary.uploader.upload(
                    image_data,
                    folder="recipes",
                    resource_type="image"
                )
                
                await recipe_collection.update_one(
                    {"_id": recipe["_id"]},
                    {
                        "$set": {
                            "image_url": upload_result["secure_url"],
                            "cloudinary_public_id": upload_result["public_id"]
                        },
                        "$unset": {"image_b64": "", "image_mime": ""}
                    }
                )
                migrated_recipes += 1
        except Exception as e:
            print(f"Failed to migrate recipe image: {str(e)}")
    
    return {
        "migrated_dishes": migrated_dishes,
        "migrated_recipes": migrated_recipes,
        "message": "Image migration completed"
    }
