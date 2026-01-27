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

def init_db():
    global db, members_collection, settings_collection
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
            print("✅ تم الاتصال بقاعدة بيانات MongoDB بنجاح!")
        except Exception as e:
            print(f"❌ فشل الاتصال بقاعدة البيانات: {e}")

DATA_FILE = "members_data.json"
SETTINGS_FILE = "settings.json"


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


# Loading data locally (will be called in create_app)
group_members = {}
group_settings = {}

def init_data(chat_id=None):
    global group_members, group_settings
    init_db()
    
    if chat_id:
        chat_id = str(chat_id)
        # فقط تحميل إذا لم يكن موجوداً في الكاش أو نريد تحديثه
        if chat_id not in group_members:
            load_data(chat_id)
        if chat_id not in group_settings:
            load_settings(chat_id)
    else:
        # تحميل الكل (عند بدء البوت محلياً فقط)
        group_members = load_data() or {}
        group_settings = load_settings() or {}
    
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
        "/id - معرفة الآيدي (بالرد على الرسالة)\n"
        "/set_msg <message> - تغيير رسالة المنشن\n"
        "/remove @user - حذف عضو\n"
        "/list - عرض الأعضاء المحفوظين\n"
        "/count - عدد الأعضاء المحفوظين\n"
        "/clear - مسح كل الأعضاء\n\n"
        "⚡ يتم حفظ الأعضاء بشكل دائم!"
    )


async def track_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تتبع المستخدمين تلقائياً عند إرسال أي رسالة"""
    if not update.effective_chat or not update.effective_user:
        return
    
    # فقط في المجموعات
    if update.effective_chat.type not in ["group", "supergroup"]:
        return
    
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    # تجاهل البوتات
    if user.is_bot:
        return
    
    # إضافة المستخدم للقائمة
    if chat_id not in group_members:
        group_members[chat_id] = {}
    
    user_id = str(user.id)
    
    # التحقق من وجود ID مؤقت لهذا المستخدم (باليوزرنيم)
    if user.username:
        temp_id = f"username_{user.username.lower()}"
        if temp_id in group_members[chat_id]:
            # حذف الـ ID المؤقت لأننا سنضيف الـ ID الحقيقي
            del group_members[chat_id][temp_id]
            logger.info(f"Merged temporary member {temp_id} into real ID {user_id}")
    
    # إضافة أو تحديث المستخدم
    needs_save = False
    if user_id not in group_members[chat_id]:
        logger.info(f"🆕 New member detected: {user.full_name} ({user_id}) in chat {chat_id}")
        group_members[chat_id][user_id] = {
            "username": user.username,
            "first_name": user.first_name or "User",
            "full_name": user.full_name or "User"
        }
        needs_save = True
    else:
        # تحديث البيانات إذا تغيرت
        old_data = group_members[chat_id][user_id]
        new_username = user.username
        new_first_name = user.first_name or "User"
        
        if old_data.get("username") != new_username or old_data.get("first_name") != new_first_name:
            logger.info(f"🔄 Updating member info: {user_id} in chat {chat_id}")
            group_members[chat_id][user_id].update({
                "username": new_username,
                "first_name": new_first_name,
                "full_name": user.full_name or "User"
            })
            needs_save = True
            
    if needs_save:
        # الحفظ في الخلفية لعدم تعطيل الرد
        # ملاحظة: في Vercel Serverless يفضل الانتظار لضمان الحفظ
        # سأتركه كـ await لضمان الاستقرار في بيئة الـ Webhook
        save_data(group_members, chat_id)


async def add_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة أعضاء يدوياً بالـ username"""
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("⚠️ هذا الأمر يعمل في المجموعات فقط!")
        return
        
    if not await is_user_admin(update, context):
        return
    
    chat_id = str(update.effective_chat.id)
    text = update.message.text
    
    # استخراج الـ usernames من الرسالة
    usernames = re.findall(r'@(\w+)', text)
    
    if not usernames:
        await update.message.reply_text(
            "❌ الاستخدام الصحيح:\n"
            "/add @user1 @user2 @user3\n\n"
            "مثال:\n"
            "/add @ahmad @sara @omar"
        )
        return
    
    if chat_id not in group_members:
        group_members[chat_id] = {}
    
    added = []
    already_exists = []
    
    for username in usernames:
        # التحقق إذا كان الـ username موجود بالفعل
        exists = False
        for uid, data in group_members[chat_id].items():
            stored_username = data.get("username") or ""
            if stored_username.lower() == username.lower():
                exists = True
                already_exists.append(f"@{username}")
                break
        
        if not exists:
            # إضافة بـ ID مؤقت (username كـ ID)
            temp_id = f"username_{username.lower()}"
            group_members[chat_id][temp_id] = {
                "username": username,
                "first_name": username,
                "full_name": username
            }
            added.append(f"@{username}")
    
    save_data(group_members)
    
    response = ""
    if added:
        response += f"✅ تم إضافة: {', '.join(added)}\n"
    if already_exists:
        response += f"⚠️ موجودين مسبقاً: {', '.join(already_exists)}\n"
    
    response += f"\n👥 إجمالي الأعضاء: {len(group_members[chat_id])}"
    
    await update.message.reply_text(response)


