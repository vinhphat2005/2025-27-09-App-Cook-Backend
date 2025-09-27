from pydantic import BaseModel, Field
from typing import Optional

# Model để nhập vào từ client 
class Ingredient(BaseModel):
    id: str = Field(alias="_id")
    name: str
    category: str  
    unit: Optional[str] = "gram"  # default unit

# Model để trả về từ API 
class IngredientOut(BaseModel):
    id: str
    name: str
    category: str
    unit: str
