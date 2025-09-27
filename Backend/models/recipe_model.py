from pydantic import BaseModel, Field, validator
from typing import List, Optional
from bson import ObjectId

class RecipeIn(BaseModel):
    name: str
    description: Optional[str] = ""
    ingredients: List[str]
    difficulty: str = "medium"
    image_url: Optional[str] = None
    instructions: List[str]
    dish_id: str  # Đây là id của Dish cha (string ObjectId)
    created_by: str  # Email hoặc user ID

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
    average_rating: Optional[float] = 0.0

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
    average_rating: Optional[float] = 0.0

    @validator("id", pre=True, always=True)
    def convert_objectid(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v

    class Config:
        validate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}