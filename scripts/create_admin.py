"""
Script to mark a user as admin in the database.
Usage:
  python create_admin.py --email admin@example.com

This sets the `role` field to 'admin' on the users collection.
It uses MONGODB_URI and DATABASE_NAME environment variables from .env
"""
import os
import argparse
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DATABASE_NAME", "cook_app")

parser = argparse.ArgumentParser()
parser.add_argument("--email", required=True, help="Email of user to promote to admin")
args = parser.parse_args()

if not MONGODB_URI:
    print("MONGODB_URI not set in environment")
    exit(1)

client = MongoClient(MONGODB_URI)
db = client[DB_NAME]
users = db["users"]

res = users.update_one({"email": args.email}, {"$set": {"role": "admin"}})
if res.matched_count:
    print(f"User {args.email} updated to role=admin")
else:
    print(f"No user found with email {args.email}")

client.close()