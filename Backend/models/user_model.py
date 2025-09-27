from pydantic import BaseModel, EmailStr, Field 
from typing import List, Optional
from datetime import datetime

class UserCreate(BaseModel):
    email: EmailStr
    display_id: str
    password: str

class UserOut(BaseModel):
    id: Optional[str]
    email: EmailStr
    display_id: str
    firebase_uid: Optional[str] = None
    name: Optional[str] = ""
    avatar: Optional[str] = ""
    bio: Optional[str] = ""
    created_at: Optional[datetime] = None
    last_active: Optional[datetime] = None

# Model cho social connections (followers/following)
class UserSocial(BaseModel):
    user_id: str
    followers: List[str] = []
    following: List[str] = []
    follower_count: int = 0
    following_count: int = 0

# Model cho user activity history  
class UserActivity(BaseModel):
    user_id: str
    favorite_dishes: List[str] = [] 
    cooked_dishes: List[str] = []
    viewed_dishes_and_users: List[str] = []
    created_recipes: List[str] = []
    created_dishes: List[str] = []

# Model cho notifications
class UserNotifications(BaseModel):
    user_id: str
    notifications: List[dict] = []  # {type, message, created_at, read}
    unread_count: int = 0

# Model cho user preferences
class UserPreferences(BaseModel):
    user_id: str
    reminders: List[str] = []  # ["07:00", "18:30"]
    dietary_restrictions: List[str] = []  # ["vegetarian", "gluten-free"]
    cuisine_preferences: List[str] = []  # ["vietnamese", "italian"]
    difficulty_preference: str = "all"  # "easy", "medium", "hard", "all"