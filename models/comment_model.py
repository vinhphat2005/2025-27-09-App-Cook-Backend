# comment_model.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class CommentIn(BaseModel):
    dish_id: str
    recipe_id: Optional[str] = None
    parent_comment_id: Optional[str] = None
    rating: Optional[int] = Field(None, ge=1, le=5)     # <-- cho phép None nếu là reply
    content: str = Field(..., max_length=2000)

class CommentUpdate(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    content: Optional[str] = Field(None, max_length=2000)

class CommentOut(BaseModel):
    id: str
    dish_id: str
    recipe_id: Optional[str] = None
    parent_comment_id: Optional[str] = None
    user_id: str
    user_display_id: Optional[str] = None
    user_avatar: Optional[str] = None
    rating: int
    content: str
    likes: int = 0
    liked_by: Optional[list] = []  # New: track who liked for atomic operations
    created_at: datetime
    updated_at: Optional[datetime] = None

class CommentPermissionOut(BaseModel):
    """Model for comment permissions response"""
    owned: bool
    can_edit: bool
    can_delete: bool
