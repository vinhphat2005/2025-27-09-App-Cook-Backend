from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime

class RatingRequest(BaseModel):
    """Model for rating recipe requests"""
    rating: int = Field(..., ge=1, le=5, description="Rating must be between 1 and 5 stars")

class RecipeIn(BaseModel):
    name: str
    description: Optional[str] = ""
    ingredients: List[str]
    difficulty: str = "medium"
    image_url: Optional[str] = None
    instructions: List[str]
    dish_id: str  # Đây là id của Dish cha (string ObjectId)
    created_by: str  # Email hoặc user ID
    
    # Validation for input sanitization
    @validator('instructions')
    def validate_instructions_length(cls, v):
        instructions_text = ' '.join(v) if isinstance(v, list) else str(v)
        if len(instructions_text) > 5000:
            raise ValueError('Instructions too long (max 5000 characters)')
        return v
    
    @validator('ingredients')
    def validate_ingredients_count(cls, v):
        if len(v) > 50:
            raise ValueError('Too many ingredients (max 50)')
        return v

class Recipe(BaseModel):
    name: str
    description: Optional[str] = ""
    ingredients: List[str]
    difficulty: str = "medium"
    image_url: Optional[str] = None
    instructions: List[str]
    dish_id: str
    created_by: str
    ratings: Optional[List[int]] = Field(default_factory=list)
    user_ratings: Optional[Dict[str, int]] = Field(default_factory=dict)  # New: {email: rating}
    average_rating: Optional[float] = 0.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        arbitrary_types_allowed = True
        validate_by_name = True
        json_schema_extra = {
            "example": {
                "name": "Fried Rice",
                "description": "A quick and tasty dish.",
                "ingredients": ["rice", "egg", "carrot", "peas"],
                "difficulty": "easy",
                "image_url": "https://example.com/image.jpg",
                "instructions": ["Boil rice", "Stir fry vegetables", "Mix everything"],
                "dish_id": "abc123dishid",
                "created_by": "user@example.com"
            }
        }

class RecipeOut(BaseModel):
    id: str = Field(alias="_id")
    name: str
    description: Optional[str]
    ingredients: List[str]
    difficulty: str
    image_url: Optional[str]
    instructions: List[str]
    dish_id: str
    created_by: str
    ratings: Optional[List[int]] = Field(default_factory=list)
    user_ratings: Optional[Dict[str, int]] = Field(default_factory=dict)  # New: user rating mapping
    average_rating: Optional[float] = 0.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @validator("id", pre=True, always=True)
    def convert_objectid(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v

    class Config:
        validate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}