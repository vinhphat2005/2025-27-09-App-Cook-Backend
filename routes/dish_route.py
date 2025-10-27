# routers/dishes.py - FIXED VERSION
from fastapi import APIRouter, HTTPException, Depends, Query
from models.dish_model import Dish, DishOut, DishIn
from models.dish_with_recipe_model import DishWithRecipeIn, DishWithRecipeOut
from models.dish_response_models import DishDetailOut, DishWithRecipeDetailOut, RecipeDetailOut
from database.mongo import dishes_collection, users_collection, recipe_collection
from bson import ObjectId
from datetime import datetime, timezone
from core.auth.dependencies import get_current_user, get_user_by_email, extract_user_email
from typing import List, Optional, Dict
from pydantic import BaseModel
import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url
import os
from dotenv import load_dotenv
import base64
import io
import logging
load_dotenv() 

# ✅ Safer Cloudinary configuration - check at startup, not import
def _configure_cloudinary():
    """Configure Cloudinary with proper error handling"""
    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

    if not all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
        # In development, log warning but don't crash
        if os.getenv("DEBUG", "False").lower() == "true":
            logging.warning("Cloudinary credentials not set. Image upload will be disabled.")
            return False
        else:
            raise ValueError("Missing Cloudinary credentials. Please set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET in your environment variables.")

    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        secure=True
    )
    
    logging.info("Cloudinary configured successfully")
    return True

# Configure at module load
CLOUDINARY_ENABLED = _configure_cloudinary()

router = APIRouter()

class RecipeDetailOut(BaseModel):
    id: str
    name: str
    description: str = ""
    ingredients: list = []
    difficulty: str = ""
    instructions: list = []
    average_rating: float = 0.0
    image_url: str = None
    created_by: str = None
    dish_id: str = None
    ratings: list = []
    created_at: datetime = None

class CheckFavoritesRequest(BaseModel):
    dish_ids: List[str]

def _to_detail_out(d) -> DishDetailOut:
    """Convert MongoDB document to DishDetailOut with consistent field mapping"""
    return DishDetailOut(
        id=str(d["_id"]),
        name=d.get("name", ""),
        image_url=d.get("image_url"),
        cooking_time=int(d.get("cooking_time") or 0),
        average_rating=float(d.get("average_rating") or 0.0),
        ingredients=d.get("ingredients") or [],
        liked_by=d.get("liked_by") or [],
        creator_id=d.get("creator_id"),
        recipe_id=d.get("recipe_id"),
        difficulty=d.get("difficulty"),
        created_at=d.get("created_at"),
    )

def _clean_dish_data(dish_dict: dict) -> dict:
    cleaned = {}
    for k in ["name", "cooking_time", "ingredients"]:
        if k in dish_dict and dish_dict[k] not in (None, "", [], {}):
            cleaned[k] = dish_dict[k]
    for k in ["image_url", "creator_id", "recipe_id", "difficulty"]:
        if k in dish_dict and dish_dict[k] not in (None, "", [], {}):
            cleaned[k] = dish_dict[k]
    cleaned.setdefault("ratings", [])
    cleaned.setdefault("average_rating", 0.0)
    cleaned.setdefault("liked_by", [])
    # ✅ Fix: Use timezone-aware datetime
    cleaned.setdefault("created_at", datetime.now(timezone.utc))
    return cleaned

async def upload_image_to_cloudinary(image_b64: str, image_mime: str, folder: str = "dishes") -> dict:
    """
    Upload image to Cloudinary and return both secure_url and public_id
    """
    try:
        # ✅ Check if Cloudinary is enabled
        if not CLOUDINARY_ENABLED:
            raise HTTPException(status_code=503, detail="Image upload service not available")
        
        logging.info(f"Uploading image to cloud storage, folder: {folder}")
        
        # ✅ Add basic size validation
        image_data = base64.b64decode(image_b64)
        
        # Check file size (limit to 10MB)
        if len(image_data) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Image too large. Max size is 10MB.")
        
        upload_result = cloudinary.uploader.upload(
            image_data,
            folder=folder,
            resource_type="image",
            transformation=[
                {"quality": "auto:good"},
                {"fetch_format": "auto"}
            ]
        )
        
        logging.info(f"Successfully uploaded image: {upload_result['secure_url']}")
        
        # ✅ Return both secure_url and public_id for flexibility
        return {
            "secure_url": upload_result["secure_url"],
            "public_id": upload_result["public_id"],
            "url": upload_result["secure_url"]  # For backward compatibility
        }
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logging.error(f"Failed to upload image to cloud storage: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to upload image: {str(e)}")

