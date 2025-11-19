"""
# routes/recommendation_route.py
# Simplified: keep only a paginated /trending feed sorted by rating desc then recency.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from database.mongo import get_database

router = APIRouter()


class DishRecommendation(BaseModel):
    dish_id: str
    name: str
    description: Optional[str]
    image_url: Optional[str]
    category: Optional[str]
    cuisine_type: Optional[str]
    difficulty: Optional[str]
    cooking_time: Optional[int]
    average_rating: float
    like_count: int
    cook_count: int
    view_count: int
    score: float
    reason: str
    similarity_reason: Optional[str] = None
    ingredients: Optional[List[str]] = None  # ✅ Add ingredients list


class RecommendationResponse(BaseModel):
    recommendations: List[DishRecommendation]
    total: int
    algorithm: str
    generated_at: datetime
    metadata: Optional[dict] = None


@router.get("/trending", response_model=RecommendationResponse)
async def get_trending_dishes(
    days: int = Query(7, ge=1, le=30, description="Window for trending (unused)"),
    limit: int = Query(6, ge=1, le=100, description="Number of items per page (default 6)"),
    offset: int = Query(0, ge=0, description="Pagination offset (skip X items)"),
    min_rating: float = Query(0, ge=0, le=5, description="Minimum rating filter (0 = none)"),
    db = Depends(get_database)
):
    """Return a paginated feed of dishes sorted by average_rating desc then created_at desc.

    This endpoint is intentionally minimal — no personalized logic.
    """
    try:
        match_query = {"is_active": True}
        if min_rating and min_rating > 0:
            match_query["average_rating"] = {"$gte": min_rating}

        cursor = (
            db.dishes
            .find(match_query)
            .sort([
                ("average_rating", -1),
                ("created_at", -1),
                ("_id", -1),
            ])
            .skip(offset)
            .limit(limit)
        )

        paginated = await cursor.to_list(length=limit)
        total_available = await db.dishes.count_documents(match_query)

        recommendations = []
        for dish in paginated:
            rating = round(dish.get("average_rating", 0) or 0, 2)
            recommendations.append(
                DishRecommendation(
                    dish_id=str(dish.get("_id")),
                    name=dish.get("name", ""),
                    description=dish.get("description", ""),
                    image_url=dish.get("image_url", ""),
                    category=dish.get("category", ""),
                    cuisine_type=dish.get("cuisine_type", ""),
                    difficulty=dish.get("difficulty", ""),
                    cooking_time=dish.get("cooking_time", 0),
                    average_rating=rating,
                    like_count=dish.get("like_count", 0),
                    cook_count=dish.get("cook_count", 0),
                    view_count=dish.get("view_count", 0),
                    score=round(rating / 5.0, 3) if rating > 0 else 0,
                    reason=(f"⭐ {rating:.1f} sao" if rating > 0 else "🆕 Món mới"),
                    similarity_reason=None,
                    ingredients=dish.get("ingredients", []),  # ✅ Include ingredients
                )
            )

        return RecommendationResponse(
            recommendations=recommendations,
            total=total_available,
            algorithm="feed_by_rating_and_recency",
            generated_at=datetime.utcnow(),
            metadata={
                "offset": offset,
                "limit": limit,
                "total_available": total_available,
                "returned": len(recommendations),
                "has_more": (offset + len(recommendations)) < total_available,
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching dishes: {str(e)}")