# test.py
import os
import motor.motor_asyncio
import asyncio
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DATABASE_NAME", "cook_app")

async def test_mongo():
    try:
        print(f"🔍 Connecting to MongoDB: {MONGODB_URI}")
        client = motor.motor_asyncio.AsyncIOMotorClient(
            MONGODB_URI,
            tls=True,
            serverSelectionTimeoutMS=5000  # 5 giây để test
        )
        db = client[DB_NAME]
        # Test lệnh server_info
        info = await db.command("ping")
        print("✅ MongoDB connected:", info)
    except Exception as e:
        print("❌ MongoDB connection failed:", e)

if __name__ == "__main__":
    asyncio.run(test_mongo())
