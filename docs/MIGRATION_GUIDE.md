# 🚀 Migration Guide: ObjectId Refactoring

## 📋 Overview

This guide walks you through migrating your existing database from **string-based user_id** to **ObjectId-based user_id** in all user-related collections.

**Estimated time:** 5-10 minutes (depending on user count)

---

## ⚠️ Pre-requisites

- [ ] Access to production database
- [ ] `DEBUG=True` in `.env` (required for migration endpoints)
- [ ] Backup of current database
- [ ] MongoDB shell access (for verification)

---

## 🔄 Migration Steps

### Step 1: Backup Database

```bash
# Set your MongoDB URI
export MONGODB_URI="your_mongodb_connection_string"

# Create backup folder with timestamp
BACKUP_DIR="backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p $BACKUP_DIR

# Backup entire database
mongodump --uri="$MONGODB_URI" --out=$BACKUP_DIR

# Verify backup
ls -lh $BACKUP_DIR/
```

**✅ Checkpoint:** Backup file should exist and have reasonable size (>1MB if you have data)

---

### Step 2: Enable Debug Mode

```bash
# In your .env file
DEBUG=True
```

**⚠️ Important:** Migration endpoints only work when `DEBUG=True`

---

### Step 3: Start Application

```bash
# Make sure app is running
uvicorn main_async:app --reload --host 0.0.0.0 --port 8000
```

**✅ Checkpoint:** You should see:
```
✅ MongoDB indexes created successfully
```

---

### Step 4: Check Current State (Optional)

```bash
# Connect to MongoDB shell
mongosh "$MONGODB_URI"

# Switch to your database
use cook_app

# Count users with OLD structure (has followers/following fields)
db.users.find({
  $or: [
    {"followers": {$exists: true}},
    {"following": {$exists: true}},
    {"recipes": {$exists: true}}
  ]
}).count()

# Count user_social documents with STRING user_id
db.user_social.find({"user_id": {$type: "string"}}).count()
```

---

### Step 5: Run Migration

#### Option A: Migrate Single User (Test First)

```bash
# Get a user_id from your database
USER_ID="507f1f77bcf86cd799439011"  # Replace with actual ID

# Migrate single user
curl -X POST "http://localhost:8000/admin/reorganize-user/$USER_ID" \
  -H "Content-Type: application/json" | jq
```

**Expected Response:**
```json
{
  "message": "Successfully migrated user 507f1f77bcf86cd799439011 to new structure",
  "migrated_collections": [
    "user_social",
    "user_activity", 
    "user_notifications",
    "user_preferences"
  ],
  "cleaned_fields": [
    "followers",
    "following",
    "recipes",
    "liked_dishes",
    "favorite_dishes",
    "cooked_dishes",
    "viewed_dishes",
    "notifications"
  ]
}
```

#### Option B: Migrate All Users

```bash
# Migrate ALL users at once
curl -X POST "http://localhost:8000/admin/migrate-all-users" \
  -H "Content-Type: application/json" | jq
```

**Expected Response:**
```json
{
  "message": "Migration completed",
  "migrated_users": 150,
  "total_users": 200,
  "skipped": 50,
  "errors": []
}
```

**Explanation:**
- `migrated_users`: Users that had old structure and were migrated
- `total_users`: Total users in database
- `skipped`: Users already in new structure (already migrated or new users)
- `errors`: Array of error messages if any migration failed

---

### Step 6: Verify Migration

#### 6.1 Check MongoDB

```bash
mongosh "$MONGODB_URI"
use cook_app

# ✅ Should return 0 (no more string user_ids)
db.user_social.find({"user_id": {$type: "string"}}).count()
db.user_activity.find({"user_id": {$type: "string"}}).count()
db.user_notifications.find({"user_id": {$type: "string"}}).count()
db.user_preferences.find({"user_id": {$type: "string"}}).count()

# ✅ Should return 0 (no more old fields in users collection)
db.users.find({
  $or: [
    {"followers": {$exists: true}},
    {"following": {$exists: true}},
    {"recipes": {$exists: true}}
  ]
}).count()

# ✅ Check indexes were created
db.users.getIndexes()
db.user_social.getIndexes()
```

#### 6.2 Check Sample User

```bash
mongosh "$MONGODB_URI"
use cook_app

# Find a user
var user = db.users.findOne()
print("User ID:", user._id)

# Check their collections use ObjectId
var social = db.user_social.findOne({"user_id": user._id})
print("Social found:", social != null)
print("Social user_id type:", typeof social.user_id)  // Should be "object"

var activity = db.user_activity.findOne({"user_id": user._id})
print("Activity found:", activity != null)
```

---

### Step 7: Test Endpoints

```bash
# Get Firebase token (use your test script)
TOKEN=$(python scripts/get_test_token.py --email test@example.com --password testpass)

# Test login (should create/update user correctly)
curl -X POST "http://localhost:8000/users/auth/google-login" \
  -H "Authorization: Bearer $TOKEN" | jq

# Test /me endpoint (should load all collections)
curl -X GET "http://localhost:8000/me" \
  -H "Authorization: Bearer $TOKEN" | jq

# Verify response includes all sections
# Should have: user, social, activity, notifications, preferences, firebase
```

