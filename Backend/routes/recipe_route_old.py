from fastapi import APIRouter, Depends, HTTPException
from models.recipe_model import RecipeIn, RecipeOut
from database.mongo import recipe_collection, users_collection
from core.auth.dependencies import get_current_user, extract_user_email, get_user_by_email
from bson import ObjectId
from typing import List

router = APIRouter()

# Tạo công thức mới
@router.post("/", response_model=RecipeOut)
async def create_recipe(recipe: RecipeIn, decoded=Depends(get_current_user)):
    user_email = extract_user_email(decoded)
    # Lấy user để lấy _id
    user = await users_collection.find_one({"email": user_email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    recipe_dict = recipe.dict()
    recipe_dict["ratings"] = []
    recipe_dict["average_rating"] = 0.0
    recipe_dict["user_ratings"] = {} 

    result = await recipe_collection.insert_one(recipe_dict)
    if not result.inserted_id:
        raise HTTPException(status_code=500, detail="Failed to create recipe")
    
    return RecipeOut(
        id=str(result.inserted_id),
        **recipe.dict(),
        ratings=[],
        average_rating=0.0
    )

# Lấy tất cả công thức (public)
@router.get("/", response_model=List[RecipeOut])
async def get_all_recipes(skip: int = 0, limit: int = 20):
    """
    Lấy danh sách tất cả recipes với pagination
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
            ratings=list(recipe.get("user_ratings", {}).values()) or recipe.get("ratings", []),
            average_rating=recipe.get("average_rating", 0.0),
        )
        for recipe in recipes
    ]

# Lấy công thức theo ID
@router.get("/{recipe_id}", response_model=RecipeOut)
async def get_recipe(recipe_id: str):
    if not ObjectId.is_valid(recipe_id):
        raise HTTPException(status_code=400, detail="Invalid recipe ID")

    recipe = await recipe_collection.find_one({"_id": ObjectId(recipe_id)})
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    user_ratings = recipe.get("user_ratings", {})
    if user_ratings:
        ratings = list(user_ratings.values())
    else:
        ratings = recipe.get("ratings", [])

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

# Lấy công thức của người dùng hiện tại
@router.get("/by-user", response_model=List[RecipeOut])
async def get_recipes_by_user(decoded=Depends(get_current_user)):
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
            # ✅ FIXED: Handle both rating formats
            ratings=list(recipe.get("user_ratings", {}).values()) or recipe.get("ratings", []),
            average_rating=recipe.get("average_rating", 0.0),
        )
        for recipe in recipes
    ]



# Đánh giá công thức (thêm sao)
@router.post("/{recipe_id}/rate")
async def rate_recipe(recipe_id: str, rating: int, decoded=Depends(get_current_user)):
    user_email = extract_user_email(decoded)
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
    if not ObjectId.is_valid(recipe_id):
        raise HTTPException(status_code=400, detail="Invalid recipe ID")

    recipe = await recipe_collection.find_one({"_id": ObjectId(recipe_id)})
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # ✅ IMPROVED: Check if user already rated this recipe
    user_ratings = recipe.get("user_ratings", {})
    if user_email in user_ratings:
        # Update existing rating
        old_rating = user_ratings[user_email]
        user_ratings[user_email] = rating
        
        # Recalculate average
        ratings = list(user_ratings.values())
        avg = round(sum(ratings) / len(ratings), 2) if ratings else 0.0
        
        await recipe_collection.update_one(
            {"_id": ObjectId(recipe_id)},
            {"$set": {
                "user_ratings": user_ratings,
                "ratings": ratings,
                "average_rating": avg
            }}
        )
        return {"msg": f"Rating updated from {old_rating} to {rating}", "average_rating": avg}
    else:
        # Add new rating
        user_ratings[user_email] = rating
        ratings = list(user_ratings.values())
        avg = round(sum(ratings) / len(ratings), 2)

        await recipe_collection.update_one(
            {"_id": ObjectId(recipe_id)},
            {"$set": {
                "user_ratings": user_ratings,
                "ratings": ratings,
                "average_rating": avg
            }}
        )
        return {"msg": "Recipe rated successfully", "average_rating": avg}
