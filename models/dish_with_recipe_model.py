from pydantic import BaseModel
from typing import List, Optional

class DishWithRecipeIn(BaseModel):
 
    name: str
    image_url: Optional[str] = None          # Make optional
    image_b64: Optional[str] = None          # Add this
    image_mime: Optional[str] = None         # Add this
    ingredients: List[str]
    cooking_time: int
    
    # Thông tin recipe
    recipe_name: Optional[str] = None
    recipe_description: Optional[str] = ""
    recipe_ingredients: Optional[List[str]] = None
    difficulty: str = "medium"  
    instructions: List[str]
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Cơm chiên trứng",
                "image_url": "https://images.unsplash.com/photo-1603133872878-684f208fb84b",
                "ingredients": ["Cơm", "Trứng", "Hành lá", "Dầu ăn", "Nước mắm"],
                "cooking_time": 15,
                "recipe_description": "Món cơm chiên trứng đơn giản, nhanh gọn",
                "difficulty": "easy",
                "instructions": [
                    "Đập trứng vào bát, đánh đều",
                    "Bắc chảo lên bếp, cho dầu vào làm nóng",
                    "Đổ trứng vào chiên sơ, xới ra",
                    "Cho cơm vào đảo đều với trứng",
                    "Nêm nước mắm, tiêu vừa ăn",
                    "Rắc hành lá lên trên và tắt bếp"
                ]
            }
        }

class DishWithRecipeOut(BaseModel):
    dish_id: str
    recipe_id: str
    dish_name: str
    recipe_name: str
    message: str = "Dish and recipe created successfully"
