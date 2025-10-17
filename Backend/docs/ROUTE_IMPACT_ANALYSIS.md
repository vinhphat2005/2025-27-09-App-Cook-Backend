# 🔍 Route Impact Analysis - ObjectId Refactoring

## 📋 Tóm tắt

Sau khi refactor `main_async.py` để dùng **ObjectId everywhere**, cần kiểm tra và fix các route files để đảm bảo consistency.

---

## 🚨 CRITICAL ISSUES FOUND

### ❌ Issue 1: `user_route.py` - Dùng Firebase UID thay vì ObjectId

**Location:** `routes/user_route.py` lines 166-241

**Problem:**
```python
@router.post("/activity/view")
async def add_view_history(payload: ViewEventIn, decoded=Depends(get_current_user)):
    uid = decoded["uid"]  # ❌ Firebase UID (string)
    now = datetime.now(timezone.utc)

    # ❌ Query với Firebase UID thay vì MongoDB ObjectId
    await user_activity_col.update_one(
        {"user_id": uid},  # ❌ WRONG: uid là Firebase UID (string)
        {"$pull": {"viewed_dishes_and_users": {"type": doc["type"], "id": doc["id"]}}},
        upsert=True
    )
    
@router.get("/activity/view")
async def get_view_history(limit: int = 50, decoded=Depends(get_current_user)):
    uid = decoded["uid"]  # ❌ Firebase UID (string)
    
    doc = await user_activity_col.find_one(
        {"user_id": uid},  # ❌ WRONG: uid là Firebase UID (string)
        {"_id": 0, "viewed_dishes_and_users": 1}
    )
```

**Why this is wrong:**
- `decoded["uid"]` = Firebase UID (e.g., `"abc123xyz456"`) - là **string**
- `user_activity_col.user_id` = MongoDB `_id` của user - giờ là **ObjectId**
- Type mismatch → query sẽ **KHÔNG tìm thấy gì**!

**Impact:**
- ❌ `/activity/view` POST - Không lưu được history
- ❌ `/activity/view` GET - Trả về empty array
- ❌ Tất cả user đều không có view history

---

### ❌ Issue 2: `utils/user_handlers.py` - Convert ObjectId → string

**Location:** `utils/user_handlers.py`

**Problems found:**

#### 2.1 - `init_user_data` trong handlers
```python
# Line 72
await UserDataService.init_user_data(str(new_user["_id"]))  # ❌ Convert to string

# Line 135
await UserDataService.init_user_data(str(user["_id"]))  # ❌ Convert to string
```

**Why this is wrong:**
- `UserDataService.init_user_data()` nhận `user_id: str` parameter
- Nó sẽ lưu **string** vào `user_social.user_id`, `user_activity.user_id`, etc.
- Nhưng `main_async.py` giờ dùng **ObjectId**!

#### 2.2 - Queries với string user_id
```python
# Line 198
social_data = await UserDataService.get_user_social(str(user["_id"]))  # ❌

# Line 221
result = await UserDataService.follow_user(str(current_user["_id"]), user_id)  # ❌

# Line 253
activity_data = await UserDataService.get_user_activity(str(user["_id"]))  # ❌

# Line 269
result = await UserDataService.add_to_cooked(str(user["_id"]), dish_id, MAX_HISTORY)  # ❌

# Line 402
notif_data = await UserDataService.get_user_notifications(str(user["_id"]))  # ❌

# Line 416, 432
await user_preferences_collection.find_one({"user_id": str(user["_id"])})  # ❌
```

**Impact:**
- Nếu `UserDataService` methods query với string → **KHÔNG tìm thấy data**
- Tất cả social/activity/notifications queries sẽ **FAIL**

---

### ❌ Issue 3: `core/user_management/service.py` - Type mismatch

**Location:** `core/user_management/service.py`

**Problems:**

#### 3.1 - Service methods nhận `user_id: str`
```python
# Lines 100, 108, 116, 124, 132, 170, 196, 222, 252
@staticmethod
async def get_user_social(user_id: str) -> Optional[UserSocial]:  # ❌ str parameter
    social_data = await user_social_collection.find_one({"user_id": user_id})
    # If user_id is string but DB has ObjectId → NOT FOUND!
```

