"""
Search Routes - Find ingredients, users, dishes with filters
"""
from fastapi import APIRouter, Query, HTTPException
from bson.objectid import ObjectId
from database.mongo import ingredients_collection, recipe_collection, users_collection, dishes_collection
from models.ingredients_model import IngredientOut
from models.recipe_model import RecipeOut
from models.user_model import UserOut
from models.dish_model import DishOut
from core.user_management.service import user_helper


router = APIRouter()


# ================== BASIC SEARCH ==================

@router.get("/ingredients", response_model=list[IngredientOut])
async def search_ingredients(q: str = Query(..., min_length=1)):
    """
    Tìm kiếm nguyên liệu theo tên
    """
    regex = {"$regex": q, "$options": "i"}
    cursor = ingredients_collection.find({"name": regex}).limit(10)
    ingredients = await cursor.to_list(length=10)
    return [
        {
            "id": str(i["_id"]),
            "name": i["name"],
            "category": i.get("category", "unknown"),
            "unit": i.get("unit", "gram")
        } for i in ingredients
    ]


@router.get("/users", response_model=list[UserOut])
async def search_users(q: str = Query(..., min_length=1)):
    """
    Tìm kiếm người dùng theo display_id
    """
    regex = {"$regex": q, "$options": "i"}
    cursor = users_collection.find({"display_id": regex}).limit(10)
    users = await cursor.to_list(length=10)
    
    # Sử dụng user_helper để format consistent với normalized structure
    return [user_helper(u) for u in users]


@router.get("/dishes", response_model=list[DishOut])
async def search_dishes(q: str = Query(..., min_length=1)):
    """
    Tìm kiếm món ăn theo tên hoặc nguyên liệu
    """
    regex = {"$regex": q, "$options": "i"}
    cursor = dishes_collection.find({
        "$or": [
            {"name": regex},
            {"ingredients": {"$elemMatch": {"$regex": q, "$options": "i"}}}
        ]
    }).limit(10)
    dishes = await cursor.to_list(length=10)
    return [
        {
            "id": str(d["_id"]),
            "name": d["name"],
            "image_url": d.get("image_url", ""),
            "cooking_time": d.get("cooking_time", 0),
            "average_rating": d.get("average_rating", 0.0)
        } for d in dishes
    ]


@router.get("/recipes", response_model=list[RecipeOut])
async def search_recipes(q: str = Query(..., min_length=1)):
    """
    Tìm kiếm công thức theo tên hoặc mô tả
    """
    regex = {"$regex": q, "$options": "i"}
    cursor = recipe_collection.find({
        "$or": [
            {"name": regex},
            {"description": regex}
        ]
    }).limit(10)
    recipes = await cursor.to_list(length=10)
    return [
        {
            "id": str(r["_id"]),
            "name": r["name"],
            "description": r.get("description", ""),
            "ingredients": r.get("ingredients", []),
            "difficulty": r.get("difficulty", "medium"),
            "image_url": r.get("image_url"),
            "instructions": r.get("instructions", []),
            "dish_id": r.get("dish_id", ""),
            "created_by": r.get("created_by", ""),
            "ratings": r.get("ratings", []),
            "average_rating": r.get("average_rating", 0.0)
        } for r in recipes
    ]


# ================== ADVANCED FILTERS ==================

@router.get("/dishes/by-time", response_model=list[DishOut])
async def filter_dishes_by_time(
    max_time: int = Query(..., description="Thời gian nấu tối đa (phút)", ge=1)
):
    """
    Lọc món ăn theo thời gian nấu
    """
    cursor = dishes_collection.find({"cooking_time": {"$lte": max_time}})
    dishes = await cursor.to_list(length=50)
    return [
        DishOut(
            id=str(d.get("_id", "")),
            name=d.get("name", ""),
            image_url=d.get("image_url", ""),
            cooking_time=d.get("cooking_time", 0),
            average_rating=d.get("average_rating", 0.0),
        )
        for d in dishes
    ]


@router.get("/dishes/by-time-rating", response_model=list[DishOut])
async def filter_dishes_by_time_rating(
    max_time: int = Query(..., description="Thời gian nấu tối đa (phút)", ge=1),
    min_rating: float = Query(0.0, description="Rating tối thiểu", ge=0.0, le=5.0)
):
    """
    Lọc món ăn theo thời gian nấu và rating
    """
    cursor = dishes_collection.find({
        "cooking_time": {"$lte": max_time},
        "average_rating": {"$gte": min_rating}
    })
    dishes = await cursor.to_list(length=50)
    return [
        DishOut(
            id=str(d.get("_id", "")),
            name=d.get("name", ""),
            image_url=d.get("image_url", ""),
            cooking_time=d.get("cooking_time", 0),
            average_rating=d.get("average_rating", 0.0),
        )
        for d in dishes
    ]


