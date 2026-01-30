"""
Telegram Mention Bot - @all
بوت تيليجرام محسّن لعمل منشن لجميع الأعضاء
- يتتبع الأعضاء تلقائياً
- إضافة أعضاء يدوياً بـ /add
- يحفظ الأعضاء بشكل دائم
- استخدم @all لمنشن الجميع
"""

import os
import json
import asyncio
import re
import html
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from flask import Flask
from threading import Thread
import sys
from dotenv import load_dotenv
import certifi

# إعداد Flask (عشان Render ما يطفي البوت)
app = Flask('')

@app.route('/')
def home():
    return "I am alive! 🤖"

def run_http():
    # Render بيحدد البورت تلقائياً في متغير البيئة PORT
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_http)
    t.start()

# إعداد الترميز للويندوز
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import logging

# إعداد الـ Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# تحميل المتغيرات البيئية
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# تكوين MongoDB
db = None
members_collection = None
settings_collection = None
tags_collection = None

def init_db():
    global db, members_collection, settings_collection, tags_collection
    if db is not None:
        return
    if MONGO_URI:
        try:
            from pymongo import MongoClient
            # استخدام certifi لحل مشاكل SSL
            client = MongoClient(MONGO_URI, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
            db = client.get_database("telegram_bot_db")
            members_collection = db.members
            settings_collection = db.settings
            tags_collection = db.tags
            print("✅ تم الاتصال بقاعدة بيانات MongoDB بنجاح!")
        except Exception as e:
            print(f"❌ فشل الاتصال بقاعدة البيانات: {e}")

DATA_FILE = "members_data.json"
SETTINGS_FILE = "settings.json"
TAGS_FILE = "tags.json"

# المخزن المؤقت في الذاكرة
group_members = {}  # {chat_id: {user_id: data}}
group_settings = {} # {chat_id: {setting: value}}
group_tags = {}     # {chat_id: {tag_name: [user_ids]}}


def load_data(chat_id=None):
    """تحميل بيانات الأعضاء (MongoDB أو ملف)"""
    if members_collection is not None:
        if chat_id:
            # تحميل مجموعة محددة فقط لسرعة الأداء
            doc = members_collection.find_one({"_id": str(chat_id)})
            if doc:
                group_members[str(chat_id)] = doc["members"]
                return {str(chat_id): doc["members"]}
            return {}
        
        # تحميل الكل (لأغراض الإحصاء فقط)
        data = {}
        cursor = members_collection.find({})
        for doc in cursor:
            data[doc["_id"]] = doc["members"]
        return data
    
    # تحميل من ملف محلي
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_data(data, chat_id=None):
    """حفظ بيانات الأعضاء (MongoDB أو ملف)"""
    if members_collection is not None:
        if chat_id:
            # حفظ مجموعة محددة فقط
            members = data.get(str(chat_id))
            if members:
                members_collection.update_one(
                    {"_id": str(chat_id)},
                    {"$set": {"members": members}},
                    upsert=True
                )
            return
            
        # الحفظ في MongoDB للكل
        for cid, members in data.items():
            members_collection.update_one(
                {"_id": str(cid)},
                {"$set": {"members": members}},
                upsert=True
            )
        return

    # الحفظ في ملف محلي
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_settings(chat_id=None):
    """تحميل الإعدادات (MongoDB أو ملف)"""
    if settings_collection is not None:
        if chat_id:
            doc = settings_collection.find_one({"_id": str(chat_id)})
            if doc and "settings" in doc:
                group_settings[str(chat_id)] = doc["settings"]
                return {str(chat_id): doc["settings"]}
            return {}
            
        data = {}
        cursor = settings_collection.find({})
        for doc in cursor:
            if "settings" in doc:
                data[doc["_id"]] = doc["settings"]
        return data

    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_settings(data, chat_id=None):
    """حفظ الإعدادات (MongoDB أو ملف)"""
    if settings_collection is not None:
        if chat_id:
            settings = data.get(str(chat_id))
            if settings:
                settings_collection.update_one(
                    {"_id": str(chat_id)},
                    {"$set": {"settings": settings}},
                    upsert=True
                )
            return
            
        for cid, settings in data.items():
            settings_collection.update_one(
                {"_id": str(cid)},
                {"$set": {"settings": settings}},
                upsert=True
            )
        return

    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_tags(chat_id=None):
    """تحميل المنشن المخصص"""
    if tags_collection is not None:
        if chat_id:
            doc = tags_collection.find_one({"_id": str(chat_id)})
            if doc:
                group_tags[str(chat_id)] = doc["tags"]
                return {str(chat_id): doc["tags"]}
            return {}
        for doc in tags_collection.find():
            group_tags[doc["_id"]] = doc["tags"]
    else:
        if os.path.exists(TAGS_FILE):
            with open(TAGS_FILE, "r", encoding='utf-8') as f:
                return json.load(f)
    return {}


def save_tags(data, chat_id):
    if tags_collection is not None:
        tags_collection.replace_one({"_id": str(chat_id)}, {"tags": data}, upsert=True)
    else:
        with open(TAGS_FILE, "w", encoding='utf-8') as f:
            json.dump(group_tags, f, ensure_ascii=False, indent=4)


def init_tags(chat_id):
    chat_id = str(chat_id)
    if chat_id not in group_tags:
        group_tags[chat_id] = {}
        loaded_tags = load_tags(chat_id)
        if loaded_tags and chat_id in loaded_tags:
            group_tags[chat_id] = loaded_tags[chat_id]


# Loading data locally (will be called in create_app)
group_members = {}
group_settings = {}
group_tags = {}

def init_data(chat_id=None):
    global group_members, group_settings, group_tags
    init_db()
    
    if chat_id:
        chat_id = str(chat_id)
        # فقط تحميل إذا لم يكن موجوداً في الكاش أو نريد تحديثه
        if chat_id not in group_members:
            load_data(chat_id)
        if chat_id not in group_settings:
            load_settings(chat_id)
        if chat_id not in group_tags:
            init_tags(chat_id) # Use init_tags to load for specific chat_id
    else:
        # تحميل الكل (عند بدء البوت محلياً فقط)
        group_members = load_data() or {}
        group_settings = load_settings() or {}
        group_tags = load_tags() or {}
    
    logger.info(f"📊 Initialization complete. Groups in memory: {len(group_members)}")

# group_members = load_data()  <-- MOVED
# group_settings = load_settings() <-- MOVED


async def is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """التحقق مما إذا كان المستخدم مشرفاً"""
    if not update.effective_chat or update.effective_chat.type == "private":
        return True
        
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ["creator", "administrator"]
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البداية"""
    await update.message.reply_text(
        "🤖 مرحباً! أنا بوت المنشن\n\n"
        "📋 كيفية الاستخدام:\n"
        "• أضفني للمجموعة وامنحني صلاحيات أدمن\n"
        "• أرسل @all لمنشن جميع الأعضاء\n\n"
        "📌 الأوامر (للمشرفين فقط 👮‍♂️):\n"
        "/add @user1 @user2 - إضافة أعضاء يدوياً\n"
        "/add_id 12345 Name - إضافة عضو بالآيدي\n"
        "/boost @user 5 - زيادة عدد مرّات منشن شخص\n"
        "/unboost @user - إعادة المنشن للوضع الطبيعي\n"
        "/id - معرفة الآيدي (بالرد على الرسالة)\n"
        "/set_msg <message> - تغيير رسالة المنشن\n"
        "/remove @user - حذف عضو\n"
        "/list - عرض الأعضاء المحفوظين\n"
        "/count - عدد الأعضاء المحفوظين\n"
        "/sync_from <ID> - نسخ الأعضاء من مجموعة أخرى\n"
        "/add_tag #tag - إنشاء تاج مخصص\n"
        "/del_tag #tag - حذف تاج مخصص\n"
        "/add_to_tag #tag @user - إضافة عضو لتاج\n"
        "/rem_from_tag #tag @user - حذف عضو من تاج\n"
        "/tags - عرض كل التاجات المخصصة\n"
        "/clean - تنظيف القائمة من الحسابات المحذوفة أو التي غادرت\n"
        "/clear - مسح كل الأعضاء\n\n"
        "⚡ يتم حفظ الأعضاء بشكل دائم!"
    )


# ... (deleted redundant track_user)


async def add_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة أعضاء يدوياً بالـ username"""
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("⚠️ هذا الأمر يعمل في المجموعات فقط!")
        return
        
    if not await is_user_admin(update, context):
        return
    
    chat_id = str(update.effective_chat.id)
    args = context.args
    if not args:
        await update.message.reply_text("❌ الاستخدام: /add @user1 @user2")
        return
    
    init_data(chat_id)
    added = []
    not_in_group = []
    
    for username in args:
        uname = username.replace("@", "").strip()
        if not uname: continue
        
        # محاولة التحقق إذا كان في المجموعة قبل الإضافة
        try:
            member = await context.bot.get_chat_member(chat_id, f"@{uname}")
            if member.status in ["left", "kicked"]:
                not_in_group.append(f"@{uname}")
                continue
        except Exception:
            # إذا فشل الفحص باليوزرنيم، لا نمنع الإضافة لكن ننبه
            pass

        uid = f"username_{uname.lower()}"
        group_members[chat_id][uid] = {
            "username": uname,
            "multiplier": 1
        }
        added.append(f"@{uname}")
    
    if added or not_in_group:
        save_data(group_members, chat_id)
        msg = ""
        if added: msg += f"✅ تم إضافة: {', '.join(added)}\n"
        if not_in_group: msg += f"⚠️ تنبيه: هؤلاء ليسوا في المجموعة: {', '.join(not_in_group)}\n"
        msg += f"👥 إجمالي الأعضاء: {len(group_members[chat_id])}"
        await update.message.reply_text(msg)


async def add_member_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة عضو عن طريق الآيدي والاسم"""
    if not await is_user_admin(update, context): return
    chat_id = str(update.effective_chat.id)
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ الاستخدام: /add_id <ID> <Name>")
        return
    
    user_id, name = args[0], " ".join(args[1:])
    if not user_id.isdigit():
        await update.message.reply_text("❌ الآيدي يجب أن يكون أرقاماً")
        return
    
    init_data(chat_id)
    if chat_id not in group_members: group_members[chat_id] = {}
    group_members[chat_id][user_id] = {"username": None, "first_name": name, "full_name": name}
    save_data(group_members, chat_id)
    await update.message.reply_text(f"✅ تم إضافة {name}\n🆔 {user_id}")


async def delete_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف عضو من القائمة"""
    if not await is_user_admin(update, context): return
    chat_id = str(update.effective_chat.id)
    text = update.message.text
    usernames = re.findall(r'@(\w+)', text)
    
    if not usernames:
        await update.message.reply_text("❌ الاستخدام: /remove @username")
        return
    
    init_data(chat_id)
    removed = []
    if chat_id in group_members:
        for username in usernames:
            for uid in list(group_members[chat_id].keys()):
                if (group_members[chat_id][uid].get("username") or "").lower() == username.lower():
                    del group_members[chat_id][uid]
                    removed.append(f"@{username}")
                    break
    
    save_data(group_members, chat_id)
    await update.message.reply_text(f"✅ تم حذف: {', '.join(removed)}")


async def clear_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مسح كل الأعضاء من المجموعة"""
    if not await is_user_admin(update, context): return
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    if chat_id in group_members:
        count = len(group_members[chat_id])
        group_members[chat_id] = {}
        save_data(group_members, chat_id)
        await update.message.reply_text(f"🗑️ تم مسح {count} عضو")


async def boost_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحديد عدد مرات منشن مستخدم معين عند عمل @all"""
    if not await is_user_admin(update, context):
        return
    
    chat_id = str(update.effective_chat.id)
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text(
            "❌ الاستخدام: /boost @username 3\n"
            "هذا سيجعل البوت يمنشن هذا الشخص 3 مرات في كل مرة تطلب فيها @all"
        )
        return
    
    username = args[0].replace("@", "").lower()
    try:
        multiplier = int(args[1])
        if multiplier < 1 or multiplier > 10:
            await update.message.reply_text("⚠️ المعامل يجب أن يكون بين 1 و 10")
            return
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح للمعامل")
        return

    init_data(chat_id)
    
    found = False
    for uid, data in group_members[chat_id].items():
        if (data.get("username") or "").lower() == username:
            group_members[chat_id][uid]["multiplier"] = multiplier
            found = True
            break
    
    if found:
        save_data(group_members, chat_id)
        await update.message.reply_text(f"✅ تم ضبط Boost بنسبة x{multiplier} للمستخدم @{username}")
    else:
        await update.message.reply_text(f"❌ لم يتم العثور على @{username} في قاعدة بيانات هذه المجموعة.\nتأكد أنه أرسل رسالة سابقاً أو أضفه يدوياً.")


async def unboost_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعادة معامل المنشن للقيمة الافتراضية (1)"""
    if not await is_user_admin(update, context): return
    chat_id = str(update.effective_chat.id)
    args = context.args
    if not args:
        await update.message.reply_text("❌ الاستخدام: /unboost @username")
        return
    
    username = args[0].replace("@", "").lower()
    init_data(chat_id)
    found = False
    if chat_id in group_members:
        for uid, data in group_members[chat_id].items():
            if (data.get("username") or "").lower() == username:
                group_members[chat_id][uid]["multiplier"] = 1
                found = True
                break
    
    if found:
        save_data(group_members, chat_id)
        await update.message.reply_text(f"✅ تم إلغاء الـ Boost للمستخدم @{username}")
    else:
        await update.message.reply_text(f"❌ المستخدم @{username} غير موجود")


async def track_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تتبع المستخدمين تلقائياً عند إرسال أي رسالة"""
    if not update.effective_chat or not update.effective_user:
        return
    
    if update.effective_chat.type not in ["group", "supergroup"]:
        return
    
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    if user.is_bot: return
    
    init_data(chat_id)
    
    user_id = str(user.id)
    needs_save = False
    
    # دمج المعرفات المؤقتة
    if user.username:
        temp_id = f"username_{user.username.lower()}"
        if temp_id in group_members[chat_id]:
            old_multiplier = group_members[chat_id][temp_id].get("multiplier", 1)
            del group_members[chat_id][temp_id]
            group_members[chat_id][user_id] = {
                "username": user.username,
                "first_name": user.first_name or "User",
                "full_name": user.full_name or "User",
                "multiplier": old_multiplier
            }
            needs_save = True
    
    if user_id not in group_members[chat_id]:
        group_members[chat_id][user_id] = {
            "username": user.username,
            "first_name": user.first_name or "User",
            "full_name": user.full_name or "User",
            "multiplier": 1
        }
        needs_save = True
    else:
        # تحديث البيانات مع الحفاظ على الـ multiplier
        data = group_members[chat_id][user_id]
        if data.get("username") != user.username or data.get("first_name") != user.first_name:
            data.update({
                "username": user.username,
                "first_name": user.first_name or "User",
                "full_name": user.full_name or "User"
            })
            needs_save = True
            
    if needs_save:
        save_data(group_members, chat_id)


async def clean_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظيف القائمة يدوياً من الأعضاء غير الموجودين"""
    if not await is_user_admin(update, context): return
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    
    if chat_id not in group_members or not group_members[chat_id]:
        await update.message.reply_text("📭 القائمة فارغة أصلاً!")
        return
    
    status_msg = await update.message.reply_text("⏳ جاري فحص القائمة وتنظيف 'الأشباح'...")
    
    ids_to_remove = []
    unique_uids = list(group_members[chat_id].keys())
    
    def find_id_by_username(username):
        uname = username.lower()
        for cid in group_members:
            for uid_key, udata in group_members[cid].items():
                if uid_key.isdigit() and (udata.get("username") or "").lower() == uname:
                    return int(uid_key)
        return None

    ids_to_remove = []
    unique_uids = list(group_members[chat_id].keys())
    
    async def check_single_member(uid):
        data = group_members[chat_id][uid]
        lookup_target = None
        if uid.isdigit():
            lookup_target = int(uid)
        else:
            uname = data.get("username") or uid.replace("username_", "")
            lookup_target = find_id_by_username(uname) or f"@{uname}"
            
        try:
            member = await context.bot.get_chat_member(chat_id, lookup_target)
            if member.status in ["left", "kicked"]:
                return uid
        except Exception as e:
            err = str(e).lower()
            if uid.isdigit() and any(x in err for x in ["user not found", "member not found", "not a member", "invalid user"]):
                return uid
        return None

    # فحص متوازي لتقليل استهلاك وقت الجلسة
    results = await asyncio.gather(*(check_single_member(uid) for uid in unique_uids))
    ids_to_remove = [uid for uid in results if uid]

    removed_count = len(ids_to_remove)
    if removed_count > 0:
        for uid in ids_to_remove:
            if uid in group_members[chat_id]:
                del group_members[chat_id][uid]
        save_data(group_members, chat_id)
        
    final_count = len(group_members[chat_id])
    await status_msg.edit_text(
        f"✅ تمت عملية التنظيف (الوضع الآمن)!\n\n"
        f"🧹 تم حذف: {removed_count} عضو مؤكد خروجهم.\n"
        f"👥 الأعضاء المتبقين: {final_count}\n\n"
        "💡 نصيحة: للأعضاء المضافين باليوزرنيم، يفضل أن يرسلوا رسالة واحدة في المجموعة ليتمكن البوت من فحصهم بدقة مستقبلاً."
    )


async def auto_add_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة الأعضاء الجدد للقائمة تلقائياً عند انضمامهم"""
    if not update.message or not update.message.new_chat_members:
        return
        
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    added_names = []
    
    for member in update.message.new_chat_members:
        if member.is_bot: continue
        
        uid = str(member.id)
        group_members[chat_id][uid] = {
            "first_name": member.first_name,
            "last_name": member.last_name,
            "full_name": member.full_name,
            "username": member.username,
            "multiplier": 1
        }
        added_names.append(member.full_name)
    
    if added_names:
        save_data(group_members, chat_id)
        logger.info(f"✨ Auto-added {len(added_names)} new members to {chat_id}")


async def sync_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نسخ أعضاء من مجموعة إلى أخرى"""
    if not await is_user_admin(update, context): return
    chat_id = str(update.effective_chat.id)
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "❌ الاستخدام: /sync_from <ID المجموعه>\n"
            "يمكنك الحصول على آيدي المجموعة من أمر /status في تلك المجموعة."
        )
        return
    
    source_chat_id = args[0]
    init_data(source_chat_id)
    
    if source_chat_id not in group_members or not group_members[source_chat_id]:
        await update.message.reply_text("❌ لم يتم العثور على أعضاء في المجموعة المصدر.")
        return
        
    init_data(chat_id)
    source_count = len(group_members[source_chat_id])
    
    # دمج الأعضاء
    for uid, data in group_members[source_chat_id].items():
        if uid not in group_members[chat_id]:
            group_members[chat_id][uid] = data
            
    save_data(group_members, chat_id)
    await update.message.reply_text(f"✅ تم نسخ {source_count} عضو بنجاح!\n👥 العدد الكلي الآن: {len(group_members[chat_id])}")


# --- نظام التاجات المخصصة ---

async def create_tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إنشاء تاج جديد"""
    if not await is_user_admin(update, context): return
    chat_id = str(update.effective_chat.id)
    init_tags(chat_id)
    
    if not context.args:
        await update.message.reply_text("❌ الاستخدام: /add_tag #tagname")
        return
        
    tag = context.args[0].lower()
    if not tag.startswith("#"): tag = "#" + tag
    
    if tag in group_tags[chat_id]:
        await update.message.reply_text(f"⚠️ التاج {tag} موجود بالفعل!")
        return
        
    group_tags[chat_id][tag] = []
    save_tags(group_tags[chat_id], chat_id)
    await update.message.reply_text(f"✅ تم إنشاء التاج {tag} بنجاح!")


async def delete_tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف تاج"""
    if not await is_user_admin(update, context): return
    chat_id = str(update.effective_chat.id)
    init_tags(chat_id)
    
    if not context.args:
        await update.message.reply_text("❌ الاستخدام: /del_tag #tagname")
        return
        
    tag = context.args[0].lower()
    if not tag.startswith("#"): tag = "#" + tag
    
    if tag not in group_tags[chat_id]:
        await update.message.reply_text(f"❌ التاج {tag} غير موجود!")
        return
        
    del group_tags[chat_id][tag]
    save_tags(group_tags[chat_id], chat_id)
    await update.message.reply_text(f"⚠️ تم حذف التاج {tag}!")


async def add_to_tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة أعضاء لتاج"""
    if not await is_user_admin(update, context): return
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    init_tags(chat_id)
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ الاستخدام: /add_to_tag #tag @user1 @user2")
        return
        
    tag = context.args[0].lower()
    if not tag.startswith("#"): tag = "#" + tag
    
    if tag not in group_tags[chat_id]:
        await update.message.reply_text(f"❌ التاج {tag} غير موجود! أنشئه أولاً بـ /add_tag")
        return
        
    added = []
    for username in context.args[1:]:
        uname = username.replace("@", "").strip().lower()
        if not uname: continue
        
        target_uid = None
        for uid, data in group_members[chat_id].items():
            if (data.get("username") or "").lower() == uname:
                target_uid = uid
                break
        
        if not target_uid:
            for cid in group_members:
                for uid_key, data in group_members[cid].items():
                    if uid_key.isdigit() and (data.get("username") or "").lower() == uname:
                        target_uid = uid_key
                        break
                if target_uid: break

        if not target_uid:
            target_uid = f"username_{uname}"
            if target_uid not in group_members[chat_id]:
                group_members[chat_id][target_uid] = {"username": uname, "multiplier": 1}
                save_data(group_members, chat_id)

        if target_uid not in group_tags[chat_id][tag]:
            group_tags[chat_id][tag].append(target_uid)
            added.append(f"@{uname}")
            
    if added:
        save_tags(group_tags[chat_id], chat_id)
        await update.message.reply_text(f"✅ تمت إضافة {len(added)} أعضاء للتاج {tag}")
    else:
        await update.message.reply_text("⚠️ لم يتم إضافة أي عضو جديد.")


async def rem_from_tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف أعضاء من تاج"""
    if not await is_user_admin(update, context): return
    chat_id = str(update.effective_chat.id)
    init_tags(chat_id)
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ الاستخدام: /rem_from_tag #tag @user")
        return
        
    tag = context.args[0].lower()
    if not tag.startswith("#"): tag = "#" + tag
    
    if tag not in group_tags[chat_id]:
        await update.message.reply_text(f"❌ التاج {tag} غير موجود!")
        return
        
    removed = []
    for username in context.args[1:]:
        uname = username.replace("@", "").strip().lower()
        if not uname: continue
        
        target_indices = []
        for i, uid in enumerate(group_tags[chat_id][tag]):
            if uid == f"username_{uname}":
                target_indices.append(i)
            elif uid.isdigit():
                found = False
                for cid in group_members:
                    if uid in group_members[cid] and (group_members[cid][uid].get("username") or "").lower() == uname:
                        found = True
                        break
                if found: target_indices.append(i)

        for i in reversed(target_indices):
            group_tags[chat_id][tag].pop(i)
            removed.append(f"@{uname}")
                
    if removed:
        save_tags(group_tags[chat_id], chat_id)
        await update.message.reply_text(f"✅ تم حذف {len(removed)} أعضاء من التاج {tag}")
    else:
        await update.message.reply_text("❌ لم يتم العثور على الأسماء المحددة في هذا التاج.")


async def list_tags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض كل التاجات"""
    chat_id = str(update.effective_chat.id)
    init_tags(chat_id)
    
    if not group_tags.get(chat_id):
        await update.message.reply_text("📭 لا يوجد تاجات مخصصة بعد.")
        return
        
    msg = "📋 **التاجات المخصصة:**\n\n"
    for tag, members in group_tags[chat_id].items():
        msg += f"🔹 {tag} ({len(members)} عضو)\n"
    
    msg += "\n💡 استخدم `#tagname` لعمل منشن للمجموعة المحددة."
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def mention_tag(update: Update, context: ContextTypes.DEFAULT_TYPE, tag_name: str):
    """منشن أعضاء تاج معين"""
    if not await is_user_admin(update, context): return
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    init_tags(chat_id)
    
    if tag_name not in group_tags[chat_id] or not group_tags[chat_id][tag_name]:
        return

    uids = group_tags[chat_id][tag_name]
    valid_members = []
    
    for uid in uids:
        if uid in group_members[chat_id]:
            valid_members.append((uid, group_members[chat_id][uid]))
        else:
            found_data = None
            for cid in group_members:
                if uid in group_members[cid]:
                    found_data = group_members[cid][uid]
                    break
            if found_data:
                valid_members.append((uid, found_data))

    if not valid_members: return

    batch_size = 5
    for i in range(0, len(valid_members), batch_size):
        batch = valid_members[i:i+batch_size]
        mentions = []
        for uid, data in batch:
            name = data.get("full_name") or data.get("first_name") or "User"
            if uid.isdigit():
                mentions.append(f'<a href="tg://user?id={uid}">{html.escape(name)}</a>')
            else:
                uname = data.get("username") or uid.replace("username_", "")
                mentions.append(f"@{uname}")
        
        await update.message.reply_text(" ".join(mentions), parse_mode=ParseMode.HTML)
        await asyncio.sleep(0.3)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل والتحقق من @all مع إمكانية تحديد عدد المرات"""
    if not update.message or not update.message.text:
        return
    
    text = update.message.text
    # 1. التحقق من @all
    match_all = re.search(r'(?:^|\s)@(?:all|everyone)(?:\s+(\d+))?\b', text, re.IGNORECASE)
    if match_all:
        rounds = 1
        if match_all.group(1):
            try:
                rounds = int(match_all.group(1))
                if rounds < 1: rounds = 1
                if rounds > 10: rounds = 10
            except: pass
        await mention_all(update, context, rounds)
        return

    # 2. التحقق من التاجات المخصصة (#tagname)
    chat_id = str(update.effective_chat.id)
    init_tags(chat_id)
    for tag in group_tags.get(chat_id, {}):
        if tag in text.lower():
            await mention_tag(update, context, tag)
            return


async def mention_all(update: Update, context: ContextTypes.DEFAULT_TYPE, total_rounds=1):
    """منشن الجميع مع دعم لعدة جولات والـ Boost"""
    if not await is_user_admin(update, context):
        return

    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    
    if chat_id not in group_members or not group_members[chat_id]:
        await update.message.reply_text("📭 القائمة فارغة!")
        return

    # بناء القائمة مع مراعاة الـ Multiplier والتحقق من الوجود
    valid_members = []
    ids_to_remove = []
    
    def find_id_by_username(username):
        """البحث عن المعرف الرقمي للمستخدم في قاعدة البيانات العالمية"""
        uname = username.lower()
        for cid in group_members:
            for uid_key, udata in group_members[cid].items():
                if uid_key.isdigit() and (udata.get("username") or "").lower() == uname:
                    return int(uid_key)
        return None

    ids_to_remove = []
    unique_uids = list(group_members[chat_id].keys())
    
    # تخطي فحص الوجود لزيادة السرعة في المجموعات الكبيرة على Vercel
    # يمكن للمدراء استخدام /clean لتنظيف القائمة يدوياً
    
    valid_members = []
    for uid in unique_uids:
        data = group_members[chat_id][uid]
        multiplier = data.get("multiplier", 1)
        # الحد الأقصى للـ boost هو 5 لضمان عدم تجاوز الوقت
        safe_multiplier = min(multiplier, 5)
        for _ in range(safe_multiplier):
            valid_members.append((uid, data))

    total_members = len(valid_members)
    if total_members == 0:
        await update.message.reply_text("📭 القائمة فارغة!")
        return

    batch_size = 5 # العودة لـ 5 بناءً على طلب المستخدم
    total_batches = (total_members + batch_size - 1) // batch_size
    
    custom_msg = group_settings.get(chat_id, {}).get("mention_message", "📣")
    reply_to_id = update.message.reply_to_message.message_id if update.message.reply_to_message else update.message.message_id

    # البدء بالجولات مع ضمان إرسال رسالة الإكمال
    try:
        for r in range(1, total_rounds + 1):
            round_prefix = f"({r}/{total_rounds}) " if total_rounds > 1 else ""
            
            for i in range(0, total_members, batch_size):
                batch = valid_members[i:i + batch_size]
                mentions = []
                
                for uid, data in batch:
                    if data.get("username"):
                        mentions.append(f"@{data['username']}")
                    else:
                        name = html.escape(data['first_name'])
                        mentions.append(f'<a href="tg://user?id={uid}">{name}</a>')
                
                batch_num = (i // batch_size) + 1
                progress = f"{round_prefix}[{batch_num}/{total_batches}]"
                message = f"{custom_msg} {progress}\n" + " ".join(mentions)
                
                # محاولة إرسال الدفعة مع معالجة الأخطاء والـ Rate Limit
                batch_sent = False
                max_retries = 3
                retry_count = 0
                
                while not batch_sent and retry_count < max_retries:
                    try:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=message,
                            reply_to_message_id=reply_to_id,
                            parse_mode=ParseMode.HTML
                        )
                        logger.info(f"✅ Sent batch {batch_num}/{total_batches}")
                        batch_sent = True
                    except Exception as e:
                        retry_count += 1
                        err_msg = str(e).lower()
                        logger.error(f"❌ Error in Round {r} Batch {batch_num} (Try {retry_count}): {e}")
                        
                        if "retry after" in err_msg:
                            import re
                            match = re.search(r'after (\d+)', err_msg)
                            seconds = int(match.group(1)) if match else 10
                            wait_time = seconds + 1
                            logger.warning(f"⏳ Rate limited! Waiting {wait_time}s then retrying...")
                            await asyncio.sleep(wait_time)
                        else:
                            # خطأ آخر (مثل رسالة طويلة جداً أو مشكلة مؤقتة)
                            await asyncio.sleep(1)
                            if retry_count >= max_retries:
                                logger.error(f"Skipping Batch {batch_num} after {max_retries} attempts.")
                
                # تأخير بسيط جداً لزيادة السرعة
                await asyncio.sleep(0.05)
    except Exception as global_e:
        logger.error(f"🔴 CRITICAL ERROR in mention_all: {global_e}")
    finally:
        # إرسال رسالة الإكمال دائماً
        completion_msgs = [
            "ارحبوا تراحيب المطر 🌧️💙",
            "حياكم الله وبياكم جميعاً 👋🌸",
            "يا هلا والله ومية هلا بالجميع ❤️🙌",
            "ارحبوا يا الربع، على العين والراس 🫡👑",
            "يا هلا ومسهلا بالجميع، نورتوا 🌟✨",
            "ارحبوا ثم ارحبوا، حيا الله هالطلة 🙏✨",
            "حيّ الله الجميع، نورتوا المكان 👁️✨",
            "يا هلا ومية هلا، منورين والله 🌙🌟",
            "ارحبوا يا كرام، حياكم الله 🫡🔥",
            "يا هلا والله، نورتوا القعدة 💎✨",
            "حياكم الله في محلكم وبين أهلكم 🏠💫",
            "ارحبوا بالجميع، شرفتونا 🫡🌾",
            "يا هلا باللي وصلوا، نورتوا الدار 🚪✨",
            "حياكم الله، الجود من الموجود 👋❤️"
        ]
        import random
        try:
            await update.message.reply_text(random.choice(completion_msgs))
        except Exception as final_e:
            logger.error(f"Could not send completion message: {final_e}")


async def list_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة الأعضاء مع الـ Boost"""
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    
    if chat_id not in group_members or not group_members[chat_id]:
        await update.message.reply_text("📭 القائمة فارغة!")
        return
    
    lines = []
    for uid, data in group_members[chat_id].items():
        boost = f" (x{data['multiplier']})" if data.get("multiplier", 1) > 1 else ""
        if data.get("username"):
            lines.append(f"• @{data['username']}{boost}")
        else:
            lines.append(f"• {data['full_name']}{boost}")
    
    # عرض أول 100 لتجنب تجاوز حد الرسالة
    text = f"📋 الأعضاء المحفوظين ({len(lines)}):\n\n" + "\n".join(lines[:100])
    await update.message.reply_text(text)


async def count_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض عدد الأعضاء"""
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    count = len(group_members.get(chat_id, {}))
    await update.message.reply_text(f"👥 عدد الأعضاء: {count}")


async def bot_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حالة البوت مع عرض الآيدي"""
    if not await is_user_admin(update, context): return
    chat_id = str(update.effective_chat.id)
    db_status = "✅ متصل بـ MongoDB" if members_collection is not None else "⚠️ تخزين محلي"
    
    # تحديد البيئة
    env_type = "Render (Polling)" if "RENDER" in os.environ else "Vercel (Webhook)"
    
    await update.message.reply_text(
        f"⚙️ **حالة البوت:**\n\n"
        f"🆔 آيدي هذه المجموعة: `{chat_id}`\n"
        f"📊 المجموعات النشطة: {len(group_members)}\n"
        f"🗄 قاعدة البيانات: {db_status}\n"
        f"🚀 الاستضافة: {env_type}",
        parse_mode=ParseMode.MARKDOWN
    )


def create_app(chat_id=None):
    """إنشاء التطبيق وإضافة المعالجات"""
    if not BOT_TOKEN: return None
    
    app = Application.builder().token(BOT_TOKEN).build()
    if chat_id:
        init_data(chat_id)
    else:
        init_db() # Just connect, don't load all
    
    handlers = [
        CommandHandler("start", start),
        CommandHandler("add", add_members),
        CommandHandler("add_id", add_member_id),
        CommandHandler("boost", boost_user),
        CommandHandler("unboost", unboost_user),
        CommandHandler("list", list_members),
        CommandHandler("remove", delete_members),
        CommandHandler("clear", clear_members),
        CommandHandler("sync_from", sync_from),
        CommandHandler("add_tag", create_tag),
        CommandHandler("del_tag", delete_tag),
        CommandHandler("add_to_tag", add_to_tag),
        CommandHandler("rem_from_tag", rem_from_tag),
        CommandHandler("tags", list_tags),
        CommandHandler("clean", clean_list),
        CommandHandler("status", bot_status),
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, auto_add_new_member),
        # MessageHandler(filters.ALL, track_user),  # تم نقله للبداية في مجموعة مستقلة
        MessageHandler(~filters.COMMAND, handle_message)
    ]
    
    # إضافة track_user في البداية (لتتبع كل الرسائل)
    app.add_handler(MessageHandler(filters.ALL, track_user), group=-1)
    
    for handler in handlers:
        app.add_handler(handler)
            
    return app


def main():
    """تشغيل البوت بنظام Polling (محلياً أو Render)"""
    application = create_app()
    if not application:
        return

    print("🚀 جاري تشغيل البوت...")
    print(f"📊 تم تحميل بيانات {len(group_members)} مجموعة")
    
    print("✅ البوت يعمل الآن!")
    print("📌 الأوامر: /add, /remove, /list, /count, /clear, @all")
    
    # تشغيل سيرفر الويب الوهمي (Keep Alive)
    keep_alive()

    # بدء تشغيل البوت (مع حذف الويب هوك القديم لضمان العمل على Render)
    print("🚀 جاري تشغيل البوت بنظام Polling...")
    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
