# routes/comment_route.py
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from bson import ObjectId
from pydantic import BaseModel, Field
from core.auth.dependencies import get_current_user
from main_async import db
from starlette.responses import Response
from fastapi import Request
router = APIRouter(prefix="/comments", tags=["Comments"])

comments_col = db["comments"]
dishes_col = db["dishes"]

# ================== Models ==================
class CommentPermissionOut(BaseModel):
    owned: bool
    can_edit: bool
    can_delete: bool

class CommentIn(BaseModel):
    dish_id: str
    recipe_id: Optional[str] = None
    parent_comment_id: Optional[str] = None
    rating: Optional[int] = Field(None, ge=1, le=5)  # Cho phép None nếu là reply
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
    created_at: datetime
    updated_at: Optional[datetime] = None
    isLiked: Optional[bool] = None
    replies: Optional[List['CommentOut']] = None
    can_edit: Optional[bool] = None  # Thêm để FE biết có thể edit không

# ================== Helpers ==================

def oid(s: str) -> ObjectId:
    try:
        return ObjectId(s)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ObjectId")

def to_out(doc: Dict[str, Any], current_user_id: Optional[str] = None) -> CommentOut:
    d = {**doc, "id": str(doc["_id"])}
    d.pop("_id", None)

    liked_by = doc.get("liked_by", []) or []
    is_liked = bool(current_user_id and current_user_id in liked_by)

    d["isLiked"] = is_liked
    print(f"current_user_id: '{current_user_id}', doc_user_id: '{doc.get('user_id')}', equal: {current_user_id == doc.get('user_id')}")
    d["can_edit"] = bool(current_user_id and doc.get("user_id") == current_user_id)

    return CommentOut(**d)


    owned = (c.get("user_id") == user_id)
    # Nếu sau này có role admin/moderator thì có thể mở rộng ở đây
    can_edit = owned
    can_delete = owned

    return CommentPermissionOut(owned=owned, can_edit=can_edit, can_delete=can_delete)

@router.head("/{comment_id}/permissions")
async def head_comment_permissions(comment_id: str, decoded=Depends(get_current_user)):
    """
    Trả về:
    - 204 nếu có quyền edit/delete (là chủ sở hữu)
    - 403 nếu không có quyền
    - 404 nếu không tồn tại
    - 401 nếu chưa đăng nhập
    """
    user_id = decoded["uid"]

    try:
        c = await comments_col.find_one({"_id": oid(comment_id)}, {"_id": 1, "user_id": 1})
    except HTTPException:
        raise

    if not c:
        raise HTTPException(status_code=404, detail="Comment not found")

    if c.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Có quyền
    return Response(status_code=204)
# dependency: cho phép không có token
async def current_user_optional(request: Request):
    try:
        user = await get_current_user(request)
        print(f"=== current_user_optional SUCCESS: {user} ===")
        return user
    except Exception as e:
        print(f"=== current_user_optional FAILED: {e} ===")
        return None
async def ensure_indexes():
    await comments_col.create_index([("dish_id", 1), ("created_at", -1)])
    await comments_col.create_index([("parent_comment_id", 1), ("created_at", 1)])
    await comments_col.create_index([("user_id", 1), ("created_at", -1)])
    # Index để kiểm tra duplicate rating
    await comments_col.create_index([("dish_id", 1), ("user_id", 1), ("parent_comment_id", 1)])

async def recalc_dish_rating(dish_id: str):
    """
    Chỉ tính trung bình từ comment gốc (parent_comment_id rỗng/None và rating > 0).
    """
    pipeline = [
        {"$match": {
            "dish_id": dish_id,
            "$or": [{"parent_comment_id": None}, {"parent_comment_id": ""}],
            "rating": {"$gt": 0}
        }},
        {"$group": {"_id": "$dish_id", "count": {"$sum": 1}, "avg": {"$avg": "$rating"}}},
    ]
    agg = comments_col.aggregate(pipeline)
    stats = await agg.to_list(length=1)
    if stats:
        s = stats[0]
        await dishes_col.update_one(
            {"_id": ObjectId(dish_id)},
            {"$set": {"average_rating": float(s["avg"]), "comments_count": int(s["count"])}},
            upsert=False,
        )
    else:
        await dishes_col.update_one(
            {"_id": ObjectId(dish_id)},
            {"$set": {"average_rating": 0.0, "comments_count": 0}},
            upsert=False,
        )