async def add_member_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة عضو عن طريق الآيدي والاسم"""
    logger.info(f"Command /add_id received from {update.effective_user.id} in chat {update.effective_chat.id}")
    logger.info(f"Args: {context.args}")

    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("⚠️ هذا الأمر يعمل في المجموعات فقط!")
        return
    
    chat_id = str(update.effective_chat.id)
    args = context.args
    
    if not await is_user_admin(update, context):
        return
    
    if len(args) < 2:
        await update.message.reply_text(
            "❌ الاستخدام الصحيح:\n"
            "/add_id <الآيدي> <الاسم>\n\n"
            "مثال:\n"
            "/add_id 123456789 احمد"
        )
        return
    
    user_id = args[0]
    name = " ".join(args[1:])
    
    # التحقق من أن الآيدي أرقام فقط
    if not user_id.isdigit():
        await update.message.reply_text("❌ الآيدي يجب أن يتكون من أرقام فقط!")
        return
    
    if chat_id not in group_members:
        group_members[chat_id] = {}
        
    group_members[chat_id][user_id] = {
        "username": None,
        "first_name": name,
        "full_name": name
    }
    
    save_data(group_members)
    
    await update.message.reply_text(
        f"✅ تم إضافة العضو بنجاح!\n"
        f"👤 الاسم: {name}\n"
        f"🆔 الآيدي: {user_id}\n\n"
        f"👥 إجمالي الأعضاء: {len(group_members[chat_id])}"
    )


async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معرفة الآيدي للشخص بالرد على رسالته"""
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ قم بالرد على رسالة الشخص لمعرفة الآيدي الخاص به")
        return
    
    user = update.message.reply_to_message.from_user
    await update.message.reply_text(
        f"👤 الاسم: {user.full_name}\n"
        f"🆔 الآيدي: `{user.id}`",
        parse_mode=ParseMode.MARKDOWN
    )


async def set_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تغيير رسالة المنشن"""
    if not await is_user_admin(update, context):
        return
    
    chat_id = str(update.effective_chat.id)
    args = context.args
    
    if not args:
        await update.message.reply_text("❌ الاستخدام: /set_msg <الرسالة الجديدة>")
        return
        
    new_message = " ".join(args)
    
    if chat_id not in group_settings:
        group_settings[chat_id] = {}
    
    group_settings[chat_id]["mention_message"] = new_message
    save_settings(group_settings)
    
    await update.message.reply_text(f"✅ تم تغيير رسالة المنشن إلى:\n{new_message}")


async def remove_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف عضو من القائمة"""
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("⚠️ هذا الأمر يعمل في المجموعات فقط!")
        return
    
    chat_id = str(update.effective_chat.id)
    text = update.message.text
    
    if not await is_user_admin(update, context):
        return
    
    usernames = re.findall(r'@(\w+)', text)
    
    if not usernames:
        await update.message.reply_text("❌ الاستخدام: /remove @username")
        return
    
    if chat_id not in group_members:
        await update.message.reply_text("📭 لا يوجد أعضاء محفوظين!")
        return
    
    removed = []
    not_found = []
    
    for username in usernames:
        found = False
        for uid in list(group_members[chat_id].keys()):
            data = group_members[chat_id][uid]
            stored_username = data.get("username") or ""
            if stored_username.lower() == username.lower():
                del group_members[chat_id][uid]
                removed.append(f"@{username}")
                found = True
                break
        if not found:
            not_found.append(f"@{username}")
    
    save_data(group_members)
    
    response = ""
    if removed:
        response += f"✅ تم حذف: {', '.join(removed)}\n"
    if not_found:
        response += f"❌ غير موجودين: {', '.join(not_found)}\n"
    
    await update.message.reply_text(response)


