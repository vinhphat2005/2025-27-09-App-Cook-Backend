# routers/dishes.py - FIXED VERSION
from fastapi import APIRouter, HTTPException, Depends, Query
from models.dish_model import Dish, DishOut, DishIn
from models.dish_with_recipe_model import DishWithRecipeIn, DishWithRecipeOut
from database.mongo import dishes_collection, users_collection, recipe_collection
from bson import ObjectId
from datetime import datetime
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

# Load Cloudinary credentials từ environment variables
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

if not all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
    raise ValueError("Missing Cloudinary credentials. Please set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET in your environment variables.")

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True
)

print(f"Cloudinary configured with cloud_name: {CLOUDINARY_CLOUD_NAME}")

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

class DishWithRecipeDetailOut(BaseModel):
    dish: 'DishDetailOut'
    recipe: Optional[RecipeDetailOut] = None

class DishDetailOut(BaseModel):
    id: str
    name: str
    image_url: Optional[str] = None
    cooking_time: int
    average_rating: float
    ingredients: List[str] = []
    liked_by: List[str] = []
    creator_id: Optional[str] = None
    recipe_id: Optional[str] = None
    difficulty: Optional[str] = None
    created_at: Optional[datetime] = None

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
    cleaned.setdefault("created_at", datetime.utcnow())
    return cleaned

async def upload_image_to_cloudinary(image_b64: str, image_mime: str, folder: str = "dishes") -> str:
    try:
        logging.info(f"Uploading to Cloudinary - Cloud: {CLOUDINARY_CLOUD_NAME}, Folder: {folder}")
        
        image_data = base64.b64decode(image_b64)
        
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
        return upload_result["secure_url"]
        
    except Exception as e:
        logging.error(f"Failed to upload image to Cloudinary (Cloud: {CLOUDINARY_CLOUD_NAME}): {str(e)}")
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

# ============= ROUTES (CORRECT ORDER) =============

# POST routes first
@router.post("/", response_model=DishOut)
async def create_dish(dish: DishIn, decoded=Depends(get_current_user)):
    user_email = extract_user_email(decoded)
    user = await get_user_by_email(user_email)

    payload = dish.dict()
    
    image_url = None
    if payload.get("image_b64") and payload.get("image_mime"):
        image_url = await upload_image_to_cloudinary(
            payload["image_b64"], 
            payload["image_mime"], 
            folder="dishes"
        )

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
        average_rating=new_doc.get("average_rating", 0.0),
    )

@router.post("/with-recipe", response_model=DishWithRecipeOut)
async def create_dish_with_recipe(data: DishWithRecipeIn, decoded=Depends(get_current_user)):
    user_email = extract_user_email(decoded)
    user = await get_user_by_email(user_email)

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
        image_url = await upload_image_to_cloudinary(
            image_b64, 
            image_mime, 
            folder="dishes"
        )

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
        "created_at": datetime.utcnow(),
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
    try:
        user_email = extract_user_email(decoded)
        user = await get_user_by_email(user_email)
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        favorite_dish_ids = user.get("favorite_dishes", [])
        
        result = {}
        for dish_id in request.dish_ids:
            result[dish_id] = dish_id in favorite_dish_ids
            
        return result
        
    except Exception as e:
        logging.error(f"Error checking favorites: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to check favorites: {str(e)}")

@router.post("/{dish_id}/rate")
async def rate_dish(dish_id: str, rating: int, decoded=Depends(get_current_user)):
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be 1-5")
    d = await dishes_collection.find_one({"_id": ObjectId(dish_id)})
    if not d:
        raise HTTPException(status_code=404, detail="Dish not found")
    ratings = d.get("ratings", [])
    ratings.append(rating)
    avg = sum(ratings) / len(ratings)
    await dishes_collection.update_one(
        {"_id": ObjectId(dish_id)},
        {"$set": {"ratings": ratings, "average_rating": avg}}
    )
    return {"msg": "Rating added", "average_rating": avg}

