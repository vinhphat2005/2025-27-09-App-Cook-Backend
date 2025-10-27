from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

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

class RecipeDetailOut(BaseModel):
    id: str
    name: str
    instructions: List[str] = []
    cooking_time: int = 0
    difficulty: Optional[str] = None
    serves: int = 1
    creator_id: Optional[str] = None
    created_by: str = None
    dish_id: str = None
    ratings: list = []
    created_at: datetime = None

class DishWithRecipeDetailOut(BaseModel):
    dish: DishDetailOut
    recipe: Optional[RecipeDetailOut] = None