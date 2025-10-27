"""
Recipe Route Handlers - Extracted from routes/recipe_route.py
All recipe-related route handlers consolidated here
"""
import logging
from fastapi import HTTPException
from models.recipe_model import RecipeIn, RecipeOut
from database.mongo import recipe_collection, users_collection
from core.auth.dependencies import extract_user_email
from bson import ObjectId
from typing import List

logger = logging.getLogger(__name__)


# ==================== INDEX MANAGEMENT ====================

async def ensure_recipe_indexes():
    """
    Create necessary indexes for recipes collection
    """
    try:
        # Index for finding recipes by creator
        await recipe_collection.create_index("created_by")
        
        # Index for finding recipes by dish
        await recipe_collection.create_index("dish_id")
        
        # Index for sorting by rating
        await recipe_collection.create_index("average_rating")
        
        # Compound index for efficient queries
        await recipe_collection.create_index([
            ("created_by", 1),
            ("created_at", -1)
        ])
        
        # Text index for search functionality
        await recipe_collection.create_index([
            ("name", "text"),
            ("description", "text"),
            ("instructions", "text")
        ])
        
        logger.info("✅ Recipe indexes created successfully")
    except Exception as e:
        logger.warning(f"⚠️ Recipe index creation failed (may already exist): {e}")


# ==================== HELPER FUNCTIONS ====================

def _validate_object_id(object_id: str, field_name: str = "ID") -> ObjectId:
    """
    Validate and convert string to ObjectId
    """
    if not object_id or not isinstance(object_id, str):
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}")
    
    if not ObjectId.is_valid(object_id):
        raise HTTPException(status_code=400, detail=f"Invalid {field_name} format")
    
    try:
        return ObjectId(object_id)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}")


def validate_rating(rating: int) -> int:
    """
    Validate rating is between 1-5 stars
    """
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5 stars")
    return rating


def extract_ratings_from_recipe(recipe: dict) -> List[int]:
    """
    Extract ratings from recipe, ensuring all ratings are 1-5 stars
    """
    user_ratings = recipe.get("user_ratings", {})
    if user_ratings:
        # New format: user_ratings = {"email": rating}
        ratings = []
        for email, rating in user_ratings.items():
            try:
                validated_rating = validate_rating(rating)
                ratings.append(validated_rating)
            except HTTPException:
                # Skip invalid ratings but don't crash
                continue
        return ratings
    else:
        # Old format: ratings = [1, 2, 3, 4, 5]
        ratings = recipe.get("ratings", [])
        validated_ratings = []
        for rating in ratings:
            try:
                validated_rating = validate_rating(rating)
                validated_ratings.append(validated_rating)
            except HTTPException:
                # Skip invalid ratings but don't crash
                continue
        return validated_ratings


# ==================== RECIPE HANDLERS ====================

