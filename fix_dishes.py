import asyncio
from database.mongo import db
from datetime import datetime, timedelta

async def fix_dishes():
    """Add ratings array to dishes"""
    
    # Create sample ratings
    sample_ratings = [
        {"user_id": "user1", "rating": 5, "timestamp": datetime.utcnow() - timedelta(days=1)},
        {"user_id": "user2", "rating": 4, "timestamp": datetime.utcnow() - timedelta(days=2)},
        {"user_id": "user3", "rating": 5, "timestamp": datetime.utcnow() - timedelta(days=3)},
        {"user_id": "user4", "rating": 4, "timestamp": datetime.utcnow() - timedelta(days=4)},
        {"user_id": "user5", "rating": 5, "timestamp": datetime.utcnow() - timedelta(days=5)},
        {"user_id": "user6", "rating": 4, "timestamp": datetime.utcnow() - timedelta(days=6)},
    ]
    
    # Update all dishes
    result = await db.dishes.update_many(
        {},
        {
            "$set": {
                "ratings": sample_ratings,
                "is_active": True,
            }
        }
    )
    
    print(f"✅ Updated {result.modified_count} dishes with ratings")
    
    # Verify
    dishes = await db.dishes.find().to_list(None)
    print(f"\n📋 Dishes after fix:")
    for d in dishes:
        ratings = d.get("ratings", [])
        print(f"  - {d['name']}: rating={d.get('average_rating', 0)}, ratings_count={len(ratings)}, is_active={d.get('is_active', False)}")

asyncio.run(fix_dishes())
