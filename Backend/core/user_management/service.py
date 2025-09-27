"""
User Management Service - Unified helpers and data operations
Combines UserDataService, user_helper, and auth_helper functionality
"""
from database.mongo import (
    users_collection,
    user_social_collection, 
    user_activity_collection, 
    user_notifications_collection, 
    user_preferences_collection
)
from models.user_model import UserSocial, UserActivity, UserNotifications, UserPreferences
from fastapi import HTTPException, Request
from bson import ObjectId
from typing import Optional, Dict, Any
import firebase_admin
from firebase_admin import auth as fb_auth


# ==================== AUTH HELPERS ====================

async def get_current_user_async(request: Request) -> Dict[str, Any]:
    """
    Verify Firebase ID token and return decoded user info - ASYNC VERSION
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    id_token = auth_header.split(" ", 1)[1].strip()

    try:
        # Firebase verify is sync, but we can make it async-compatible
        decoded = fb_auth.verify_id_token(id_token, check_revoked=True)
        return decoded
    except fb_auth.ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="Token expired")
    except fb_auth.RevokedIdTokenError:
        raise HTTPException(status_code=401, detail="Token revoked")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

# Keep old function for backward compatibility
def get_current_user(request: Request) -> Dict[str, Any]:
    """
    DEPRECATED: Use get_current_user_async instead
    """
    import asyncio
    return asyncio.run(get_current_user_async(request))


async def get_user_by_email(user_email: str):
    """
    Helper function to get user from database by email
    """
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


# ==================== USER HELPER ====================

def user_helper(user) -> dict:
    """
    Convert user document to dict, handling ObjectId serialization
    Updated for new normalized structure - only basic user info
    """
    if not user:
        return {}
    
    return {
        "id": str(user["_id"]) if isinstance(user["_id"], ObjectId) else str(user.get("_id", "")),
        "email": user.get("email", ""),
        "display_id": user.get("display_id", ""),
        "name": user.get("name", ""),
        "avatar": user.get("avatar", ""),
        "bio": user.get("bio", ""),
        "created_at": user.get("createdAt"),  # Note: fixed field name
        "last_active": user.get("lastLoginAt")  # Note: fixed field name
    }


# ==================== USER DATA SERVICE ====================

class UserDataService:
    """Service để quản lý các collections liên quan đến user"""
    
    @staticmethod
    async def get_user_social(user_id: str) -> Optional[UserSocial]:
        """Lấy thông tin social của user"""
        social_data = await user_social_collection.find_one({"user_id": user_id})
        if social_data:
            return UserSocial(**social_data)
        return None
    
    @staticmethod
    async def get_user_activity(user_id: str) -> Optional[UserActivity]:
        """Lấy activity history của user"""
        activity_data = await user_activity_collection.find_one({"user_id": user_id})
        if activity_data:
            return UserActivity(**activity_data)
        return None
    
    @staticmethod
    async def get_user_notifications(user_id: str) -> Optional[UserNotifications]:
        """Lấy notifications của user"""
        notif_data = await user_notifications_collection.find_one({"user_id": user_id})
        if notif_data:
            return UserNotifications(**notif_data)
        return None
    
    @staticmethod
    async def get_user_preferences(user_id: str) -> Optional[UserPreferences]:
        """Lấy preferences của user"""
        pref_data = await user_preferences_collection.find_one({"user_id": user_id})
        if pref_data:
            return UserPreferences(**pref_data)
        return None
    
    @staticmethod
    async def init_user_data(user_id: str):
        """Khởi tạo data cho user mới"""
        # Tạo social data
        await user_social_collection.insert_one({
            "user_id": user_id,
            "followers": [],
            "following": [],
            "follower_count": 0,
            "following_count": 0
        })
        
        # Tạo activity data
        await user_activity_collection.insert_one({
            "user_id": user_id,
            "favorite_dishes": [],
            "cooked_dishes": [],
            "viewed_dishes": [],
            "created_recipes": [],
            "created_dishes": []
        })
        
        # Tạo notifications data
        await user_notifications_collection.insert_one({
            "user_id": user_id,
            "notifications": [],
            "unread_count": 0
        })
        
        # Tạo preferences data
        await user_preferences_collection.insert_one({
            "user_id": user_id,
            "reminders": [],
            "dietary_restrictions": [],
            "cuisine_preferences": [],
            "difficulty_preference": "all"
        })
    
    @staticmethod
    async def add_to_cooked(user_id: str, dish_id: str, max_history: int = 50):
        """Thêm món ăn vào lịch sử đã nấu"""
        activity = await user_activity_collection.find_one({"user_id": user_id})
        
        if not activity:
            await UserDataService.init_user_data(user_id)
            activity = {"cooked_dishes": []}
        
        cooked = activity.get("cooked_dishes", [])
        
        if dish_id in cooked:
            return {"msg": "Dish already in cooked history"}
        
        if len(cooked) >= max_history:
            cooked = cooked[1:]  # Xóa món cũ nhất
        
        cooked.append(dish_id)
        
        await user_activity_collection.update_one(
            {"user_id": user_id},
            {"$set": {"cooked_dishes": cooked}}
        )
        
        return {"msg": "Dish added to cooked history"}
    
    @staticmethod
    async def add_to_viewed(user_id: str, dish_id: str, max_history: int = 50):
        """Thêm món ăn vào lịch sử đã xem"""
        activity = await user_activity_collection.find_one({"user_id": user_id})
        
        if not activity:
            await UserDataService.init_user_data(user_id)
            activity = {"viewed_dishes": []}
        
        viewed = activity.get("viewed_dishes", [])
        
        if dish_id in viewed:
            return {"msg": "Dish already in viewed history"}
        
        if len(viewed) >= max_history:
            viewed = viewed[1:]  # Xóa món cũ nhất
        
        viewed.append(dish_id)
        
        await user_activity_collection.update_one(
            {"user_id": user_id},
            {"$set": {"viewed_dishes": viewed}}
        )
        
        return {"msg": "Dish added to viewed history"}
    
    @staticmethod
    async def add_to_favorites(user_id: str, dish_id: str):
        """Thêm món ăn vào danh sách yêu thích"""
        await user_activity_collection.update_one(
            {"user_id": user_id},
            {"$addToSet": {"favorite_dishes": dish_id}}
        )
        return {"msg": "Dish added to favorites"}
    
    @staticmethod
    async def follow_user(follower_id: str, following_id: str):
        """User follow user khác"""
        # Thêm vào following list của follower
        await user_social_collection.update_one(
            {"user_id": follower_id},
            {"$addToSet": {"following": following_id}}
        )
        
        # Thêm vào followers list của người được follow
        await user_social_collection.update_one(
            {"user_id": following_id},
            {"$addToSet": {"followers": follower_id}}
        )
        
        # Cập nhật counter
        await UserDataService._update_social_counters(follower_id)
        await UserDataService._update_social_counters(following_id)
        
        return {"msg": "Successfully followed user"}
    
    @staticmethod
    async def _update_social_counters(user_id: str):
        """Cập nhật số lượng followers/following"""
        social = await user_social_collection.find_one({"user_id": user_id})
        if social:
            follower_count = len(social.get("followers", []))
            following_count = len(social.get("following", []))
            
            await user_social_collection.update_one(
                {"user_id": user_id},
                {"$set": {
                    "follower_count": follower_count,
                    "following_count": following_count
                }}
            )

    # ==================== MIGRATION HELPERS ====================
    
    @staticmethod
    async def migrate_single_user(user):
        """Migration một user từ structure cũ sang mới"""
        user_id = str(user["_id"])
        
        # Migrate social data
        social_data = {
            "user_id": user_id,
            "followers": user.get("followers", []),
            "following": user.get("following", []),
            "follower_count": len(user.get("followers", [])),
            "following_count": len(user.get("following", []))
        }
        await user_social_collection.update_one(
            {"user_id": user_id},
            {"$set": social_data},
            upsert=True
        )
        
        # Migrate activity data
        activity_data = {
            "user_id": user_id,
            "favorite_dishes": user.get("favorite_dishes", []),
            "cooked_dishes": user.get("cooked_dishes", []),
            "viewed_dishes": user.get("viewed_dishes", []),
            "created_recipes": user.get("recipes", []),
            "created_dishes": []
        }
        await user_activity_collection.update_one(
            {"user_id": user_id},
            {"$set": activity_data},
            upsert=True
        )
        
        # Migrate notifications data
        notif_data = {
            "user_id": user_id,
            "notifications": user.get("notifications", []),
            "unread_count": len(user.get("notifications", []))
        }
        await user_notifications_collection.update_one(
            {"user_id": user_id},
            {"$set": notif_data},
            upsert=True
        )
        
        # Migrate preferences data
        pref_data = {
            "user_id": user_id,
            "reminders": user.get("reminders", []),
            "dietary_restrictions": [],
            "cuisine_preferences": [],
            "difficulty_preference": "all"
        }
        await user_preferences_collection.update_one(
            {"user_id": user_id},
            {"$set": pref_data},
            upsert=True
        )
        
        # Clean up old fields from users collection
        await users_collection.update_one(
            {"_id": user["_id"]},
            {"$unset": {
                "followers": "",
                "following": "",
                "recipes": "",
                "favorite_dishes": "",
                "cooked_dishes": "",
                "viewed_dishes": "",
                "notifications": "",
                "reminders": ""
            }}
        )
        
        return f"Migrated user: {user.get('email', 'unknown')}"
    
    @staticmethod
    async def migrate_all_users():
        """Migration tất cả users từ structure cũ sang mới"""
        print("🚀 Starting user data migration...")
        
        users = await users_collection.find().to_list(length=1000)
        migrated_count = 0
        
        for user in users:
            try:
                # Check if already migrated (no old fields)
                if not any(field in user for field in ["followers", "following", "recipes", "favorite_dishes"]):
                    continue
                
                result = await UserDataService.migrate_single_user(user)
                print(f"📦 {result}")
                migrated_count += 1
                
            except Exception as e:
                print(f"❌ Error migrating {user.get('email', 'unknown')}: {e}")
        
        print(f"✅ Migration completed! Migrated {migrated_count} users")
        return {"migrated_users": migrated_count, "total_users": len(users)}