@router.post("/{dish_id}/toggle-favorite")
async def toggle_favorite_dish(dish_id: str, decoded=Depends(get_current_user)):
    user_email = decoded.get("email")
    user = await users_collection.find_one({"email": user_email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    favorite_ids = user.get("favorite_dishes") or []
    dish_id_str = str(dish_id)
    if dish_id_str in favorite_ids:
        await users_collection.update_one(
            {"_id": user["_id"]},
            {"$pull": {"favorite_dishes": dish_id_str}}
        )
        return {"isFavorite": False}
    else:
        await users_collection.update_one(
            {"_id": user["_id"]},
            {"$addToSet": {"favorite_dishes": dish_id_str}}
        )
        return {"isFavorite": True}

# Admin routes
@router.post("/admin/cleanup")
async def cleanup_dishes(decoded=Depends(get_current_user)):
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
    migrated_count = 0
    
    dishes_cursor = dishes_collection.find({
        "recipe_id": {"$exists": True, "$ne": None},
        "difficulty": {"$exists": False}
    })
    
    async for dish in dishes_cursor:
        try:
            recipe_id = dish.get("recipe_id")
            if recipe_id:
                recipe = await recipe_collection.find_one({"_id": ObjectId(recipe_id)})
                if recipe and recipe.get("difficulty"):
                    await dishes_collection.update_one(
                        {"_id": dish["_id"]},
                        {"$set": {"difficulty": recipe["difficulty"]}}
                    )
                    migrated_count += 1
                    logging.info(f"Migrated difficulty '{recipe['difficulty']}' for dish: {dish.get('name')}")
        except Exception as e:
            logging.error(f"Failed to migrate dish {dish.get('_id')}: {str(e)}")
    
    return {
        "migrated_count": migrated_count,
        "message": f"Successfully migrated difficulty for {migrated_count} dishes"
    }

@router.post("/admin/migrate-images")
async def migrate_existing_images(decoded=Depends(get_current_user)):
    migrated_dishes = 0
    migrated_recipes = 0
    
    dishes_cursor = dishes_collection.find({"image_b64": {"$exists": True, "$ne": None}})
    async for dish in dishes_cursor:
        try:
            if dish.get("image_b64") and dish.get("image_mime"):
                image_url = await upload_image_to_cloudinary(
                    dish["image_b64"], 
                    dish["image_mime"], 
                    folder="dishes_migration"
                )
                
                await dishes_collection.update_one(
                    {"_id": dish["_id"]},
                    {
                        "$set": {"image_url": image_url},
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
                image_url = await upload_image_to_cloudinary(
                    recipe["image_b64"], 
                    recipe["image_mime"], 
                    folder="recipes_migration"
                )
                
                await recipe_collection.update_one(
                    {"_id": recipe["_id"]},
                    {
                        "$set": {"image_url": image_url},
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
        user = await get_user_by_email(user_email)
        
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
                {"creator_id": ObjectId(user_id)}, # ObjectId version (if stored as ObjectId)
                {"created_by": user_email_from_doc},  # User email
                {"created_by": user_id},           # User ID in created_by field
                {"user_id": user_id},              # Alternative user_id field
                {"owner_id": user_id},             # Alternative owner_id field
            ]
        }
        
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
            user = await get_user_by_email(user_email)
            
            if not user:
                logging.warning(f"User not found for my_dishes query: {user_email}")
                return []  # Return empty list if user not found
            
            user_id, user_email_from_doc, user_username = _get_user_identification(user)
            
            # Add user filter to base query
            user_filter = {
                "$or": [
                    {"creator_id": user_id},
                    {"creator_id": ObjectId(user_id)},
                    {"created_by": user_email_from_doc},
                    {"created_by": user_id},
                    {"user_id": user_id},
                    {"owner_id": user_id}
                ]
            }
            
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
    Get single dish details by ID
    """
    try:
        d = await dishes_collection.find_one({"_id": ObjectId(dish_id)})
        if not d:
            raise HTTPException(status_code=404, detail="Dish not found")
        return _to_detail_out(d)
    except Exception as e:
        logging.error(f"Error getting dish {dish_id}: {str(e)}")
        raise HTTPException(status_code=404, detail="Dish not found")

@router.get("/{dish_id}/with-recipe", response_model=DishWithRecipeDetailOut)
async def get_dish_with_recipe(dish_id: str):
    """
    Get dish with associated recipe details
    """
    try:
        dish = await dishes_collection.find_one({"_id": ObjectId(dish_id)})
        if not dish:
            raise HTTPException(status_code=404, detail="Dish not found")
        
        recipe = None
        recipe_id = dish.get("recipe_id")
        if recipe_id:
            try:
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