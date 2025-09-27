"""
User Management Routes - Simplified Main Router
All handlers moved to utils.user_handlers for better organization
"""
from pydantic import BaseModel
from typing import Literal,Optional
from fastapi import APIRouter, Depends, Body
from models.user_model import UserOut
from main_async import user_activity_col  # đã init trong main_async.py (motor)
from core.auth.dependencies import get_current_user
from datetime import datetime, timezone
from utils.user_handlers import (
    # Profile handlers
    create_user_handler,
    get_user_handler, 
    get_me_handler,
    update_me_handler,
    search_users_handler,
    get_my_favorites_handler,
    
    # Social handlers
    get_my_social_handler,
    follow_user_handler,
    get_user_dishes_handler,
    
    # Activity handlers
    get_my_activity_handler,
    add_cooked_dish_handler,
    add_viewed_dish_handler,
    notify_favorite_handler,
    get_viewed_dishes_handler,

    # Preferences handlers
    get_my_notifications_handler,
    set_reminders_handler,
    get_reminders_handler
)
from typing import List

# Main router
router = APIRouter()

# ==================== PROFILE ROUTES ====================
@router.post("/", response_model=UserOut)
async def create_user(decoded=Depends(get_current_user)):
    return await create_user_handler(decoded)

@router.get("/me", response_model=UserOut)
async def get_me(decoded=Depends(get_current_user)):
    return await get_me_handler(decoded)

@router.put("/me", response_model=UserOut)
async def update_me(user_update: dict = Body(...), decoded=Depends(get_current_user)):
    return await update_me_handler(user_update, decoded)

@router.get("/search/")
async def search_users(q: str, decoded=Depends(get_current_user)):
    return await search_users_handler(q, decoded)

@router.get("/{user_id}", response_model=UserOut) 
async def get_user(user_id: str):
    return await get_user_handler(user_id)

@router.get("/me/favorites")
async def get_my_favorites(decoded=Depends(get_current_user)):
    return await get_my_favorites_handler(decoded)

# ==================== SOCIAL ROUTES ====================
@router.get("/me/social")
async def get_my_social(decoded=Depends(get_current_user)):
    return await get_my_social_handler(decoded)

@router.post("/{user_id}/follow")
async def follow_user(user_id: str, decoded=Depends(get_current_user)):
    return await follow_user_handler(user_id, decoded)

@router.get("/{user_id}/dishes")
async def get_user_dishes(user_id: str):
    return await get_user_dishes_handler(user_id)

# ==================== ACTIVITY ROUTES ====================

@router.post("/me/cooked/{dish_id}")
async def add_cooked_dish(dish_id: str, decoded=Depends(get_current_user)):
    return await add_cooked_dish_handler(dish_id, decoded)

# @router.post("/me/viewed/{dish_id}")
# async def add_viewed_dish(dish_id: str, decoded=Depends(get_current_user)):
#     return await add_viewed_dish_handler(dish_id, decoded)

# @router.get("/me/viewed-dishes")
# async def get_viewed_dishes(limit: int = 20, decoded=Depends(get_current_user)):
#     return await get_viewed_dishes_handler(limit, decoded)

@router.post("/notify-favorite/{dish_id}")
async def notify_favorite(dish_id: str):
    return await notify_favorite_handler(dish_id)

# ==================== PREFERENCES ROUTES ====================
@router.get("/me/notifications")
async def get_my_notifications(decoded=Depends(get_current_user)):
    return await get_my_notifications_handler(decoded)

@router.post("/me/reminders")
async def set_reminders(reminders: List[str] = Body(...), decoded=Depends(get_current_user)):
    return await set_reminders_handler(reminders, decoded)

@router.get("/me/reminders", response_model=List[str])
async def get_reminders(decoded=Depends(get_current_user)):
    return await get_reminders_handler(decoded)



class ViewEventIn(BaseModel):
    type: Literal["dish", "user"]
    target_id: str
    name: Optional[str] = ""     # FE có thể gửi kèm để hiển thị nhanh
    image: Optional[str] = ""    # URL hoặc data:image/...;base64,...
    timestamp: Optional[datetime] = None  # nếu không gửi sẽ dùng now()

MAX_HISTORY = 50  # giới hạn lịch sử

# ====== SỬA ROUTE LƯU LỊCH SỬ (chỉ thay nội dung bên trong) ======
@router.post("/activity/view")
async def add_view_history(payload: ViewEventIn, decoded=Depends(get_current_user)):
    """
    Lưu 1 entry vào lịch sử xem của user.
    Bây giờ lưu dạng OBJECT: {type, id, name, image, ts}
    - Không trùng: nếu đã có (cùng type+id) thì kéo lên đầu và cập nhật snapshot.
    - Giới hạn: giữ tối đa MAX_HISTORY phần tử.
    """
    uid = decoded["uid"]
    now = datetime.now(timezone.utc)

    # Chuẩn hóa record để lưu
    doc = {
        "type": payload.type,
        "id": payload.target_id,
        "name": payload.name or "",
        "image": payload.image or "",
        "ts": payload.timestamp or now,
    }


    await user_activity_col.update_one(
        {"user_id": uid},
        {"$pull": {"viewed_dishes_and_users": {"type": doc["type"], "id": doc["id"]}}},
        upsert=True
    )

    # 2) Đẩy item mới lên đầu + cắt danh sách
    await user_activity_col.update_one(
        {"user_id": uid},
        {
            "$push": {
                "viewed_dishes_and_users": {
                    "$each": [doc],
                    "$position": 0,
                    "$slice": MAX_HISTORY
                }
            },
            "$set": {"updated_at": now}
        },
        upsert=True
    )

    return {"ok": True, "added": doc}

from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class ViewEventOut(BaseModel):
    type: Literal["dish", "user"]
    id: str
    name: Optional[str] = ""
    image: Optional[str] = ""  
    ts: Optional[datetime] = None

def _normalize_view_entry(it: Any) -> Optional[Dict[str, Any]]:
    """Hỗ trợ cả định dạng cũ (string 'dish:<id>') lẫn định dạng mới (object)."""
    if isinstance(it, str):
        parts = it.split(":")
        if len(parts) >= 2 and parts[0] in ("dish", "user"):
            return {"type": parts[0], "id": ":".join(parts[1:])}
        return None
    if isinstance(it, dict) and it.get("type") in ("dish", "user") and it.get("id"):
        return {
            "type": it["type"],
            "id": str(it["id"]),
            "name": it.get("name", "") or "",
            "image": it.get("image", "") or "",
            "ts": it.get("ts"),
        }
    return None

@router.get("/activity/view")
async def get_view_history(limit: int = 50, decoded=Depends(get_current_user)):
    """
    Trả về lịch sử đã xem (mới nhất nằm đầu).
    Giữ tương thích ngược: chấp nhận cả string 'dish:<id>' và object {type,id,...}.
    """
    uid = decoded["uid"]

    doc = await user_activity_col.find_one(
        {"user_id": uid},
        {"_id": 0, "viewed_dishes_and_users": 1}
    )

    raw = (doc or {}).get("viewed_dishes_and_users", [])
    items: List[Dict[str, Any]] = []

    for it in raw:
        norm = _normalize_view_entry(it)
        if norm:
            items.append(norm)

    # raw đã được push theo thứ tự mới nhất ở đầu; cắt theo limit
    if limit and limit > 0:
        items = items[:limit]

    return {"items": items, "count": len(items)}