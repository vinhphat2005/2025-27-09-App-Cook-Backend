"""
Recipe Management Routes - Simplified Main Router
All handlers moved to utils.recipe_handlers for better organization
"""
from fastapi import APIRouter, Depends, Body
from models.recipe_model import RecipeIn, RecipeOut
from core.auth.dependencies import get_current_user
from utils.recipe_handlers import (
    create_recipe_handler,
    get_all_recipes_handler,
    get_recipe_handler,
    get_recipes_by_user_handler,
    rate_recipe_handler
)
from typing import List

router = APIRouter()

# ==================== RECIPE ROUTES ====================
@router.post("/", response_model=RecipeOut)
async def create_recipe(recipe: RecipeIn, decoded=Depends(get_current_user)):
    return await create_recipe_handler(recipe, decoded)

@router.get("/", response_model=List[RecipeOut])
async def get_all_recipes(skip: int = 0, limit: int = 20):
    return await get_all_recipes_handler(skip, limit)

@router.get("/by-user", response_model=List[RecipeOut])
async def get_recipes_by_user(decoded=Depends(get_current_user)):
    return await get_recipes_by_user_handler(decoded)

@router.get("/{recipe_id}", response_model=RecipeOut)
async def get_recipe(recipe_id: str):
    return await get_recipe_handler(recipe_id)

@router.post("/{recipe_id}/rate")
async def rate_recipe(recipe_id: str, rating: int, decoded=Depends(get_current_user)):
    return await rate_recipe_handler(recipe_id, rating, decoded)
