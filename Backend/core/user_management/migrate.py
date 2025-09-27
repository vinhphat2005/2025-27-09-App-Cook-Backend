"""
User Data Migration Script
Unified migration utility for converting from monolithic to normalized user structure
"""
import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.user_management.service import UserDataService


async def main():
    """Main migration function with interactive options"""
    print("🗄️  User Data Migration Utility")
    print("=" * 50)
    print("1. Migrate all users")
    print("2. Check migration status") 
    print("3. Exit")
    
    choice = input("\nSelect option (1-3): ").strip()
    
    if choice == "1":
        confirm = input("⚠️  This will migrate ALL users. Continue? (y/N): ").strip().lower()
        if confirm == 'y':
            result = await UserDataService.migrate_all_users()
            print(f"\n🎉 Migration Summary:")
            print(f"   Migrated: {result['migrated_users']} users")
            print(f"   Total: {result['total_users']} users")
        else:
            print("❌ Migration cancelled")
    
    elif choice == "2":
        await check_migration_status()
    
    elif choice == "3":
        print("👋 Goodbye!")
        return
    
    else:
        print("❌ Invalid choice")


async def check_migration_status():
    """Check how many users need migration"""
    from database.mongo import users_collection
    
    total_users = await users_collection.count_documents({})
    old_structure_users = await users_collection.count_documents({
        "$or": [
            {"followers": {"$exists": True}},
            {"following": {"$exists": True}},
            {"recipes": {"$exists": True}},
            {"favorite_dishes": {"$exists": True}}
        ]
    })
    
    migrated_users = total_users - old_structure_users
    
    print(f"\n📊 Migration Status:")
    print(f"   Total users: {total_users}")
    print(f"   Migrated: {migrated_users}")
    print(f"   Need migration: {old_structure_users}")
    
    if old_structure_users > 0:
        print(f"\n⚠️  {old_structure_users} users still need migration")
    else:
        print(f"\n✅ All users have been migrated!")


if __name__ == "__main__":
    asyncio.run(main())