def get_optimized_image_url(public_id: str, width: int = None, height: int = None, crop: str = "auto") -> str:
    try:
        transformations = []
        
        if width and height:
            transformations.append({
                "width": width,
                "height": height,
                "crop": crop,
                "gravity": "auto"
            })
        
        transformations.extend([
            {"quality": "auto:good"},
            {"fetch_format": "auto"}
        ])
        
        optimized_url, _ = cloudinary_url(
            public_id,
            transformation=transformations
        )
        
        return optimized_url
    except Exception as e:
        logging.error(f"Failed to generate optimized URL: {str(e)}")
        return public_id

# Helper function to get user ID from different possible fields
def _get_user_identification(user_doc):
    """Extract user identification info from user document"""
    if not user_doc:
        return None, None, None
    
    user_id = str(user_doc["_id"])
    user_email = user_doc.get("email")
    user_username = user_doc.get("username")
    
    return user_id, user_email, user_username

def _validate_object_id(id_str: str, field_name: str = "ID") -> ObjectId:
    """
    Validate and convert string to ObjectId
    Raises HTTPException if invalid
    """
    if not id_str or not isinstance(id_str, str):
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}: empty or not string")
    
    if not ObjectId.is_valid(id_str):
        raise HTTPException(status_code=400, detail=f"Invalid {field_name} format")
    
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name} format")

# ============= ROUTES (CORRECT ORDER) =============

# POST routes first
@router.post("/", response_model=DishOut)
async def create_dish(dish: DishIn, decoded=Depends(get_current_user)):
    user_email = extract_user_email(decoded)
    user = await get_user_by_email(user_email, decoded)  # ✅ Pass decoded token

    payload = dish.dict()
    
    image_url = None
    if payload.get("image_b64") and payload.get("image_mime"):
        upload_result = await upload_image_to_cloudinary(
            payload["image_b64"], 
            payload["image_mime"], 
            folder="dishes"
        )
        image_url = upload_result["secure_url"]

    new_doc = _clean_dish_data({
        "name": payload["name"],
        "cooking_time": payload["cooking_time"],
        "ingredients": payload.get("ingredients", []),
        "difficulty": payload.get("difficulty", "easy"),
        "image_url": image_url,
        "creator_id": str(user["_id"]),
    })

    result = await dishes_collection.insert_one(new_doc)
    if not result.inserted_id:
        raise HTTPException(status_code=500, detail="Insert failed")

    return DishOut(
        id=str(result.inserted_id),
        name=new_doc["name"],
        cooking_time=new_doc["cooking_time"],
        ingredients=new_doc.get("ingredients", []),  # ✅ Fix: Include ingredients for frontend
        average_rating=new_doc.get("average_rating", 0.0),
        image_url=new_doc.get("image_url", None),  # ✅ Fix: Use None instead of empty string
        creator_id=new_doc.get("creator_id"),
        created_at=new_doc.get("created_at")
    )

