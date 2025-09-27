from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class DishIn(BaseModel):
    name: str
    cooking_time: int
    ingredients: List[str] = []
    # Ảnh do FE mã hóa -> gửi thẳng cho BE lưu
    image_b64: Optional[str] = None        # có/không có prefix data:...;base64,
    image_mime: Optional[str] = None       # ví dụ: "image/jpeg", "image/png"
    ratings: List[int] = Field(default_factory=list)
    average_rating: Optional[float] = 0.0
    liked_by: List[str] = Field(default_factory=list)

class Dish(DishIn):
    id: Optional[str] = Field(default=None, alias="_id")
    creator_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        validate_by_name = True  # nếu bạn đang dùng Pydantic v1

class DishOut(BaseModel):
    id: str
    name: str
    cooking_time: int
    average_rating: float

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        
