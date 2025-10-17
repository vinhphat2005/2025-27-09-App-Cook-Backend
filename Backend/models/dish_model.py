from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

class DishIn(BaseModel):
    """Model for creating/updating dish - Only user input fields"""
    name: str
    cooking_time: int = Field(..., ge=1, le=1440, description="Cooking time in minutes (1-1440)")
    ingredients: List[str] = []
    # Ảnh do FE mã hóa -> gửi thẳng cho BE lưu
    image_b64: Optional[str] = None        # có/không có prefix data:...;base64,
    image_mime: Optional[str] = None       # ví dụ: "image/jpeg", "image/png"
    
    # Input validation
    @validator('name')
    def validate_name_length(cls, v):
        if len(v) > 200:
            raise ValueError('Dish name too long (max 200 characters)')
        return v.strip()  # Remove leading/trailing whitespace
    
    @validator('cooking_time')
    def validate_cooking_time(cls, v):
        if v < 1:
            raise ValueError('Cooking time must be positive')
        if v > 1440:  # 24 hours = 1440 minutes
            raise ValueError('Cooking time too long (max 24 hours)')
        return v
    
    @validator('ingredients')
    def validate_ingredients(cls, v):
        if len(v) > 50:
            raise ValueError('Too many ingredients (max 50)')
        
        # Clean up empty strings and whitespace
        cleaned = [ing.strip() for ing in v if ing and ing.strip()]
        
        if len(cleaned) == 0:
            raise ValueError('At least one ingredient is required')
        
        return cleaned

class Dish(BaseModel):
    """Internal model - Full document in database"""
    id: Optional[str] = Field(default=None, alias="_id")
    name: str
    cooking_time: int
    ingredients: List[str] = []
    image_b64: Optional[str] = None
    image_mime: Optional[str] = None
    
    # Backend-managed fields
    ratings: List[int] = Field(default_factory=list)
    user_ratings: Dict[str, int] = Field(default_factory=dict)  # {user_email: rating}
    average_rating: float = 0.0
    liked_by: List[str] = Field(default_factory=list)
    
    creator_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        validate_by_name = True  # nếu bạn đang dùng Pydantic v1

class DishOut(BaseModel):
    """Response model for dish data"""
    id: str
    name: str
    cooking_time: int
    ingredients: List[str] = []  # Frontend needs this to display ingredients
    average_rating: float
    user_ratings: Optional[Dict[str, int]] = Field(default_factory=dict)  # New: user rating mapping
    image_url: Optional[str] = None  # Cloudinary URL, not empty string default
    creator_id: Optional[str] = None
    created_at: Optional[datetime] = None
    liked_by: Optional[List[str]] = Field(default_factory=list)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True

# New models for specific requests
class DishRatingRequest(BaseModel):
    """Model for rating dish requests"""
    rating: int = Field(..., ge=1, le=5, description="Rating must be between 1 and 5 stars")

class DishLikeResponse(BaseModel):
    """Response model for like/unlike operations"""
    liked: bool
    total_likes: int
        