**All affected methods:**
- `get_user_social(user_id: str)` ❌
- `get_user_activity(user_id: str)` ❌
- `get_user_notifications(user_id: str)` ❌
- `get_user_preferences(user_id: str)` ❌
- `init_user_data(user_id: str)` ❌
- `add_to_cooked(user_id: str, ...)` ❌
- `add_to_viewed(user_id: str, ...)` ❌
- `add_to_favorites(user_id: str, ...)` ❌
- `_update_social_counters(user_id: str)` ❌

#### 3.2 - `init_user_data` tạo documents với string
```python
@staticmethod
async def init_user_data(user_id: str):  # ❌ Receives string
    # Tạo social data
    await user_social_collection.insert_one({
        "user_id": user_id,  # ❌ Lưu string
        "followers": [],
        ...
    })
    
    # Tạo activity data
    await user_activity_collection.insert_one({
        "user_id": user_id,  # ❌ Lưu string
        ...
    })
```

**Impact:**
- Users mới được tạo sẽ có **string user_id** trong collections phụ
- Không consistent với users được tạo từ `main_async.py` (ObjectId)
- Database sẽ có **MIX of string and ObjectId** → CHAOS!

---

## 📊 Impact Summary

| File | Affected Functions | Severity | Impact |
|------|-------------------|----------|--------|
| `routes/user_route.py` | `add_view_history()`, `get_view_history()` | 🔴 HIGH | View history không hoạt động |
| `utils/user_handlers.py` | 10+ functions | 🔴 HIGH | Social/Activity queries fail |
| `core/user_management/service.py` | All `UserDataService` methods | 🔴 CRITICAL | Toàn bộ user data system broken |

---

## 🔧 Required Fixes

### Fix 1: Update `user_route.py` to use MongoDB _id

**File:** `routes/user_route.py`

**Change:**
```python
# ❌ BEFORE
@router.post("/activity/view")
async def add_view_history(payload: ViewEventIn, decoded=Depends(get_current_user)):
    uid = decoded["uid"]  # ❌ Firebase UID
    
    await user_activity_col.update_one(
        {"user_id": uid},  # ❌ String
        ...
    )

# ✅ AFTER
@router.post("/activity/view")
async def add_view_history(payload: ViewEventIn, decoded=Depends(get_current_user)):
    # ✅ Get MongoDB user document to get ObjectId
    from database.mongo import users_collection
    from bson import ObjectId
    
    email = decoded.get("email")
    user = await users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(404, "User not found")
    
    user_oid = user["_id"]  # ✅ ObjectId
    
    await user_activity_col.update_one(
        {"user_id": user_oid},  # ✅ ObjectId
        ...
    )
```

---

### Fix 2: Update `utils/user_handlers.py` to pass ObjectId

**File:** `utils/user_handlers.py`

**Change all instances:**
```python
# ❌ BEFORE
await UserDataService.init_user_data(str(new_user["_id"]))
social_data = await UserDataService.get_user_social(str(user["_id"]))

# ✅ AFTER
await UserDataService.init_user_data(new_user["_id"])  # Pass ObjectId
social_data = await UserDataService.get_user_social(user["_id"])  # Pass ObjectId
```

**Lines to fix:** 72, 135, 198, 221, 253, 269, 402, 416, 432

---

### Fix 3: Update `core/user_management/service.py` type signatures

**File:** `core/user_management/service.py`

**Change:**
```python
# ❌ BEFORE
@staticmethod
async def get_user_social(user_id: str) -> Optional[UserSocial]:
    social_data = await user_social_collection.find_one({"user_id": user_id})
    
@staticmethod
async def init_user_data(user_id: str):
    await user_social_collection.insert_one({
        "user_id": user_id,
        ...
    })

# ✅ AFTER
from bson import ObjectId

@staticmethod
async def get_user_social(user_id: ObjectId) -> Optional[UserSocial]:
    social_data = await user_social_collection.find_one({"user_id": user_id})
    
@staticmethod
async def init_user_data(user_id: ObjectId):
    await user_social_collection.insert_one({
        "user_id": user_id,  # ✅ ObjectId
        ...
    })
```

**All methods to update:**
- `get_user_social(user_id: ObjectId)` 
- `get_user_activity(user_id: ObjectId)`
- `get_user_notifications(user_id: ObjectId)`
- `get_user_preferences(user_id: ObjectId)`
- `init_user_data(user_id: ObjectId)`
- `add_to_cooked(user_id: ObjectId, ...)`
- `add_to_viewed(user_id: ObjectId, ...)`
- `add_to_favorites(user_id: ObjectId, ...)`
- `_update_social_counters(user_id: ObjectId)`