async def create_recipe_handler(recipe: RecipeIn, decoded):
    """
    Tạo công thức mới với validation và error handling
    """
    from datetime import datetime, timezone
    
    user_email = extract_user_email(decoded)
    
    try:
        # Validate user exists
        user = await users_collection.find_one({"email": user_email})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Validate dish_id if provided
        if recipe.dish_id:
            dish_oid = _validate_object_id(recipe.dish_id, "dish ID")
        
        # Input sanitization
        if len(recipe.instructions) > 5000:
            raise HTTPException(status_code=400, detail="Instructions too long (max 5000 characters)")
        if len(recipe.ingredients) > 50:
            raise HTTPException(status_code=400, detail="Too many ingredients (max 50)")
        
        # ✅ Prepare complete recipe data with security
        recipe_dict = recipe.dict()
        recipe_dict["ratings"] = []
        recipe_dict["average_rating"] = 0.0
        recipe_dict["user_ratings"] = {}  # For new rating system
        recipe_dict["created_by"] = user_email  # Ensure consistency
        recipe_dict["created_at"] = datetime.now(timezone.utc)  # Add timestamp
        recipe_dict["updated_at"] = datetime.now(timezone.utc)

        result = await recipe_collection.insert_one(recipe_dict)
        if not result.inserted_id:
            raise HTTPException(status_code=500, detail="Failed to create recipe")
        
        logger.info(f"Recipe created by {user_email}: {result.inserted_id}")
        
        # ✅ Return data based on actual inserted document
        created_recipe = await recipe_collection.find_one({"_id": result.inserted_id})
        
        return RecipeOut(
            id=str(created_recipe["_id"]),
            name=created_recipe["name"],
            description=created_recipe.get("description", ""),
            ingredients=created_recipe["ingredients"],
            difficulty=created_recipe.get("difficulty", "medium"),
            image_url=created_recipe.get("image_url"),
            instructions=created_recipe["instructions"],
            dish_id=created_recipe["dish_id"],
            created_by=created_recipe["created_by"],
            ratings=[],
            average_rating=0.0
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create recipe for {user_email}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create recipe")


async def get_all_recipes_handler(skip: int = 0, limit: int = 20):
    """
    Lấy tất cả công thức (public) với pagination
    """
    # Validate pagination parameters
    if skip < 0:
        skip = 0
    if limit <= 0 or limit > 100:  # Prevent abuse
        limit = 20
    
    try:
        # Use projection for better performance
        projection = {
            "name": 1,
            "description": 1,
            "ingredients": 1,
            "difficulty": 1,
            "image_url": 1,
            "instructions": 1,
            "dish_id": 1,
            "created_by": 1,
            "ratings": 1,
            "user_ratings": 1,
            "average_rating": 1
        }
        recipes = await recipe_collection.find({}, projection).sort("_id", -1).skip(skip).limit(limit).to_list(length=limit)
    except Exception as e:
        logger.error(f"Failed to fetch recipes: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch recipes")
    
    return [
        RecipeOut(
            id=str(recipe["_id"]),
            name=recipe["name"],
            description=recipe.get("description", ""),
            ingredients=recipe["ingredients"],
            difficulty=recipe.get("difficulty", "medium"),
            image_url=recipe.get("image_url"),
            instructions=recipe["instructions"],
            dish_id=recipe["dish_id"],
            created_by=recipe["created_by"],
            # ✅ FIXED: Use validated ratings extraction
            ratings=extract_ratings_from_recipe(recipe),
            average_rating=recipe.get("average_rating", 0.0),
        )
        for recipe in recipes
    ]


async def get_recipe_handler(recipe_id: str):
    """
    Lấy công thức theo ID
    """
    recipe_oid = _validate_object_id(recipe_id, "recipe ID")

    try:
        recipe = await recipe_collection.find_one({"_id": recipe_oid})
        if not recipe:
            raise HTTPException(status_code=404, detail="Recipe not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch recipe {recipe_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch recipe")

    # ✅ FIXED: Handle both old and new rating format with validation
    ratings = extract_ratings_from_recipe(recipe)

    return RecipeOut(
        id=str(recipe["_id"]),
        name=recipe["name"],
        description=recipe.get("description", ""),
        ingredients=recipe["ingredients"],
        difficulty=recipe.get("difficulty", "medium"),
        image_url=recipe.get("image_url"),
        instructions=recipe["instructions"],
        dish_id=recipe["dish_id"],
        created_by=recipe["created_by"],
        ratings=ratings,
        average_rating=recipe.get("average_rating", 0.0),
    )


async def get_recipes_by_user_handler(decoded):
    """
    Lấy công thức của người dùng hiện tại
    """
    user_email = extract_user_email(decoded)
    
    try:
        user = await users_collection.find_one({"email": user_email})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Use projection for better performance
        projection = {
            "name": 1,
            "description": 1,
            "ingredients": 1,
            "difficulty": 1,
            "image_url": 1,
            "instructions": 1,
            "dish_id": 1,
            "created_by": 1,
            "ratings": 1,
            "user_ratings": 1,
            "average_rating": 1
        }
        recipes = await recipe_collection.find({"created_by": user_email}, projection).to_list(length=100)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch user recipes for {user_email}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch user recipes")
    
    return [
        RecipeOut(
            id=str(recipe["_id"]),
            name=recipe["name"],
            description=recipe.get("description", ""),
            ingredients=recipe["ingredients"],
            difficulty=recipe.get("difficulty", "medium"),
            image_url=recipe.get("image_url"),
            instructions=recipe["instructions"],
            dish_id=recipe["dish_id"],
            created_by=recipe["created_by"],
            # ✅ FIXED: Handle both rating formats with validation
            ratings=extract_ratings_from_recipe(recipe),
            average_rating=recipe.get("average_rating", 0.0),
        )
        for recipe in recipes
    ]


async def rate_recipe_handler(recipe_id: str, rating: int, decoded):
    """
    🔒 COMPLETELY ATOMIC rating operation to prevent race conditions
    Single atomic operation updates rating AND recalculates average
    """
    user_email = extract_user_email(decoded)
    validated_rating = validate_rating(rating)
    recipe_oid = _validate_object_id(recipe_id, "recipe ID")
    
    try:
        # 🔒 COMPLETELY ATOMIC: Single operation that:
        # 1. Sets user rating
        # 2. Uses MongoDB aggregation to recalculate average in same operation
        # 3. Prevents any race conditions
        
        result = await recipe_collection.find_one_and_update(
            {"_id": recipe_oid},
            [
                {
                    "$set": {
                        f"user_ratings.{user_email}": validated_rating,
                        "updated_at": "$$NOW"
                    }
                },
                {
                    "$set": {
                        # Recalculate ratings array from user_ratings
                        "ratings": {
                            "$map": {
                                "input": {"$objectToArray": "$user_ratings"},
                                "as": "rating",
                                "in": "$$rating.v"
                            }
                        }
                    }
                },
                {
                    "$set": {
                        # Recalculate average from new ratings array
                        "average_rating": {
                            "$cond": {
                                "if": {"$gt": [{"$size": "$ratings"}, 0]},
                                "then": {
                                    "$round": [
                                        {"$avg": "$ratings"},
                                        2
                                    ]
                                },
                                "else": 0.0
                            }
                        }
                    }
                }
            ],
            return_document=True
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Recipe not found")
        
        # Extract final average for response
        final_avg = result.get("average_rating", 0.0)
        
        logger.info(f"Recipe {recipe_id} rated by {user_email}: {validated_rating} (avg: {final_avg})")
        return {
            "msg": "Recipe rated successfully", 
            "average_rating": final_avg,
            "user_rating": validated_rating
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rate recipe {recipe_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to rate recipe")