@router.get("/dishes/by-difficulty", response_model=list[DishOut])
async def filter_dishes_by_difficulty(
    difficulty: str = Query(..., description="Độ khó: easy, medium, hard")
):
    """
    Lọc món ăn theo độ khó
    """
    if difficulty not in ["easy", "medium", "hard"]:
        raise HTTPException(status_code=400, detail="Invalid difficulty level")
    
    cursor = dishes_collection.find({"difficulty": difficulty})
    dishes = await cursor.to_list(length=50)
    return [
        DishOut(
            id=str(d.get("_id", "")),
            name=d.get("name", ""),
            image_url=d.get("image_url", ""),
            cooking_time=d.get("cooking_time", 0),
            average_rating=d.get("average_rating", 0.0),
        )
        for d in dishes
    ]


# ================== COMBINED SEARCH ==================

# ✅ Cập nhật search_all function
@router.get("/all")
async def search_all(q: str = Query(..., min_length=2)):
    """
    Tìm kiếm tổng hợp - tất cả loại data
    """
    regex = {"$regex": q, "$options": "i"}
    
    dishes_cursor = dishes_collection.find({
        "$or": [
            {"name": regex},
            {"ingredients": {"$elemMatch": {"$regex": q, "$options": "i"}}}
        ]
    }).limit(5)
    dishes = await dishes_cursor.to_list(length=5)
    
  
    users_cursor = users_collection.find({"display_id": regex}).limit(5)
    users = await users_cursor.to_list(length=5)
    

    ingredients_cursor = ingredients_collection.find({"name": regex}).limit(5)
    ingredients = await ingredients_cursor.to_list(length=5)
    
    return {
        "dishes": [
            {
                "id": str(d["_id"]),
                "name": d["name"],
                "type": "dish",
                "image_url": d.get("image_url", ""),
                "cooking_time": d.get("cooking_time", 0),
                "ingredients": d.get("ingredients", [])  
            } for d in dishes
        ],
        "users": [
            {
                "id": str(u["_id"]),
                "name": u.get("name", u["display_id"]),
                "type": "user",
                "display_id": u["display_id"],
                "avatar": u.get("avatar", "")
            } for u in users
        ],
        "ingredients": [
            {
                "id": str(i["_id"]),
                "name": i["name"],
                "type": "ingredient",
                "category": i.get("category", "")
            } for i in ingredients
        ],
        "total_results": len(dishes) + len(users) + len(ingredients)
    }

# Cập nhật endpoint dishes-by-ingredients
@router.get("/dishes-by-ingredients")
async def search_dishes_by_ingredients(
    ingredients: str = Query("", description="Comma-separated ingredients")
):
    """
    Tìm món ăn theo nhiều nguyên liệu (GET với query params)
    """
    # Parse ingredients từ string
    ingredient_list = [ing.strip() for ing in ingredients.split(',') if ing.strip()]
    
    if not ingredient_list:
        return {"dishes": [], "total_results": 0}
    
    # ✅ Sửa query syntax
    or_conditions = []
    for ing in ingredient_list:
        or_conditions.append({"ingredients": {"$regex": ing, "$options": "i"}})
    
    # Tìm dishes có chứa ít nhất 1 ingredient
    cursor = dishes_collection.find({
        "$or": or_conditions
    })
    
    dishes = await cursor.to_list(length=50)
    
    # Sắp xếp theo số lượng ingredients khớp
    scored_dishes = []
    for dish in dishes:
        dish_ingredients = dish.get("ingredients", [])
        match_count = sum(1 for ing in ingredient_list 
                         if any(ing.lower() in d_ing.lower() for d_ing in dish_ingredients))
        
        scored_dishes.append({
            "id": str(dish["_id"]),
            "name": dish["name"],
            "image_url": dish.get("image_url", ""),
            "cooking_time": dish.get("cooking_time", 0),
            "average_rating": dish.get("average_rating", 0.0),
            "ingredients": dish_ingredients,
            "match_count": match_count,
            "match_percentage": (match_count / len(ingredient_list)) * 100
        })
    
    # Sắp xếp theo độ khớp giảm dần
    scored_dishes.sort(key=lambda x: x["match_count"], reverse=True)
    
    return {
        "dishes": scored_dishes[:20],
        "total_results": len(scored_dishes),
        "search_ingredients": ingredient_list
    }