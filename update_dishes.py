import asyncio
from database.mongo import db
from datetime import datetime, timedelta

async def update_dishes():
    """Update existing dishes with better ratings"""
    
    update_data = [
        {
            "name": "Phở bò",
            "average_rating": 4.5,
            "rating_count": 120,
            "like_count": 250,
            "cook_count": 180,
            "view_count": 1000,
        },
        {
            "name": "Cơm gà Hội An",
            "average_rating": 4.7,
            "rating_count": 200,
            "like_count": 350,
            "cook_count": 250,
            "view_count": 1500,
        },
        {
            "name": "Ramen",
            "average_rating": 4.6,
            "rating_count": 150,
            "like_count": 280,
            "cook_count": 200,
            "view_count": 1200,
        }
    ]
    
    for data in update_data:
        result = await db.dishes.update_one(
            {"name": data["name"]},
            {"$set": {
                **data,
                "updated_at": datetime.utcnow()
            }}
        )
        print(f"✅ Updated {data['name']}: {result.modified_count} modified")
    
    # Verify
    dishes = await db.dishes.find().to_list(None)
    print(f"\n📋 Updated dishes:")
    for d in dishes:
        print(f"  - {d['name']}: rating={d.get('average_rating', 0)}, count={d.get('rating_count', 0)}")

asyncio.run(update_dishes())
