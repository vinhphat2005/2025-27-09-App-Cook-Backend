"""
Recipe Route Handlers - Extracted from routes/recipe_route.py
All recipe-related route handlers consolidated here
"""
from fastapi import HTTPException
from models.recipe_model import RecipeIn, RecipeOut
from database.mongo import recipe_collection, users_collection
from core.auth.dependencies import extract_user_email
from bson import ObjectId
from typing import List


# ==================== HELPER FUNCTIONS ====================

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
    Tạo công thức mới
    """
    user_email = extract_user_email(decoded)
    user = await users_collection.find_one({"email": user_email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # ✅ Prepare complete recipe data
    recipe_dict = recipe.dict()
    recipe_dict["ratings"] = []
    recipe_dict["average_rating"] = 0.0
    recipe_dict["user_ratings"] = {}  # For new rating system

    result = await recipe_collection.insert_one(recipe_dict)
    if not result.inserted_id:
        raise HTTPException(status_code=500, detail="Failed to create recipe")
    
    # ✅ Return consistent data
    return RecipeOut(
        id=str(result.inserted_id),
        **recipe.dict(),
        ratings=[],
        average_rating=0.0
    )


async def get_all_recipes_handler(skip: int = 0, limit: int = 20):
    """
    Lấy tất cả công thức (public) với pagination
    """
    if limit > 100:  # Prevent abuse
        limit = 100
    
    recipes = await recipe_collection.find().sort("_id", -1).skip(skip).limit(limit).to_list(length=limit)
    
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
    if not ObjectId.is_valid(recipe_id):
        raise HTTPException(status_code=400, detail="Invalid recipe ID")

    recipe = await recipe_collection.find_one({"_id": ObjectId(recipe_id)})
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

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
    user = await users_collection.find_one({"email": user_email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    recipes = await recipe_collection.find({"created_by": user_email}).to_list(length=100)
    
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
    Đánh giá công thức (thêm sao) - Validate 1-5 stars
    """
    user_email = extract_user_email(decoded)
    
    # ✅ FIXED: Use centralized validation
    validated_rating = validate_rating(rating)
    
    if not ObjectId.is_valid(recipe_id):
        raise HTTPException(status_code=400, detail="Invalid recipe ID")

    recipe = await recipe_collection.find_one({"_id": ObjectId(recipe_id)})
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # ✅ FIXED: Check if user already rated this recipe
    user_ratings = recipe.get("user_ratings", {})
    if user_email in user_ratings:
        # Update existing rating
        old_rating = user_ratings[user_email]
        user_ratings[user_email] = validated_rating
        
        # Recalculate average with validated ratings only
        ratings = extract_ratings_from_recipe({"user_ratings": user_ratings})
        avg = round(sum(ratings) / len(ratings), 2) if ratings else 0.0
        
        await recipe_collection.update_one(
            {"_id": ObjectId(recipe_id)},
            {"$set": {
                "user_ratings": user_ratings,
                "ratings": ratings,
                "average_rating": avg
            }}
        )
        return {"msg": f"Rating updated from {old_rating} to {validated_rating}", "average_rating": avg}
    else:
        # Add new rating
        user_ratings[user_email] = validated_rating
        ratings = extract_ratings_from_recipe({"user_ratings": user_ratings})
        avg = round(sum(ratings) / len(ratings), 2) if ratings else 0.0

        await recipe_collection.update_one(
            {"_id": ObjectId(recipe_id)},
            {"$set": {
                "user_ratings": user_ratings,
                "ratings": ratings,
                "average_rating": avg
            }}
        )
        return {"msg": "Recipe rated successfully", "average_rating": avg}
