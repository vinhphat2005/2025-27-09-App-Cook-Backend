"""
Script to seed sample dishes into MongoDB
Run: python scripts/seed_dishes.py
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
import random

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.mongo import db

async def seed_dishes():
    """Seed sample dishes into MongoDB"""
    
    # Sample dishes data
    sample_dishes = [
        {
            "name": "Phở Gà",
            "description": "Món phở gà truyền thống với nước dùi vàng đậm đà",
            "category": "Vietnamese",
            "cuisine_type": "Vietnamese",
            "difficulty": "medium",
            "cooking_time": 45,
            "ingredients": ["gà", "nước dùi", "bánh phở", "hành", "gừng"],
            "steps": [
                "Chuẩn bị nước dùi gà",
                "Nấu bánh phở",
                "Thêm gia vị",
                "Dùng nóng"
            ],
            "average_rating": 4.5,
            "rating_count": 120,
            "like_count": 250,
            "cook_count": 180,
            "view_count": 1000,
            "image_url": "https://via.placeholder.com/300?text=Pho+Ga",
            "created_at": datetime.utcnow() - timedelta(days=10),
            "updated_at": datetime.utcnow(),
        },
        {
            "name": "Cơm Tấm Sài Gòn",
            "description": "Cơm tấm nướng sườn với tương ớt",
            "category": "Vietnamese",
            "cuisine_type": "Vietnamese",
            "difficulty": "easy",
            "cooking_time": 30,
            "ingredients": ["cơm tấm", "sườn", "tương ớt", "rau sống"],
            "steps": [
                "Nướng sườn",
                "Chuẩn bị cơm",
                "Dọn trang trí",
                "Ăn nóng"
            ],
            "average_rating": 4.7,
            "rating_count": 200,
            "like_count": 350,
            "cook_count": 250,
            "view_count": 1500,
            "image_url": "https://via.placeholder.com/300?text=Com+Tam",
            "created_at": datetime.utcnow() - timedelta(days=5),
            "updated_at": datetime.utcnow(),
        },
        {
            "name": "Bánh Mì Thịt Nướng",
            "description": "Bánh mì giòn với thịt nướng và rau sống",
            "category": "Vietnamese",
            "cuisine_type": "Vietnamese",
            "difficulty": "easy",
            "cooking_time": 25,
            "ingredients": ["bánh mì", "thịt", "cà chua", "dưa chuột", "hành"],
            "steps": [
                "Nướng thịt",
                "Chuẩn bị bánh",
                "Xếp các lớp",
                "Ăn ngay"
            ],
            "average_rating": 4.6,
            "rating_count": 150,
            "like_count": 280,
            "cook_count": 200,
            "view_count": 1200,
            "image_url": "https://via.placeholder.com/300?text=Banh+Mi",
            "created_at": datetime.utcnow() - timedelta(days=3),
            "updated_at": datetime.utcnow(),
        },
        {
            "name": "Gỏi Cuốn Tôm",
            "description": "Gỏi cuốn tôm tươi với nước chấm ngon",
            "category": "Vietnamese",
            "cuisine_type": "Vietnamese",
            "difficulty": "easy",
            "cooking_time": 20,
            "ingredients": ["tôm", "bánh tráng", "rau sống", "nước chấm"],
            "steps": [
                "Luộc tôm",
                "Chuẩn bị bánh tráng",
                "Cuốn gỏi",
                "Ăn ngay"
            ],
            "average_rating": 4.8,
            "rating_count": 180,
            "like_count": 400,
            "cook_count": 220,
            "view_count": 1600,
            "image_url": "https://via.placeholder.com/300?text=Goi+Cuon",
            "created_at": datetime.utcnow() - timedelta(days=1),
            "updated_at": datetime.utcnow(),
        },
        {
            "name": "Mỳ Ý Spaghetti",
            "description": "Spaghetti carbonara với xà phòng cà chua",
            "category": "Italian",
            "cuisine_type": "Italian",
            "difficulty": "medium",
            "cooking_time": 35,
            "ingredients": ["mỳ ý", "trứng", "xà phòng", "hạt tiêu", "bơ"],
            "steps": [
                "Nấu mỳ",
                "Chuẩn bị nước sốt",
                "Trộn đều",
                "Ăn nóng"
            ],
            "average_rating": 4.4,
            "rating_count": 100,
            "like_count": 200,
            "cook_count": 150,
            "view_count": 800,
            "image_url": "https://via.placeholder.com/300?text=Spaghetti",
            "created_at": datetime.utcnow() - timedelta(days=7),
            "updated_at": datetime.utcnow(),
        },
        {
            "name": "Bún Chả Hà Nội",
            "description": "Bún chả với thịt nướng và nước chấm",
            "category": "Vietnamese",
            "cuisine_type": "Vietnamese",
            "difficulty": "medium",
            "cooking_time": 40,
            "ingredients": ["bún", "thịt", "nước chấm", "rau sống"],
            "steps": [
                "Nấu bún",
                "Nướng thịt",
                "Chuẩn bị nước chấm",
                "Ăn nóng"
            ],
            "average_rating": 4.5,
            "rating_count": 110,
            "like_count": 260,
            "cook_count": 190,
            "view_count": 1100,
            "image_url": "https://via.placeholder.com/300?text=Bun+Cha",
            "created_at": datetime.utcnow() - timedelta(days=8),
            "updated_at": datetime.utcnow(),
        },
        {
            "name": "Cà Chua Trứng",
            "description": "Một món ăn đơn giản nhưng rất ngon",
            "category": "Vietnamese",
            "cuisine_type": "Vietnamese",
            "difficulty": "easy",
            "cooking_time": 15,
            "ingredients": ["cà chua", "trứng", "dầu ăn", "muối"],
            "steps": [
                "Cắt cà chua",
                "Đánh trứng",
                "Xào nhanh",
                "Ăn ngay"
            ],
            "average_rating": 4.3,
            "rating_count": 80,
            "like_count": 150,
            "cook_count": 120,
            "view_count": 600,
            "image_url": "https://via.placeholder.com/300?text=Ca+Chua+Trung",
            "created_at": datetime.utcnow() - timedelta(days=12),
            "updated_at": datetime.utcnow(),
        },
        {
            "name": "Canh Chua Cá",
            "description": "Canh chua với cá tươi và gia vị",
            "category": "Vietnamese",
            "cuisine_type": "Vietnamese",
            "difficulty": "medium",
            "cooking_time": 35,
            "ingredients": ["cá", "chua", "cà chua", "hành", "gia vị"],
            "steps": [
                "Nấu nước dùi",
                "Thêm cá",
                "Nêm gia vị",
                "Ăn nóng"
            ],
            "average_rating": 4.6,
            "rating_count": 140,
            "like_count": 300,
            "cook_count": 210,
            "view_count": 1300,
            "image_url": "https://via.placeholder.com/300?text=Canh+Chua+Ca",
            "created_at": datetime.utcnow() - timedelta(days=6),
            "updated_at": datetime.utcnow(),
        },
        {
            "name": "Thịt Nướng Nước Mắm",
            "description": "Thịt nướng ướp nước mắm ngon lành",
            "category": "Vietnamese",
            "cuisine_type": "Vietnamese",
            "difficulty": "easy",
            "cooking_time": 30,
            "ingredients": ["thịt", "nước mắm", "hành", "tỏi"],
            "steps": [
                "Ướp thịt",
                "Nướng",
                "Dọn trang trí",
                "Ăn nóng"
            ],
            "average_rating": 4.7,
            "rating_count": 160,
            "like_count": 330,
            "cook_count": 240,
            "view_count": 1400,
            "image_url": "https://via.placeholder.com/300?text=Thit+Nuong",
            "created_at": datetime.utcnow() - timedelta(days=4),
            "updated_at": datetime.utcnow(),
        },
        {
            "name": "Cơm Chiên Dương Châu",
            "description": "Cơm chiên với tôm, thịt và trứng",
            "category": "Chinese",
            "cuisine_type": "Chinese",
            "difficulty": "medium",
            "cooking_time": 25,
            "ingredients": ["cơm", "tôm", "thịt", "trứng", "rau"],
            "steps": [
                "Chuẩn bị nguyên liệu",
                "Chiên cơm",
                "Thêm các loại",
                "Ăn ngay"
            ],
            "average_rating": 4.5,
            "rating_count": 130,
            "like_count": 270,
            "cook_count": 200,
            "view_count": 1150,
            "image_url": "https://via.placeholder.com/300?text=Com+Chien",
            "created_at": datetime.utcnow() - timedelta(days=9),
            "updated_at": datetime.utcnow(),
        },
    ]
    
    try:
        print(f"🔄 Connecting to MongoDB: {os.getenv('DATABASE_NAME', 'cook_app')}")
        
        # Check if dishes already exist
        existing_count = await db.dishes.count_documents({})
        print(f"📊 Existing dishes: {existing_count}")
        
        if existing_count > 0:
            print("ℹ️  Database already has dishes. Skipping seed.")
            return
        
        # Insert sample dishes
        print(f"\n📝 Inserting {len(sample_dishes)} sample dishes...")
        result = await db.dishes.insert_many(sample_dishes)
        print(f"✅ Successfully inserted {len(result.inserted_ids)} dishes!")
        
        # Verify insertion
        count = await db.dishes.count_documents({})
        print(f"✅ Total dishes in database: {count}")
        
        # Show first dish as sample
        first_dish = await db.dishes.find_one({})
        if first_dish:
            print(f"\n📋 Sample dish:")
            print(f"  - Name: {first_dish['name']}")
            print(f"  - Category: {first_dish['category']}")
            print(f"  - Rating: {first_dish['average_rating']} ⭐")
            print(f"  - Likes: {first_dish['like_count']}")
        
    except Exception as e:
        print(f"❌ Error seeding dishes: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(seed_dishes())
