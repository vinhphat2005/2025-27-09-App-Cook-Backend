from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class RatingCreate(BaseModel):
    recipe_id: str
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = ""

class RatingOut(RatingCreate):
    id: str = Field(alias="_id")
    user_id: str
    created_at: datetime