---

## 🧪 Testing After Fixes

### Test 1: View History
```bash
# Login
TOKEN=$(python scripts/get_test_token.py)

# Add view history
curl -X POST http://localhost:8000/users/activity/view \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "dish",
    "target_id": "507f1f77bcf86cd799439011",
    "name": "Test Dish",
    "image": "http://example.com/image.jpg"
  }'

# Expected: {"ok": true, "added": {...}}

# Get view history
curl -X GET http://localhost:8000/users/activity/view \
  -H "Authorization: Bearer $TOKEN"

# Expected: {"items": [...], "count": 1}
```

### Test 2: User Social Data
```bash
# Get my social
curl -X GET http://localhost:8000/users/me/social \
  -H "Authorization: Bearer $TOKEN"

# Expected: {"followers": [], "following": [], ...}
```

### Test 3: MongoDB Verification
```bash
mongosh "$MONGODB_URI"
use cook_app

# Check user_activity collection
var user = db.users.findOne({"email": "test@example.com"})
print("User _id:", user._id)
print("User _id type:", typeof user._id)  // Should be "object"

var activity = db.user_activity.findOne({"user_id": user._id})
print("Activity found:", activity != null)
print("Activity user_id type:", typeof activity.user_id)  // Should be "object"

# ✅ Both should be "object" (ObjectId)
# ❌ If one is "object" and one is "string" → BROKEN
```

---

## 📝 Fix Priority

### 🔴 CRITICAL (Fix NOW):
1. ✅ `core/user_management/service.py` - Change all `user_id: str` → `user_id: ObjectId`
2. ✅ `utils/user_handlers.py` - Remove all `str(user["_id"])` conversions
3. ✅ `routes/user_route.py` - Fix view history routes

### 🟡 MEDIUM (Fix Soon):
4. ⏳ Review other route files for similar issues
5. ⏳ Add type hints everywhere
6. ⏳ Add integration tests

### 🟢 LOW (Cleanup):
7. ⏳ Update documentation
8. ⏳ Add migration script for existing data

---

## 🎯 Consistency Rules

Going forward, enforce these rules:

### Rule 1: Always use ObjectId for user_id
```python
# ✅ CORRECT
user_oid = user["_id"]  # Keep as ObjectId
await collection.find_one({"user_id": user_oid})

# ❌ WRONG
user_id = str(user["_id"])  # Don't convert
await collection.find_one({"user_id": user_id})
```

### Rule 2: Type hints are mandatory
```python
# ✅ CORRECT
async def get_user_data(user_id: ObjectId) -> dict:
    return await collection.find_one({"user_id": user_id})

# ❌ WRONG
async def get_user_data(user_id):  # No type hint
    return await collection.find_one({"user_id": user_id})
```

### Rule 3: Never mix Firebase UID with MongoDB _id
```python
# ✅ CORRECT
# Firebase UID: Only for Firebase operations
firebase_uid = decoded["uid"]  
firebase_user = fb_auth.get_user(firebase_uid)

# MongoDB _id: For all database operations
email = decoded["email"]
user = await users_collection.find_one({"email": email})
user_oid = user["_id"]  # Use this for queries

# ❌ WRONG
uid = decoded["uid"]
await user_activity_col.find_one({"user_id": uid})  # Mixing Firebase UID with MongoDB!
```

---

## 📊 Verification Checklist

After fixes:

- [ ] All `UserDataService` methods use `ObjectId` type hints
- [ ] All handlers in `user_handlers.py` pass ObjectId (not string)
- [ ] `user_route.py` view history routes use MongoDB _id (not Firebase UID)
- [ ] No `str(user["_id"])` conversions before database queries
- [ ] All tests pass
- [ ] MongoDB documents show consistent ObjectId types

---

## 🚨 Breaking Changes Summary

| What Changed | Before | After |
|--------------|--------|-------|
| `UserDataService` params | `user_id: str` | `user_id: ObjectId` |
| Handler calls | `str(user["_id"])` | `user["_id"]` |
| View history queries | Firebase UID | MongoDB ObjectId |
| Collection documents | Mixed str/ObjectId | All ObjectId |

---

*Analysis completed: 2025-10-15*  
*Critical issues found: 3*  
*Files affected: 3*  
*Priority: 🔴 URGENT - Fix before production*