# ================== Routes ==================

@router.on_event("startup")
async def _on_startup():
    await ensure_indexes()

@router.post("/", response_model=CommentOut)
async def create_comment(payload: CommentIn, decoded=Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    user_id = decoded["uid"]
    user_display_id = decoded.get("email", "").split("@")[0] if decoded.get("email") else None
    user_avatar = decoded.get("picture")

    # Kiểm tra dish tồn tại
    try:
        dish_oid = ObjectId(payload.dish_id)
    except Exception:
        raise HTTPException(400, "Invalid dish_id")
    dish_exists = await dishes_col.find_one({"_id": dish_oid}, {"_id": 1})
    if not dish_exists:
        raise HTTPException(404, detail="Dish not found")

    # Kiểm tra parent comment nếu có
    if payload.parent_comment_id:
        try:
            _ = ObjectId(payload.parent_comment_id)
        except Exception:
            raise HTTPException(400, "Invalid parent_comment_id")
        parent = await comments_col.find_one({"_id": ObjectId(payload.parent_comment_id)}, {"_id": 1, "dish_id": 1})
        if not parent:
            raise HTTPException(404, "Parent comment not found")
        if parent["dish_id"] != payload.dish_id:
            raise HTTPException(400, "Parent comment dish mismatch")
        
        # Nếu là reply -> rating mặc định 0 (không tính avg)
        rating_val = 0
    else:
        # Nếu là comment gốc -> kiểm tra user đã rate món này chưa
        existing_rating = await comments_col.find_one({
            "dish_id": payload.dish_id,
            "user_id": user_id,
            "$or": [{"parent_comment_id": None}, {"parent_comment_id": ""}],
            "rating": {"$gt": 0}
        })
        
        if existing_rating:
            raise HTTPException(400, detail="Bạn đã đánh giá món ăn này rồi. Bạn có thể chỉnh sửa bình luận cũ của mình.")
        
        # Rating bắt buộc cho comment gốc
        if payload.rating is None or payload.rating <= 0:
            raise HTTPException(400, detail="Vui lòng chọn số sao đánh giá (1-5)")
        rating_val = int(payload.rating)

    doc = {
        "dish_id": payload.dish_id,
        "recipe_id": payload.recipe_id,
        "parent_comment_id": payload.parent_comment_id,
        "user_id": user_id,
        "user_display_id": user_display_id,
        "user_avatar": user_avatar,
        "rating": rating_val,
        "content": payload.content,
        "liked_by": [],  # Array chứa user_id đã like
        "likes": 0,      # Số lượng likes
        "created_at": now,
        "updated_at": None,
    }

    res = await comments_col.insert_one(doc)
    doc["_id"] = res.inserted_id

    # Chỉ recalc cho comment gốc
    if not payload.parent_comment_id:
        await recalc_dish_rating(payload.dish_id)

    return to_out(doc, user_id)

@router.get("/by-dish/{dish_id}")
async def list_comments_by_dish(
    dish_id: str,
    parent_comment_id: Optional[str] = Query(default=None, description="Để lấy reply của 1 comment, truyền id comment cha"),
    limit: int = Query(default=10, description="Số comment tối đa trả về; truyền 0 để lấy tất cả"),
    skip: int = 0,
    decoded=Depends(current_user_optional)
):
    user_id = decoded.get("uid") if decoded else None
    
    # Query main comments
    q: Dict[str, Any] = {"dish_id": dish_id}
    if parent_comment_id is None:
        q["$or"] = [{"parent_comment_id": None}, {"parent_comment_id": ""}]
    else:
        q["parent_comment_id"] = parent_comment_id

    cursor = comments_col.find(q).sort("created_at", -1).skip(skip)

    if limit > 0:
        cursor = cursor.limit(limit)

    items: List[CommentOut] = []
    async for c in cursor:
        # Convert main comment
        comment_out = to_out(c, user_id)
        
        # Load replies if it's a main comment
        if not c.get("parent_comment_id"):
            reply_cursor = comments_col.find({
                "parent_comment_id": str(c["_id"])  # ← Đây là chỗ ĐÚNG
            }).sort("created_at", 1)
            # Thử cả ObjectId và string để đảm bảo
            comment_id_str = str(c["_id"])
            reply_cursor = comments_col.find({
                "$or": [
                    {"parent_comment_id": comment_id_str},
            {"parent_comment_id": c["_id"]}
        ]
    }).sort("created_at", 1)
            
            replies = []
            async for reply in reply_cursor:
                replies.append(to_out(reply, user_id))
            
            # Set replies to comment
            comment_dict = comment_out.dict()
            comment_dict["replies"] = replies
            comment_out = CommentOut(**comment_dict)
        
        items.append(comment_out)

    total = await comments_col.count_documents(q)
    return {
        "items": items,
        "count": len(items),
        "total": total
    }

@router.get("/check-user-rating/{dish_id}")
async def check_user_rating(dish_id: str, decoded=Depends(current_user_optional)):
    # nếu chưa đăng nhập → coi như chưa đánh giá
    if not decoded:
        return {"has_rated": False}

    user_id = decoded["uid"]
    existing_rating = await comments_col.find_one({
        "dish_id": dish_id,
        "user_id": user_id,
        "$or": [{"parent_comment_id": None}, {"parent_comment_id": ""}],
        "rating": {"$gt": 0}
    }, {"_id": 1, "rating": 1, "content": 1, "created_at": 1})

    if existing_rating:
        return {
            "has_rated": True,
            "comment_id": str(existing_rating["_id"]),
            "rating": existing_rating["rating"],
            "content": existing_rating["content"],
            "created_at": existing_rating["created_at"],
        }
    return {"has_rated": False}

@router.post("/{comment_id}/like")
async def toggle_like_comment(comment_id: str, decoded=Depends(get_current_user)):
    user_id = decoded["uid"]
    try:
        c_oid = ObjectId(comment_id)
    except Exception:
        raise HTTPException(400, "Invalid comment_id")

    c = await comments_col.find_one({"_id": c_oid}, {"_id": 1, "liked_by": 1})
    if not c:
        raise HTTPException(404, "Comment not found")

    liked_by: List[str] = c.get("liked_by", [])
    if user_id in liked_by:
        # Đã like -> un-like
        await comments_col.update_one(
            {"_id": c_oid},
            {
                "$pull": {"liked_by": user_id}, 
                "$inc": {"likes": -1},
                "$set": {"updated_at": datetime.now(timezone.utc)}
            }
        )
        liked = False
    else:
        # Chưa like -> like
        await comments_col.update_one(
            {"_id": c_oid},
            {
                "$addToSet": {"liked_by": user_id}, 
                "$inc": {"likes": 1},
                "$set": {"updated_at": datetime.now(timezone.utc)}
            }
        )
        liked = True

    # Get updated likes count
    c2 = await comments_col.find_one({"_id": c_oid}, {"likes": 1})
    likes_count = c2.get("likes", 0)

    return {"ok": True, "liked": liked, "likes_count": likes_count}

@router.patch("/{comment_id}", response_model=CommentOut)
async def update_comment(comment_id: str, payload: CommentUpdate, decoded=Depends(get_current_user)):
    user_id = decoded["uid"]
    
    # Lấy comment hiện tại để kiểm tra
    current_comment = await comments_col.find_one({"_id": oid(comment_id), "user_id": user_id})
    if not current_comment:
        raise HTTPException(404, "Comment not found or not owned by user")
    
    upd: Dict[str, Any] = {}
    
    # Chỉ cho phép update rating nếu là comment gốc và có rating > 0
    if payload.rating is not None:
        is_main_comment = not current_comment.get("parent_comment_id")
        if not is_main_comment:
            raise HTTPException(400, "Cannot update rating for replies")
        if current_comment.get("rating", 0) <= 0:
            raise HTTPException(400, "Cannot add rating to comment without rating")
        upd["rating"] = int(payload.rating)
    
    if payload.content is not None:
        upd["content"] = payload.content
        
    if not upd:
        raise HTTPException(400, "No fields to update")
    upd["updated_at"] = datetime.now(timezone.utc)

    c = await comments_col.find_one_and_update(
        {"_id": oid(comment_id), "user_id": user_id},
        {"$set": upd},
        return_document=True,
    )

    # Recalc rating nếu có thay đổi rating
    if "rating" in upd:
        await recalc_dish_rating(c["dish_id"])
    
    return to_out(c, user_id)

@router.delete("/{comment_id}")
async def delete_comment(comment_id: str, decoded=Depends(get_current_user)):
    user_id = decoded["uid"]
    c = await comments_col.find_one({"_id": oid(comment_id)})
    if not c:
        raise HTTPException(404, "Comment not found")
    if c["user_id"] != user_id:
        raise HTTPException(403, "You can only delete your own comment")

    # Xóa cả comment và các reply của nó
    await comments_col.delete_many({
        "$or": [
            {"_id": oid(comment_id)},
            {"parent_comment_id": comment_id}
        ]
    })
    
    await recalc_dish_rating(c["dish_id"])
    return {"ok": True}

@router.get("/summary/{dish_id}")
async def get_dish_comment_summary(dish_id: str):
    pipeline = [
        {"$match": {
            "dish_id": dish_id,
            "$or": [{"parent_comment_id": None}, {"parent_comment_id": ""}],
            "rating": {"$gt": 0}
        }},
        {
            "$group": {
                "_id": "$dish_id",
                "count": {"$sum": 1},
                "avg": {"$avg": "$rating"},
                "stars": {"$push": "$rating"},
            }
        },
    ]
    agg = comments_col.aggregate(pipeline)
    stats = await agg.to_list(length=1)
    if not stats:
        return {"dish_id": dish_id, "count": 0, "avg": 0.0}

    s = stats[0]
    return {
        "dish_id": dish_id,
        "count": int(s["count"]),
        "avg": float(s["avg"]),
    }
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone

class CommentPutIn(BaseModel):
    content: Optional[str] = Field(None, max_length=2000)
    rating: Optional[int] = Field(None, ge=1, le=5)

@router.put("/{comment_id}", response_model=CommentOut)
async def put_update_comment(comment_id: str, payload: CommentPutIn, decoded=Depends(get_current_user)):
    """
    Cập nhật comment theo phương thức PUT để khớp với FE.
    - Cho phép sửa content ở cả comment gốc và reply.
    - Chỉ cho phép sửa rating nếu là comment gốc (parent_comment_id None/"") và rating hiện tại > 0.
    """
    user_id = decoded["uid"]

    # Lấy comment hiện tại và kiểm tra quyền sở hữu
    current_comment = await comments_col.find_one({"_id": oid(comment_id), "user_id": user_id})
    if not current_comment:
        raise HTTPException(404, "Comment not found or not owned by user")

    upd = {}

    # Cập nhật nội dung nếu có
    if payload.content is not None:
        upd["content"] = payload.content

    # Xử lý rating nếu có
    if payload.rating is not None:
        is_main_comment = not current_comment.get("parent_comment_id")
        if not is_main_comment:
            raise HTTPException(400, "Cannot update rating for replies")
        if current_comment.get("rating", 0) <= 0:
            # Không cho thêm rating mới cho comment vốn không có rating
            raise HTTPException(400, "Cannot add rating to comment without rating")
        upd["rating"] = int(payload.rating)

    if not upd:
        raise HTTPException(400, "No fields to update")

    upd["updated_at"] = datetime.now(timezone.utc)

    # Cập nhật và trả về
    c = await comments_col.find_one_and_update(
        {"_id": oid(comment_id), "user_id": user_id},
        {"$set": upd},
        return_document=True,
    )

    # Nếu có chỉnh rating -> tính lại điểm trung bình món ăn
    if "rating" in upd:
        await recalc_dish_rating(c["dish_id"])

    return to_out(c, user_id)
@router.get("/{comment_id}/permissions", response_model=CommentPermissionOut)
async def get_comment_permissions(comment_id: str, decoded=Depends(get_current_user)):
    """
    Trả JSON để FE dùng:
    {
      "owned": bool,
      "can_edit": bool,
      "can_delete": bool
    }
    - 401 nếu chưa đăng nhập
    - 404 nếu comment không tồn tại
    """
    user_id = decoded["uid"]
    # validate ObjectId & tìm comment
    c = await comments_col.find_one({"_id": oid(comment_id)}, {"_id": 1, "user_id": 1})
    if not c:
        raise HTTPException(status_code=404, detail="Comment not found")

    owned = (c.get("user_id") == user_id)
    return CommentPermissionOut(owned=owned, can_edit=owned, can_delete=owned)