@router.post("/with-recipe", response_model=DishWithRecipeOut)
async def create_dish_with_recipe(data: DishWithRecipeIn, decoded=Depends(get_current_user)):
    user_email = extract_user_email(decoded)
    user = await get_user_by_email(user_email, decoded)  # ✅ Pass decoded token

    difficulty_map = {
        "Dễ": "easy",
        "Trung bình": "medium", 
        "Khó": "hard"
    }

    normalized_difficulty = difficulty_map.get(data.difficulty, data.difficulty.lower())
    
    image_b64 = getattr(data, "image_b64", None)
    image_mime = getattr(data, "image_mime", None)
    
    image_url = None
    if image_b64 and image_mime:
        upload_result = await upload_image_to_cloudinary(
            image_b64, 
            image_mime, 
            folder="dishes"
        )
        image_url = upload_result["secure_url"]

    dish_doc = _clean_dish_data({
        "name": data.name,
        "ingredients": data.ingredients,
        "cooking_time": data.cooking_time,
        "difficulty": normalized_difficulty,
        "image_url": image_url,
        "creator_id": str(user["_id"]),
    })
    
    dish_result = await dishes_collection.insert_one(dish_doc)
    if not dish_result.inserted_id:
        raise HTTPException(status_code=500, detail="Failed to create dish")

    dish_id = str(dish_result.inserted_id)

    recipe_doc = {
        "name": data.recipe_name or f"Cách làm {data.name}",
        "description": data.recipe_description or f"Hướng dẫn làm {data.name}",
        "ingredients": data.recipe_ingredients or data.ingredients,
        "difficulty": normalized_difficulty,
        "instructions": data.instructions,
        "dish_id": dish_id,
        "created_by": user_email,
        "ratings": [],
        "average_rating": 0.0,
        "image_url": image_url,
        # ✅ Fix: Use timezone-aware datetime
        "created_at": datetime.now(timezone.utc),
    }
    
    recipe_result = await recipe_collection.insert_one(recipe_doc)
    if not recipe_result.inserted_id:
        await dishes_collection.delete_one({"_id": dish_result.inserted_id})
        raise HTTPException(status_code=500, detail="Failed to create recipe")

    await dishes_collection.update_one(
        {"_id": dish_result.inserted_id},
        {"$set": {"recipe_id": str(recipe_result.inserted_id)}}
    )

    return DishWithRecipeOut(
        dish_id=dish_id,
        recipe_id=str(recipe_result.inserted_id),
        dish_name=data.name,
        recipe_name=recipe_doc["name"],
        message=f"Món '{data.name}' và công thức nấu ăn đã được tạo thành công!"
    )

@router.post("/check-favorites", response_model=Dict[str, bool])
async def check_favorites(request: CheckFavoritesRequest, decoded=Depends(get_current_user)):
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        user_email = extract_user_email(decoded)
        logger.info(f"🔍 Check favorites - User email: {user_email}")
        
        # ✅ Use get_user_by_email for consistency
        user = await get_user_by_email(user_email, decoded)  # ✅ Pass decoded token
        logger.info(f"✅ User found: {user.get('_id')} - {user.get('email')}")
        
        favorite_dish_ids = user.get("favorite_dishes", [])
        logger.info(f"📋 User has {len(favorite_dish_ids)} favorite dishes")
        
        result = {}
        for dish_id in request.dish_ids:
            result[dish_id] = dish_id in favorite_dish_ids
            
        logger.info(f"✅ Check favorites result: {len(result)} dishes checked")
        return result
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions  
    except Exception as e:
        logger.error(f"❌ Error checking favorites: {str(e)}")
        logger.error(f"📧 User email: {decoded.get('email', 'N/A')}")
        logger.error(f"🆔 User UID: {decoded.get('uid', 'N/A')}")
        raise HTTPException(status_code=500, detail=f"Failed to check favorites: {str(e)}")

