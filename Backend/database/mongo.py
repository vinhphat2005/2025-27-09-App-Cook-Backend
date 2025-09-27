import motor.motor_asyncio
import os
from dotenv import load_dotenv

load_dotenv()

# Use same MongoDB config as main_async.py
MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DATABASE_NAME", "cook_app")

# ASYNC MongoDB client (Motor) - consistent with main_async.py
client = motor.motor_asyncio.AsyncIOMotorClient(
    MONGODB_URI,
    tls=True,
    serverSelectionTimeoutMS=30000,
)
db = client[DB_NAME]

# Core collections (ALL ASYNC)
ingredients_collection = db["ingredients"]
recipe_collection = db["recipes"]
users_collection = db["users"]
dishes_collection = db["dishes"]

# User-related collections (ALL ASYNC)
user_social_collection = db["user_social"]  # followers, following
user_activity_collection = db["user_activity"]  # favorites, cooked, viewed
user_notifications_collection = db["user_notifications"]  # notifications
user_preferences_collection = db["user_preferences"]  # reminders, preferences