**✅ Expected Response Structure:**
```json
{
  "user": {
    "id": "507f1f77bcf86cd799439011",
    "email": "test@example.com",
    "name": "Test User"
  },
  "social": {
    "user_id": "...",
    "followers": [],
    "following": [],
    "follower_count": 0,
    "following_count": 0
  },
  "activity": {
    "user_id": "...",
    "favorite_dishes": [],
    "cooked_dishes": []
  },
  "notifications": {
    "user_id": "...",
    "notifications": [],
    "unread_count": 0
  },
  "preferences": {
    "user_id": "...",
    "reminders": [],
    "dietary_restrictions": []
  },
  "firebase": {
    "uid": "...",
    "email": "test@example.com"
  }
}
```

---

### Step 8: Performance Test

```bash
# Test query performance with indexes
time curl -X GET "http://localhost:8000/me" \
  -H "Authorization: Bearer $TOKEN"

# Should complete in <50ms (with indexes)
```

---

### Step 9: Disable Debug Mode (Production)

```bash
# In your .env file
DEBUG=False
```

**⚠️ After this, migration endpoints will return 403 Forbidden**

---

## 🔍 Troubleshooting

### Issue: Migration endpoint returns 403

**Cause:** `DEBUG=False` in environment

**Fix:**
```bash
# Set DEBUG=True in .env
DEBUG=True

# Restart app
```

---

### Issue: "User not found" error

**Cause:** Invalid ObjectId format

**Fix:**
```bash
# Make sure user_id is valid 24-character hex string
# Get valid user_id from database:
mongosh "$MONGODB_URI" --eval "db.users.findOne()._id"
```

---

### Issue: "Migration failed: duplicate key error"

**Cause:** User already has documents in new collections

**Fix:**
```bash
# This is safe to ignore - user was already migrated
# The migration will skip already-migrated users
```

---

### Issue: Slow queries after migration

**Cause:** Indexes not created

**Fix:**
```bash
# Restart app to trigger index creation
# Or manually create indexes:
mongosh "$MONGODB_URI"
use cook_app

db.users.createIndex({"email": 1}, {unique: true})
db.users.createIndex({"display_id": 1}, {unique: true, sparse: true})
db.user_social.createIndex({"user_id": 1}, {unique: true})
db.user_activity.createIndex({"user_id": 1}, {unique: true})
db.user_notifications.createIndex({"user_id": 1}, {unique: true})
db.user_preferences.createIndex({"user_id": 1}, {unique: true})
```

---

### Issue: Type mismatch errors in logs

**Cause:** Some code still using string user_id

**Fix:**
```python
# ❌ OLD CODE
user_id = str(user_doc["_id"])
social = await user_social_col.find_one({"user_id": user_id})

# ✅ NEW CODE
user_id = user_doc["_id"]  # Keep as ObjectId
social = await user_social_col.find_one({"user_id": user_id})
```

---

## 📊 Verification Checklist

After migration, verify these points:

- [ ] **Zero string user_ids:** `db.user_social.find({"user_id": {$type: "string"}}).count() == 0`
- [ ] **All users migrated:** `db.users.find({"followers": {$exists: true}}).count() == 0`
- [ ] **Indexes created:** `db.users.getIndexes().length >= 3`
- [ ] **Login works:** Can authenticate with Firebase token
- [ ] **/me endpoint works:** Returns user + social + activity + notifications + preferences
- [ ] **Performance good:** Queries complete in <50ms
- [ ] **No errors in logs:** Check application logs for errors

---

## 🎯 Rollback Plan (Emergency)

If something goes wrong:

### Option 1: Restore from Backup

```bash
# Stop application
pkill -f uvicorn

# Restore from backup
mongorestore --uri="$MONGODB_URI" --drop $BACKUP_DIR

# Verify restoration
mongosh "$MONGODB_URI" --eval "db.users.countDocuments()"

# Start application with OLD code
git checkout <previous_commit>
uvicorn main_async:app --reload
```

### Option 2: Revert Code Only

```bash
# Keep database as-is (new structure)
# Revert code to handle both string and ObjectId

# This is NOT RECOMMENDED - fix forward instead
```

---

## 📈 Expected Performance Improvements

| Metric | Before Migration | After Migration | Improvement |
|--------|-----------------|-----------------|-------------|
| `/me` endpoint | 300-500ms | 10-50ms | **10-50x faster** |
| User lookup by email | 200-400ms | 2-5ms | **100x faster** |
| Social data query | 100-300ms | 1-3ms | **100-300x faster** |
| Database size | Same | -10-20% (removed duplicate data) | Smaller |

---

## ✅ Success Criteria

Migration is successful when:

1. ✅ All user_ids in secondary collections are ObjectId type
2. ✅ No old fields (followers, following, recipes) in users collection
3. ✅ All indexes created successfully
4. ✅ All API endpoints respond correctly
5. ✅ No errors in application logs
6. ✅ Query performance improved (check with `time curl`)

---

## 📞 Support

If you encounter issues:

1. Check logs: `tail -f logs/app.log`
2. Check MongoDB logs: `mongosh --eval "db.adminCommand({getLog: 'global'})"`
3. Review this guide's troubleshooting section
4. Contact backend team with:
   - Error messages
   - Migration response JSON
   - User count from database
   - Sample user document

---

*Migration Guide Version: 1.0*  
*Created: 2025-10-15*  
*Last Updated: 2025-10-15*