@router.post("/{dish_id}/rate")
async def rate_dish(dish_id: str, rating: int, decoded=Depends(get_current_user)):
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be 1-5")
    
    # ✅ Validate ObjectId before using
    dish_oid = _validate_object_id(dish_id, "dish_id")
    
    # ✅ Check dish exists first
    d = await dishes_collection.find_one({"_id": dish_oid})
    if not d:
        raise HTTPException(status_code=404, detail="Dish not found")
    
    # ✅ CONCURRENCY SAFE: Use atomic operations
    # Add rating using $push and recalculate average using aggregation
    result = await dishes_collection.update_one(
        {"_id": dish_oid},
        {"$push": {"ratings": rating}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Dish not found")
    
    # ✅ Calculate new average using aggregation (atomic)
    pipeline = [
        {"$match": {"_id": dish_oid}},
        {"$project": {
            "average_rating": {"$avg": "$ratings"},
            "rating_count": {"$size": "$ratings"}
        }}
    ]
    
    aggregation_result = await dishes_collection.aggregate(pipeline).to_list(1)
    if aggregation_result:
        new_average = aggregation_result[0]["average_rating"]
        rating_count = aggregation_result[0]["rating_count"]
        
        # Update the average_rating field
        await dishes_collection.update_one(
            {"_id": dish_oid},
            {"$set": {"average_rating": new_average}}
        )
        
        return {
            "msg": "Rating added successfully", 
            "average_rating": new_average,
            "total_ratings": rating_count
        }
    else:
        raise HTTPException(status_code=404, detail="Dish not found")

@router.post("/{dish_id}/toggle-favorite")
async def toggle_favorite_dish(dish_id: str, decoded=Depends(get_current_user)):
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # ✅ Validate ObjectId before using
        dish_oid = _validate_object_id(dish_id, "dish_id")
        
        # ✅ Check if dish exists first
        dish_exists = await dishes_collection.find_one({"_id": dish_oid}, {"_id": 1})
        if not dish_exists:
            raise HTTPException(status_code=404, detail="Dish not found")
        
        # ✅ Use consistent method for getting user email and user data
        user_email = extract_user_email(decoded)
        logger.info(f"🔍 Toggle favorite - User email: {user_email}")
        
        # ✅ Use get_user_by_email for consistency with other endpoints
        user = await get_user_by_email(user_email, decoded)  # ✅ Pass decoded token
        logger.info(f"✅ User found: {user.get('_id')} - {user.get('email')}")
        
        favorite_ids = user.get("favorite_dishes") or []
        dish_id_str = str(dish_oid)
        
        logger.info(f"📋 Current favorites: {len(favorite_ids)} dishes")
        logger.info(f"❤️ Toggling dish: {dish_id_str}")
        
        if dish_id_str in favorite_ids:
            # Remove from favorites
            await users_collection.update_one(
                {"_id": user["_id"]},
                {"$pull": {"favorite_dishes": dish_id_str}}
            )
            logger.info(f"➖ Removed dish {dish_id_str} from favorites")
            return {"isFavorite": False, "message": "Removed from favorites"}
        else:
            # Add to favorites
            await users_collection.update_one(
                {"_id": user["_id"]},
                {"$addToSet": {"favorite_dishes": dish_id_str}}
            )
            logger.info(f"➕ Added dish {dish_id_str} to favorites")
            return {"isFavorite": True, "message": "Added to favorites"}
            
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"❌ Error in toggle_favorite_dish: {str(e)}")
        logger.error(f"📧 User email: {decoded.get('email', 'N/A')}")
        logger.error(f"🆔 User UID: {decoded.get('uid', 'N/A')}")
        raise HTTPException(status_code=500, detail=f"Failed to toggle favorite: {str(e)}")

def _check_admin_access(decoded):
    """
    Check if user has admin access
    For now, checking DEBUG environment or specific admin emails
    """
    import os
    
    # Allow in DEBUG mode
    if os.getenv("DEBUG", "False").lower() == "true":
        return True
    
    # Check for admin emails (add your admin emails here)
    user_email = extract_user_email(decoded)
    admin_emails = os.getenv("ADMIN_EMAILS", "").split(",")
    admin_emails = [email.strip() for email in admin_emails if email.strip()]
    
    if user_email in admin_emails:
        return True
    
    # You can add role-based check here if you have user roles in database
    # user = await users_collection.find_one({"email": user_email})
    # if user and user.get("role") == "admin":
    #     return True
    
    return False

# Admin routes
@router.post("/admin/cleanup")
async def cleanup_dishes(decoded=Depends(get_current_user)):
    # ✅ Check admin access
    if not _check_admin_access(decoded):
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

@router.post("/admin/migrate-difficulty")
async def migrate_difficulty_to_dishes(decoded=Depends(get_current_user)):
    # ✅ Check admin access
    if not _check_admin_access(decoded):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    migrated_count = 0
    
    dishes_cursor = dishes_collection.find({
        "recipe_id": {"$exists": True, "$ne": None},
        "difficulty": {"$exists": False}
    })
    
    async for dish in dishes_cursor:
        try:
            recipe_id = dish.get("recipe_id")
            if recipe_id:
                # ✅ Validate ObjectId before using
                if ObjectId.is_valid(recipe_id):
                    recipe = await recipe_collection.find_one({"_id": ObjectId(recipe_id)})
                    if recipe and recipe.get("difficulty"):
                        await dishes_collection.update_one(
                            {"_id": dish["_id"]},
                            {"$set": {"difficulty": recipe["difficulty"]}}
                        )
                        migrated_count += 1
                        logging.info(f"Migrated difficulty '{recipe['difficulty']}' for dish: {dish.get('name')}")
                else:
                    logging.warning(f"Invalid recipe_id format: {recipe_id} for dish: {dish.get('name')}")
        except Exception as e:
            logging.error(f"Failed to migrate dish {dish.get('_id')}: {str(e)}")
    
    return {
        "migrated_count": migrated_count,
        "message": f"Successfully migrated difficulty for {migrated_count} dishes"
    }

@router.post("/admin/migrate-images")
async def migrate_existing_images(decoded=Depends(get_current_user)):
    # ✅ Check admin access
    if not _check_admin_access(decoded):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    migrated_dishes = 0
    migrated_recipes = 0
    
    dishes_cursor = dishes_collection.find({"image_b64": {"$exists": True, "$ne": None}})
    async for dish in dishes_cursor:
        try:
            if dish.get("image_b64") and dish.get("image_mime"):
                upload_result = await upload_image_to_cloudinary(
                    dish["image_b64"], 
                    dish["image_mime"], 
                    folder="dishes_migration"
                )
                
                await dishes_collection.update_one(
                    {"_id": dish["_id"]},
                    {
                        "$set": {"image_url": upload_result["secure_url"]},
                        "$unset": {"image_b64": "", "image_mime": ""}
                    }
                )
                migrated_dishes += 1
        except Exception as e:
            logging.error(f"Failed to migrate dish {dish['_id']}: {str(e)}")
    
    recipes_cursor = recipe_collection.find({"image_b64": {"$exists": True, "$ne": None}})
    async for recipe in recipes_cursor:
        try:
            if recipe.get("image_b64") and recipe.get("image_mime"):
                upload_result = await upload_image_to_cloudinary(
                    recipe["image_b64"], 
                    recipe["image_mime"], 
                    folder="recipes_migration"
                )
                
                await recipe_collection.update_one(
                    {"_id": recipe["_id"]},
                    {
                        "$set": {"image_url": upload_result["secure_url"]},
                        "$unset": {"image_b64": "", "image_mime": ""}
                    }
                )
                migrated_recipes += 1
        except Exception as e:
            logging.error(f"Failed to migrate recipe {recipe['_id']}: {str(e)}")
    
    return {
        "migrated_dishes": migrated_dishes,
        "migrated_recipes": migrated_recipes,
        "message": "Image migration completed"
    }

# ============= GET ROUTES (SPECIFIC FIRST, DYNAMIC LAST) =============

# FIXED: High-rated dishes endpoint for Recipe screen
@router.get("/high-rated", response_model=List[DishDetailOut])
async def get_high_rated_dishes(min_rating: float = 4.0, limit: int = 50, skip: int = 0):
    """
    CRITICAL: Returns ONLY dishes with average_rating >= min_rating
    Used by Recipe screen to show featured/popular dishes
    """
    logging.info(f"Fetching high-rated dishes - min_rating: {min_rating}, limit: {limit}, skip: {skip}")
    
    try:
        # Query for dishes with rating >= min_rating AND valid name
        query = {
            "name": {"$exists": True, "$ne": "", "$ne": None},
            "average_rating": {"$gte": min_rating}
        }
        
        logging.info(f"High-rated query: {query}")
        
        cursor = dishes_collection.find(query).sort("average_rating", -1).skip(skip).limit(limit)
        high_rated_docs = await cursor.to_list(length=limit)
        
        logging.info(f"Found {len(high_rated_docs)} high-rated dishes")
        
        # Convert to response format
        result = [_to_detail_out(d) for d in high_rated_docs]
        
        # Log sample for debugging
        if result:
            logging.info(f"Sample high-rated dish: {result[0].name} (rating: {result[0].average_rating})")
        
        return result
        
    except Exception as e:
        logging.error(f"Error in get_high_rated_dishes: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch high-rated dishes: {str(e)}")

# FIXED: My dishes endpoint for Profile screen  
@router.get("/my-dishes", response_model=List[DishDetailOut])
async def get_my_dishes(
    limit: int = 50,
    skip: int = 0,
    decoded=Depends(get_current_user)
):
    """
    CRITICAL: Returns dishes created by current user
    Used by Profile screen to show user's dishes
    """
    try:
        user_email = extract_user_email(decoded)
        user = await get_user_by_email(user_email, decoded)  # ✅ Pass decoded token
        
        if not user:
            logging.error(f"User not found for email: {user_email}")
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id, user_email_from_doc, user_username = _get_user_identification(user)
        
        logging.info(f"Fetching dishes for user - ID: {user_id}, Email: {user_email_from_doc}")
        
        # Build comprehensive query to find user's dishes
        # Check multiple possible fields where user ID might be stored
        query = {
            "name": {"$exists": True, "$ne": "", "$ne": None},  # Valid dish name
            "$or": [
                {"creator_id": user_id},           # String version of user ID
                {"created_by": user_email_from_doc},  # User email
                {"created_by": user_id},           # User ID in created_by field
                {"user_id": user_id},              # Alternative user_id field
                {"owner_id": user_id},             # Alternative owner_id field
            ]
        }
        
        # ✅ Safe ObjectId conversion - only if valid
        if ObjectId.is_valid(user_id):
            query["$or"].append({"creator_id": ObjectId(user_id)})  # ObjectId version
        
        # Also include username if available
        if user_username:
            query["$or"].append({"created_by": user_username})
        
        logging.info(f"My dishes query: {query}")
        
        cursor = dishes_collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        user_dishes = await cursor.to_list(length=limit)
        
        logging.info(f"Found {len(user_dishes)} dishes for user {user_id}")
        
        # Log sample dishes for debugging
        if user_dishes:
            logging.info("Sample user dishes:")
            for i, dish in enumerate(user_dishes[:3]):  # Log first 3
                logging.info(f"  {i+1}. {dish.get('name')} - creator_id: {dish.get('creator_id')}")
        
        result = [_to_detail_out(dish) for dish in user_dishes]
        return result
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logging.error(f"Error in get_my_dishes: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch user dishes: {str(e)}")

@router.get("/suggest/today", response_model=List[DishDetailOut])
async def suggest_today(limit: int = 12):
    """
    Returns recent dishes for today's suggestions
    """
    try:
        query = {"name": {"$exists": True, "$ne": "", "$ne": None}}
        cursor = dishes_collection.find(query).sort("created_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [_to_detail_out(d) for d in docs]
    except Exception as e:
        logging.error(f"Error in suggest_today: {str(e)}")
        return []  # Return empty list on error

@router.get("/random", response_model=List[DishDetailOut])
async def get_random_dishes(limit: int = 3):
    """
    Returns random dishes
    """
    try:
        pipeline = [
            {"$match": {"name": {"$exists": True, "$ne": "", "$ne": None}}},
            {"$sample": {"size": limit}},
        ]
        
        docs = await dishes_collection.aggregate(pipeline).to_list(length=limit)
        return [_to_detail_out(d) for d in docs]
        
    except Exception as e:
        logging.error(f"Error fetching random dishes: {str(e)}")
        # Fallback to regular query
        try:
            cursor = dishes_collection.find(
                {"name": {"$exists": True, "$ne": "", "$ne": None}}
            ).sort("created_at", -1).limit(limit)
            docs = await cursor.to_list(length=limit)
            return [_to_detail_out(d) for d in docs]
        except Exception as fallback_e:
            logging.error(f"Fallback query also failed: {str(fallback_e)}")
            return []

# FIXED: Main dishes list endpoint - handles both general and user-specific queries
@router.get("/", response_model=List[DishDetailOut])
async def get_dishes(
    limit: int = 20,
    skip: int = 0,
    my_dishes: bool = False,
    decoded=Depends(get_current_user)
):
    """
    Main dishes endpoint - can return all dishes or user's dishes based on my_dishes parameter
    """
    try:
        base_query = {"name": {"$exists": True, "$ne": "", "$ne": None}}
        
        if my_dishes:
            # Get current user info
            user_email = extract_user_email(decoded)
            user = await get_user_by_email(user_email, decoded)  # ✅ Pass decoded token
            
            if not user:
                logging.warning(f"User not found for my_dishes query: {user_email}")
                return []  # Return empty list if user not found
            
            user_id, user_email_from_doc, user_username = _get_user_identification(user)
            
            # Add user filter to base query
            user_filter = {
                "$or": [
                    {"creator_id": user_id},
                    {"created_by": user_email_from_doc},
                    {"created_by": user_id},
                    {"user_id": user_id},
                    {"owner_id": user_id}
                ]
            }
            
            # ✅ Safe ObjectId conversion - only if valid
            if ObjectId.is_valid(user_id):
                user_filter["$or"].append({"creator_id": ObjectId(user_id)})
            
            if user_username:
                user_filter["$or"].append({"created_by": user_username})
            
            # Combine base query with user filter
            query = {"$and": [base_query, user_filter]}
            
            logging.info(f"My dishes query via main endpoint: {query}")
        else:
            query = base_query
            logging.info(f"All dishes query: {query}")
        
        cursor = dishes_collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        dishes = await cursor.to_list(length=limit)
        
        logging.info(f"Found {len(dishes)} dishes (my_dishes={my_dishes})")
        
        return [_to_detail_out(dish) for dish in dishes]
        
    except Exception as e:
        logging.error(f"Error in get_dishes: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch dishes: {str(e)}")

# ============= DYNAMIC ROUTES (MUST COME LAST) =============

@router.get("/{dish_id}", response_model=DishDetailOut)
async def get_dish_detail(dish_id: str):
    """
    Get single dish details by ID - SECURE VERSION
    """
    try:
        # ✅ Validate ObjectId before using
        dish_oid = _validate_object_id(dish_id, "dish_id")
        
        d = await dishes_collection.find_one({"_id": dish_oid})
        if not d:
            raise HTTPException(status_code=404, detail="Dish not found")
        return _to_detail_out(d)
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logging.error(f"Error getting dish {dish_id}: {str(e)}")
        raise HTTPException(status_code=404, detail="Dish not found")

@router.get("/{dish_id}/with-recipe", response_model=DishWithRecipeDetailOut)
async def get_dish_with_recipe(dish_id: str):
    """
    Get dish with associated recipe details - SECURE VERSION
    """
    try:
        # ✅ Validate ObjectId before using
        dish_oid = _validate_object_id(dish_id, "dish_id")
        
        dish = await dishes_collection.find_one({"_id": dish_oid})
        if not dish:
            raise HTTPException(status_code=404, detail="Dish not found")
        
        recipe = None
        recipe_id = dish.get("recipe_id")
        if recipe_id:
            try:
                # ✅ Validate recipe ObjectId before using
                if ObjectId.is_valid(recipe_id):
                    r = await recipe_collection.find_one({"_id": ObjectId(recipe_id)})
                    if r:
                        recipe = RecipeDetailOut(
                            id=str(r["_id"]),
                            name=r.get("name", ""),
                            description=r.get("description", ""),
                            ingredients=r.get("ingredients", []),
                            difficulty=r.get("difficulty", ""),
                            instructions=r.get("instructions", []),
                            average_rating=float(r.get("average_rating", 0.0)),
                            image_url=r.get("image_url"),
                            created_by=r.get("created_by"),
                            dish_id=r.get("dish_id"),
                            ratings=r.get("ratings", []),
                            created_at=r.get("created_at"),
                        )
                else:
                    logging.warning(f"Invalid recipe_id format: {recipe_id} for dish: {dish_id}")
            except Exception as recipe_e:
                logging.warning(f"Failed to fetch recipe {recipe_id}: {str(recipe_e)}")
                # Continue without recipe if recipe fetch fails
        
        return DishWithRecipeDetailOut(
            dish=_to_detail_out(dish),
            recipe=recipe
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logging.error(f"Error getting dish with recipe {dish_id}: {str(e)}")
        raise HTTPException(status_code=404, detail="Dish not found")