import os
from pymongo import MongoClient
import certifi
from dotenv import load_dotenv

load_dotenv()
uri = os.getenv("MONGO_URI")
print(f"Connecting to: {uri[:20]}...")

try:
    client = MongoClient(uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    print("✅ MongoDB connection successful!")
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")