async def clear_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مسح كل الأعضاء من المجموعة"""
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("⚠️ هذا الأمر يعمل في المجموعات فقط!")
        return
    
    chat_id = str(update.effective_chat.id)
    
    if not await is_user_admin(update, context):
        return
    
    if chat_id in group_members:
        count = len(group_members[chat_id])
        group_members[chat_id] = {}
        save_data(group_members)
        await update.message.reply_text(f"🗑️ تم مسح {count} عضو من القائمة!")
    else:
        await update.message.reply_text("📭 القائمة فارغة أصلاً!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل والتحقق من @all"""
    if not update.message:
        return
    
    # تتبع المستخدم أولاً - تم نقله لمعالج منفصل (group -1) لضمان الدقة
    pass
    
    # التحقق من وجود @all (فقط في الرسائل النصية)
    if update.message.text:
        text = update.message.text
        # استخدام Regex للتأكد من أنها كلمة منفصلة وليست جزء من ايميل مثلاً
        # (?:^|\s) تعني بداية السطر أو مسافة
        # @(all|everyone) تعني @all أو @everyone
        # \b تعني نهاية الكلمة
        if re.search(r'(?:^|\s)@(all|everyone)\b', text, re.IGNORECASE):
            logger.info(f"Trigger received in chat {update.effective_chat.id} from {update.effective_user.id}")
            await mention_all(update, context)


async def mention_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منشن لجميع الأعضاء - 5 في كل رسالة"""
    # التحقق من الصلاحيات
    if not await is_user_admin(update, context):
        return

    chat_id = str(update.effective_chat.id)
    sender_id = str(update.effective_user.id)
    sender_username = update.effective_user.username
    
    if chat_id not in group_members or len(group_members[chat_id]) == 0:
        await update.message.reply_text(
            "📭 لا يوجد أعضاء محفوظين!\n\n"
            "💡 أضف أعضاء باستخدام:\n"
            "/add @user1 @user2 @user3"
        )
        return
    
    # استثناء المرسل من القائمة
    members = []
    for uid, data in group_members[chat_id].items():
        # استثناء المرسل
        if uid == sender_id:
            continue
        member_username = data.get("username") or ""
        if sender_username and member_username.lower() == sender_username.lower():
            continue
        members.append((uid, data))
    
    logger.info(f"Found {len(members)} members to mention in chat {chat_id}")
    
    if len(members) == 0:
        await update.message.reply_text("📭 لا يوجد أعضاء آخرين لعمل منشن لهم!")
        return
    
    total_members = len(members)
    batch_size = 5
    
    # تقسيم الأعضاء إلى مجموعات من 5 وتجهيز المهام
    tasks = []
    total_batches = (total_members + batch_size - 1) // batch_size
    
    # استخدام الرسالة المخصصة أو الافتراضية مرة واحدة
    custom_msg = "📣"
    if chat_id in group_settings and "mention_message" in group_settings[chat_id]:
        custom_msg = group_settings[chat_id]["mention_message"]
        
    # تحديد الرسالة التي سيتم الرد عليها
    reply_to_id = update.message.message_id
    if update.message.reply_to_message:
        reply_to_id = update.message.reply_to_message.message_id

    for i in range(0, total_members, batch_size):
        batch = members[i:i + batch_size]
        mentions = []
        
        for user_id, data in batch:
            if data.get("username"):
                mentions.append(f"@{data['username']}")
            else:
                name = html.escape(data['first_name'])
                mentions.append(f'<a href="tg://user?id={user_id}">{name}</a>')
        
        batch_num = (i // batch_size) + 1
        message = f"{custom_msg} ({batch_num}/{total_batches}): " + " ".join(mentions)
        
        # إضافة مهمة الإرسال للقائمة
        tasks.append(context.bot.send_message(
            chat_id=chat_id,
            text=message,
            reply_to_message_id=reply_to_id,
            parse_mode=ParseMode.HTML
        ))
    
    # إرسال الجميع بالتوازي لأقصى سرعة
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    
    # رسائل انتهاء عشوائية
    completion_messages = [
        "ارحبوا 🫡",
        "تم بنجاح! 🚀",
        "تم المنشن للجميع ✅",
        "أبشروا بالخير ✨",
        "أهلاً وسهلاً بالجميع 👋",
        "تم الإرسال.. الله يحييكم! 🌟"
    ]
    import random
    await update.message.reply_text(random.choice(completion_messages))


async def list_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة الأعضاء المحفوظين"""
    chat_id = str(update.effective_chat.id)
    
    if chat_id not in group_members or len(group_members[chat_id]) == 0:
        await update.message.reply_text("📭 لا يوجد أعضاء محفوظين حالياً!")
        return
    
    members_list = []
    for user_id, data in group_members[chat_id].items():
        if data.get("username"):
            members_list.append(f"• @{data['username']}")
        else:
            members_list.append(f"• {data.get('full_name', 'User')}")
    
    if len(members_list) > 50:
        await update.message.reply_text(
            f"📋 الأعضاء المحفوظين: {len(members_list)} عضو\n"
            "⚠️ القائمة طويلة جداً للعرض"
        )
    else:
        await update.message.reply_text(
            f"📋 الأعضاء المحفوظين ({len(members_list)}):\n\n" + 
            "\n".join(members_list)
        )


