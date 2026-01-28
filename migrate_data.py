import json
import os
import pymongo
import certifi
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    print("❌ Error: MONGO_URI not found in .env file.")
    exit(1)

# Files to migrate
MEMBERS_FILE = "members_data.json"
SETTINGS_FILE = "settings.json"

def migrate():
    print("🚀 Starting migration to MongoDB...")
    
    try:
        # Connect to MongoDB
        client = pymongo.MongoClient(MONGO_URI, tlsCAFile=certifi.where())
        db = client["telegram_bot"]
        
        members_collection = db["members"]
        settings_collection = db["settings"]
        print("✅ Connected to MongoDB.")
        
        # Migrate Members
        if os.path.exists(MEMBERS_FILE):
            print(f"📂 Found {MEMBERS_FILE}. processing...")
            with open(MEMBERS_FILE, "r", encoding="utf-8") as f:
                members_data = json.load(f)
            
            if members_data:
                count = 0
                for chat_id, members_list in members_data.items():
                    # Upsert: Update if exists, Insert if new
                    members_collection.update_one(
                        {"_id": int(chat_id)},
                        {"$set": {"members": members_list}},
                        upsert=True
                    )
                    count += 1
                print(f"✅ Migrated {count} groups from members data.")
            else:
                print("⚠️ members_data.json is empty.")
        else:
            print(f"ℹ️ {MEMBERS_FILE} not found. Skipping.")

        # Migrate Settings
        if os.path.exists(SETTINGS_FILE):
            print(f"📂 Found {SETTINGS_FILE}. processing...")
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings_data = json.load(f)
            
            if settings_data:
                count = 0
                for chat_id, settings in settings_data.items():
                    settings_collection.update_one(
                        {"_id": int(chat_id)},
                        {"$set": {"settings": settings}},
                        upsert=True
                    )
                    count += 1
                print(f"✅ Migrated {count} settings documents.")
            else:
                print("⚠️ settings.json is empty.")
        else:
            print(f"ℹ️ {SETTINGS_FILE} not found. Skipping.")

        print("\n🎉 Migration completed successfully!")

    except Exception as e:
        print(f"\n❌ An error occurred: {e}")

if __name__ == "__main__":
    migrate()