async def count_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض عدد الأعضاء المحفوظين"""
    chat_id = str(update.effective_chat.id)
    
    if chat_id not in group_members:
        count = 0
    else:
        count = len(group_members[chat_id])
    
    await update.message.reply_text(f"👥 عدد الأعضاء المحفوظين: {count}")

async def bot_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """التحقق من حالة البوت والاتصال"""
    if not await is_user_admin(update, context):
        return
        
    db_status = "✅ متصل" if members_collection is not None else "❌ غير متصل (يعمل محلياً فقط)"
    groups_count = len(group_members)
    
    status_text = (
        f"⚙️ **حالة البوت:**\n\n"
        f"🗄 قاعدة البيانات: {db_status}\n"
        f"📊 عدد المجموعات النشطة: {groups_count}\n"
        f"🔑 التوكن: `{BOT_TOKEN[:10]}...`\n"
        f"🌐 البيئة: Vercel Serverless"
    )
    await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)


def create_app(chat_id=None):
    """إنشاء وتجهيز تطبيق البوت"""
    if not BOT_TOKEN:
        print("❌ خطأ: لم يتم العثور على BOT_TOKEN!")
        return None
    
    # إنشاء التطبيق
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Initialize data for specific chat to save time
    init_data(chat_id)
    
    # إضافة الأوامر
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("add", add_members))
    application.add_handler(CommandHandler("add_id", add_member_id))
    application.add_handler(CommandHandler("id", get_id))
    application.add_handler(CommandHandler("set_msg", set_message))
    application.add_handler(CommandHandler("remove", remove_member))
    application.add_handler(CommandHandler("clear", clear_members))
    application.add_handler(CommandHandler("list", list_members))
    application.add_handler(CommandHandler("count", count_members))
    application.add_handler(CommandHandler("status", bot_status))
    
    # معالج الرسائل وتلقي كل التفاعلات (حتى الأوامر) لتسجيل الأعضاء
    application.add_handler(MessageHandler(filters.ALL, track_user), group=-1)
    
    # معالج الرسائل (للمنشن)
    application.add_handler(MessageHandler(~filters.COMMAND, handle_message))
    
    return application


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

    # بدء تشغيل البوت
    print("🚀 جاري تشغيل البوت...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
