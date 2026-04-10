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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
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

BOT_VERSION = "1.0.3-NUCLEAR-FIX (2026-02-21 11:10)"

# تحميل المتغيرات البيئية
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# تكوين MongoDB
db = None
members_collection = None
settings_collection = None
tags_collection = None
history_collection = None  # سجل استخدام @all

# كاش لعدد الرسائل (لتقليل عمليات الحفظ على MongoDB)
message_count_cache = {}  # {chat_id: {user_id: count}}
MESSAGE_SAVE_THRESHOLD = 5


def disable_db(exc=None):
    global db, members_collection, settings_collection, tags_collection, history_collection
    if exc:
        logger.error(f"Disabling MongoDB and falling back to local storage: {exc}")
    db = None
    members_collection = None
    settings_collection = None
    tags_collection = None
    history_collection = None

def init_db():
    global db, members_collection, settings_collection, tags_collection, history_collection
    if db is not None:
        return
    if MONGO_URI:
        try:
            from pymongo import MongoClient
            # استخدام certifi لحل مشاكل SSL
            client = MongoClient(MONGO_URI, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
            client.admin.command("ping")
            db = client.get_database("telegram_bot_db")
            members_collection = db.members
            settings_collection = db.settings
            tags_collection = db.tags
            history_collection = db.history
            print("✅ تم الاتصال بقاعدة بيانات MongoDB بنجاح!")
        except Exception as e:
            msg = f"❌ فشل الاتصال بقاعدة البيانات: {e}"
            print(msg)
            # محاولة إرسال تنبيه للمالك إذا أمكن
            try:
                import requests
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                              json={"chat_id": 1616533142, "text": msg})
            except:
                pass

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
        try:
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
        except Exception as e:
            disable_db(e)
    
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
        try:
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
        except Exception as e:
            disable_db(e)

    # الحفظ في ملف محلي
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_settings(chat_id=None):
    """تحميل الإعدادات (MongoDB أو ملف)"""
    if settings_collection is not None:
        try:
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
        except Exception as e:
            disable_db(e)

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
        try:
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
        except Exception as e:
            disable_db(e)

    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_tags(chat_id=None):
    """تحميل المنشن المخصص"""
    if tags_collection is not None:
        try:
            if chat_id:
                doc = tags_collection.find_one({"_id": str(chat_id)})
                if doc:
                    group_tags[str(chat_id)] = doc["tags"]
                    return {str(chat_id): doc["tags"]}
                return {}
            for doc in tags_collection.find():
                group_tags[doc["_id"]] = doc["tags"]
        except Exception as e:
            disable_db(e)
    else:
        if os.path.exists(TAGS_FILE):
            with open(TAGS_FILE, "r", encoding='utf-8') as f:
                return json.load(f)
    return {}


def save_tags(data, chat_id):
    if tags_collection is not None:
        try:
            tags_collection.replace_one({"_id": str(chat_id)}, {"tags": data}, upsert=True)
            return
        except Exception as e:
            disable_db(e)
    with open(TAGS_FILE, "w", encoding='utf-8') as f:
        json.dump(group_tags, f, ensure_ascii=False, indent=4)


def init_tags(chat_id):
    chat_id = str(chat_id)
    if chat_id not in group_tags:
        group_tags[chat_id] = {}
        loaded_tags = load_tags(chat_id)
        if loaded_tags and chat_id in loaded_tags:
            group_tags[chat_id] = loaded_tags[chat_id]


# (these are initialized above at lines 92-94 — no need to re-declare)

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
    """التحقق مما إذا كان المستخدم مشرفاً (تيليجرام أو مخصص)"""
    if not update.effective_chat or update.effective_chat.type == "private":
        return True
        
    user_id = update.effective_user.id
    chat_id = str(update.effective_chat.id)
    
    # التحقق من المشرفين المخصصين أولاً
    init_data(chat_id)
    custom_admins = group_settings.get(chat_id, {}).get("custom_admins", [])
    if str(user_id) in custom_admins:
        return True
    
    try:
        member = await context.bot.get_chat_member(int(chat_id), user_id)
        return member.status in ["creator", "administrator"]
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البداية"""
    # Debug message
    try:
        await context.bot.send_message(chat_id=1616533142, text=f"🔍 Start handler triggered for chat: {update.effective_chat.id}")
    except:
        pass

    await update.message.reply_text(
        "🤖 مرحباً! أنا بوت المنشن\n\n"
        "📋 كيفية الاستخدام:\n"
        "• أضفني للمجموعة وامنحني صلاحيات أدمن\n"
        "• أرسل @all لمنشن جميع الأعضاء\n"
        "• أرسل @all quiet للمنشن بدون رسالة إكمال\n\n"
        "📌 الأوامر (للمشرفين فقط 👮‍♂️):\n"
        "/add @user - إضافة (أو رُد على رسالة)\n"
        "/add_id ID اسم - إضافة بالآيدي\n"
        "/ping @user رسالة - منشن شخص واحد\n"
        "/mention_id ID اسم - منشن بالآيدي\n"
        "/boost @user 5 - زيادة مرّات المنشن\n"
        "/unboost @user - إعادة الوضع الطبيعي\n"
        "/id - معرفة الآيدي (بالرد)\n"
        "/list - عرض الأعضاء (أو /list محمد للبحث)\n"
        "/count - عدد الأعضاء\n"
        "/history - آخر استخدامات @all\n"
        "/backup - نسخة احتياطية\n"
        "/remove @user - حذف عضو\n"
        "/block_mention @user - منع @all لشخص\n"
        "/unblock_mention @user - رفع الحظر\n"
        "/setmsg رسالة - تغيير رسالة المنشن\n"
        "/exclude @user - استثناء عضو\n"
        "/unexclude @user - إلغاء الاستثناء\n"
        "/add_tag #tag - إنشاء تاج مخصص\n"
        "/del_tag #tag | /add_to_tag | /rem_from_tag | /tags\n"
        "/sync_from <ID> - نسخ من مجموعة أخرى\n"
        "/clean - تنظيف | /clear - مسح الكل\n"
        "/schedule HH:MM - جدولة تلقائية\n"
        "/setadmin @user - تعيين مشرف للبوت\n"
        "/status - حالة البوت\n\n"
        "⚡ يتم حفظ الأعضاء بشكل دائم!"
    )


# ... (deleted redundant track_user)


async def add_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة أعضاء يدوياً بالـ username أو بالرد على رسالة"""
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("⚠️ هذا الأمر يعمل في المجموعات فقط!")
        return

    if not await is_user_admin(update, context):
        return

    chat_id = str(update.effective_chat.id)
    init_data(chat_id)

    # استخدام effective_message لضمان الحصول على بيانات الرد
    msg = update.effective_message
    
    # دعم الرد على رسالة مباشرة
    if msg.reply_to_message:
        replied_msg = msg.reply_to_message
        target_user = replied_msg.from_user
        target_chat = replied_msg.sender_chat # للأدمينات المخفيين أو القنوات
        # ... logic remains same ...
        if target_user:
            if target_user.is_bot:
                await msg.reply_text("❌ لا يمكن إضافة بوت.")
                return
            uid = str(target_user.id)
            username = target_user.username
            first_name = target_user.first_name or "User"
            full_name = target_user.full_name or "User"
            name_display = f"@{username}" if username else full_name
        elif target_chat:
            uid = f"chat_{target_chat.id}"
            username = target_chat.username
            first_name = target_chat.title or "Anonymous Admin"
            full_name = target_chat.title or "Anonymous Admin"
            name_display = f"@{username}" if username else first_name
        else:
            await msg.reply_text("❌ لم يمكن تحديد صاحب الرسالة.")
            return

        group_members[chat_id][uid] = {
            "username": username,
            "first_name": first_name,
            "full_name": full_name,
            "multiplier": group_members[chat_id].get(uid, {}).get("multiplier", 1)
        }
        save_data(group_members, chat_id)
        await msg.reply_text(
            f"✅ تم إضافة {name_display}!\n👥 الإجمالي: {len(group_members[chat_id])}"
        )
        return

    args = context.args
    if not args:
        # إضافة رمز صغير (R-) للتشخيص إذا لم يجد الرد
        await msg.reply_text("❌ الاستخدام:\n/add @user1 @user2\nأو رُد على رسالة شخص بـ /add (R-)")
        return

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
    """مسح كل الأعضاء مع تأكيد inline"""
    if not await is_user_admin(update, context): return
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    count = len(group_members.get(chat_id, {}))
    if count == 0:
        await update.message.reply_text("📭 القائمة فارغة أصلاً!")
        return
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ نعم، امسح الكل", callback_data=f"clear_confirm_{chat_id}"),
        InlineKeyboardButton("❌ إلغاء", callback_data="clear_cancel")
    ]])
    await update.message.reply_text(
        f"⚠️ هل أنت متأكد من مسح **{count}** عضو؟\nلا يمكن التراجع!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


async def clear_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة تأكيد /clear"""
    query = update.callback_query
    await query.answer()
    if query.data == "clear_cancel":
        await query.edit_message_text("✔️ تم إلغاء العملية.")
        return
    if query.data.startswith("clear_confirm_"):
        chat_id = query.data.replace("clear_confirm_", "")
        count = len(group_members.get(chat_id, {}))
        group_members[chat_id] = {}
        save_data(group_members, chat_id)
        await query.edit_message_text(f"🗑️ تم مسح {count} عضو بنجاح.")


async def get_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معرفة الآيدي الرقمي عن طريق الرد على رسالة"""
    msg = update.effective_message
    if msg.reply_to_message:
        replied_msg = msg.reply_to_message
        target_user = replied_msg.from_user
        target_chat = replied_msg.sender_chat
        
        if target_user:
            lines = [
                f"🆔 **معلومات المستخدم:**",
                f"• الاسم: {target_user.full_name}",
                f"• الآيدي: `{target_user.id}`",
            ]
            if target_user.username:
                lines.append(f"• اليوزر: @{target_user.username}")
        elif target_chat:
            lines = [
                f"🆔 **معلومات الشات/الأدمن:**",
                f"• الاسم: {target_chat.title}",
                f"• الآيدي: `{target_chat.id}`",
            ]
            if target_chat.username:
                lines.append(f"• اليوزر: @{target_chat.username}")
        else:
            await msg.reply_text("❌ لم يمكن تحديد صاحب الرسالة. (تأكد من صلاحيات البوت)")
            return
            
        await msg.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    else:
        # عرض معلومات من أرسل الأمر
        user = update.effective_user
        lines = [
            f"🆔 **معلوماتك:**",
            f"• الاسم: {user.full_name}",
            f"• الآيدي: `{user.id}`",
        ]
        if user.username:
            lines.append(f"• اليوزر: @{user.username}")
        lines.append(f"\n💡 للحصول على آيدي شخص آخر، رُد على رسالته بـ /id")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


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


async def set_mention_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين رسالة مخصصة للمنشن"""
    if not await is_user_admin(update, context):
        return
    
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    
    if not context.args:
        current_msg = group_settings.get(chat_id, {}).get("mention_message", "📣")
        await update.message.reply_text(
            f"📝 الرسالة الحالية: {current_msg}\n\n"
            f"للتغيير استخدم:\n`/setmsg رسالتك الجديدة`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    new_msg = " ".join(context.args)
    if chat_id not in group_settings:
        group_settings[chat_id] = {}
    group_settings[chat_id]["mention_message"] = new_msg
    save_settings(group_settings, chat_id)
    await update.message.reply_text(f"✅ تم تعيين رسالة المنشن إلى:\n{new_msg}")


async def exclude_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استثناء عضو من المنشنات"""
    if not await is_user_admin(update, context):
        return
    
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    
    if not context.args:
        # عرض المستثنين الحاليين
        excluded = group_settings.get(chat_id, {}).get("excluded", [])
        if not excluded:
            await update.message.reply_text("📭 لا يوجد أعضاء مستثنين حالياً.")
        else:
            names = []
            for uid in excluded:
                if uid in group_members.get(chat_id, {}):
                    data = group_members[chat_id][uid]
                    names.append(f"• {data.get('first_name', uid)}")
            await update.message.reply_text(f"🚫 الأعضاء المستثنين:\n" + "\n".join(names))
        return
    
    username = context.args[0].replace("@", "").lower()
    
    # البحث عن العضو
    found_uid = None
    for uid, data in group_members.get(chat_id, {}).items():
        if (data.get("username") or "").lower() == username:
            found_uid = uid
            break
    
    if not found_uid:
        await update.message.reply_text(f"❌ المستخدم @{username} غير موجود في القائمة.")
        return
    
    if chat_id not in group_settings:
        group_settings[chat_id] = {}
    if "excluded" not in group_settings[chat_id]:
        group_settings[chat_id]["excluded"] = []
    
    if found_uid not in group_settings[chat_id]["excluded"]:
        group_settings[chat_id]["excluded"].append(found_uid)
        save_settings(group_settings, chat_id)
        await update.message.reply_text(f"✅ تم استثناء @{username} من المنشنات.")
    else:
        await update.message.reply_text(f"⚠️ @{username} مستثنى بالفعل.")


async def unexclude_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء استثناء عضو"""
    if not await is_user_admin(update, context):
        return
    
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    
    if not context.args:
        await update.message.reply_text("استخدم: `/unexclude @username`", parse_mode=ParseMode.MARKDOWN)
        return
    
    username = context.args[0].replace("@", "").lower()
    
    # البحث عن العضو
    found_uid = None
    for uid, data in group_members.get(chat_id, {}).items():
        if (data.get("username") or "").lower() == username:
            found_uid = uid
            break
    
    if not found_uid:
        await update.message.reply_text(f"❌ المستخدم @{username} غير موجود.")
        return
    
    excluded = group_settings.get(chat_id, {}).get("excluded", [])
    if found_uid in excluded:
        excluded.remove(found_uid)
        group_settings[chat_id]["excluded"] = excluded
        save_settings(group_settings, chat_id)
        await update.message.reply_text(f"✅ تم إلغاء استثناء @{username}. سيتم منشنه الآن.")
    else:
        await update.message.reply_text(f"⚠️ @{username} ليس مستثنى أصلاً.")


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات المجموعة"""
    chat_id = str(update.effective_chat.id)
    
    # إعادة تحميل البيانات من قاعدة البيانات لضمان الدقة
    if chat_id in group_members:
        del group_members[chat_id]
    init_data(chat_id)
    
    members = group_members.get(chat_id, {})
    settings = group_settings.get(chat_id, {})
    tags = group_tags.get(chat_id, {})
    
    total_members = len(members)
    excluded_count = len(settings.get("excluded", []))
    boosted_count = sum(1 for m in members.values() if m.get("multiplier", 1) > 1)
    tags_count = len(tags)
    
    # أكثر الأعضاء تفاعلاً
    sorted_members = sorted(
        [(uid, data) for uid, data in members.items() if data.get("message_count", 0) > 0],
        key=lambda x: x[1].get("message_count", 0),
        reverse=True
    )[:5]
    
    top_active = ""
    if sorted_members:
        top_active = "\n\n🔥 **أكثر الأعضاء تفاعلاً:**\n"
        for i, (uid, data) in enumerate(sorted_members, 1):
            name = data.get("first_name", "Unknown")
            count = data.get("message_count", 0)
            top_active += f"{i}. {name}: {count} رسالة\n"
    
    await update.message.reply_text(
        f"📊 **إحصائيات المجموعة**\n\n"
        f"👥 إجمالي الأعضاء: {total_members}\n"
        f"🚫 المستثنين: {excluded_count}\n"
        f"⚡ المعززين (Boost): {boosted_count}\n"
        f"🏷 التاجات: {tags_count}\n"
        f"📝 رسالة المنشن: {settings.get('mention_message', '📣')}"
        f"{top_active}",
        parse_mode=ParseMode.MARKDOWN
    )


async def export_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصدير قائمة الأعضاء"""
    if not await is_user_admin(update, context):
        return
    
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    
    members = group_members.get(chat_id, {})
    if not members:
        await update.message.reply_text("📭 القائمة فارغة!")
        return
    
    lines = []
    for uid, data in members.items():
        username = f"@{data['username']}" if data.get('username') else f"ID:{uid}"
        name = data.get('first_name', 'Unknown')
        boost = f" (x{data['multiplier']})" if data.get('multiplier', 1) > 1 else ""
        lines.append(f"{username} - {name}{boost}")
    
    export_text = f"📋 قائمة أعضاء المجموعة ({len(members)} عضو)\n\n" + "\n".join(lines)
    
    # إرسال كملف نصي إذا كان طويلاً
    if len(export_text) > 4000:
        from io import BytesIO
        file = BytesIO(export_text.encode('utf-8'))
        file.name = f"members_{chat_id}.txt"
        await update.message.reply_document(file, caption="📋 قائمة الأعضاء")
    else:
        await update.message.reply_text(export_text)


async def is_telegram_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """التحقق من أن المستخدم مشرف تيليجرام فعلي (وليس مخصص)"""
    if not update.effective_chat or update.effective_chat.type == "private":
        return True
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ["creator", "administrator"]
    except Exception:
        return False


async def set_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة مشرف مخصص للبوت"""
    # فقط مشرفي تيليجرام الفعليين يمكنهم إضافة مشرفين مخصصين
    if not await is_telegram_admin(update, context):
        await update.message.reply_text("❌ هذا الأمر متاح فقط لمشرفي المجموعة الفعليين.")
        return
    
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    
    if not context.args:
        await update.message.reply_text(
            "👤 **إضافة مشرف للبوت**\n\n"
            "استخدم: `/setadmin @username`\n\n"
            "المشرف المخصص يستطيع استخدام جميع أوامر البوت حتى لو لم يكن مشرف في تيليجرام.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    username = context.args[0].replace("@", "").lower()
    
    # البحث عن المستخدم
    found_uid = None
    for uid, data in group_members.get(chat_id, {}).items():
        if (data.get("username") or "").lower() == username:
            found_uid = uid
            break
    
    if not found_uid:
        await update.message.reply_text(f"❌ المستخدم @{username} غير موجود في قائمة الأعضاء.")
        return
    
    if chat_id not in group_settings:
        group_settings[chat_id] = {}
    if "custom_admins" not in group_settings[chat_id]:
        group_settings[chat_id]["custom_admins"] = []
    
    if found_uid not in group_settings[chat_id]["custom_admins"]:
        group_settings[chat_id]["custom_admins"].append(found_uid)
        save_settings(group_settings, chat_id)
        await update.message.reply_text(f"✅ تم تعيين @{username} كمشرف للبوت!")
    else:
        await update.message.reply_text(f"⚠️ @{username} مشرف مخصص بالفعل.")


async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إزالة مشرف مخصص"""
    if not await is_telegram_admin(update, context):
        await update.message.reply_text("❌ هذا الأمر متاح فقط لمشرفي المجموعة الفعليين.")
        return
    
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    
    if not context.args:
        await update.message.reply_text("استخدم: `/removeadmin @username`", parse_mode=ParseMode.MARKDOWN)
        return
    
    username = context.args[0].replace("@", "").lower()
    
    # البحث عن المستخدم
    found_uid = None
    for uid, data in group_members.get(chat_id, {}).items():
        if (data.get("username") or "").lower() == username:
            found_uid = uid
            break
    
    if not found_uid:
        await update.message.reply_text(f"❌ المستخدم @{username} غير موجود.")
        return
    
    custom_admins = group_settings.get(chat_id, {}).get("custom_admins", [])
    if found_uid in custom_admins:
        custom_admins.remove(found_uid)
        group_settings[chat_id]["custom_admins"] = custom_admins
        save_settings(group_settings, chat_id)
        await update.message.reply_text(f"✅ تم إزالة @{username} من المشرفين المخصصين.")
    else:
        await update.message.reply_text(f"⚠️ @{username} ليس مشرف مخصص.")


async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة المشرفين المخصصين"""
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    
    custom_admins = group_settings.get(chat_id, {}).get("custom_admins", [])
    
    if not custom_admins:
        await update.message.reply_text("📭 لا يوجد مشرفين مخصصين حالياً.")
        return
    
    names = []
    for uid in custom_admins:
        if uid in group_members.get(chat_id, {}):
            data = group_members[chat_id][uid]
            username = f"@{data['username']}" if data.get('username') else data.get('first_name', uid)
            names.append(f"• {username}")
    
    await update.message.reply_text(f"👤 **المشرفون المخصصون:**\n" + "\n".join(names), parse_mode=ParseMode.MARKDOWN)


async def import_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استيراد قائمة الأعضاء من ملف أو نص"""
    if not await is_user_admin(update, context):
        return
    
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    
    # التحقق من وجود ملف مرفق
    if update.message.reply_to_message and update.message.reply_to_message.document:
        doc = update.message.reply_to_message.document
        file = await context.bot.get_file(doc.file_id)
        file_bytes = await file.download_as_bytearray()
        content = file_bytes.decode('utf-8')
    elif context.args:
        content = " ".join(context.args)
    else:
        await update.message.reply_text(
            "📥 **كيفية الاستيراد:**\n\n"
            "1️⃣ أرسل ملف نصي ثم رد عليه بـ `/import`\n"
            "2️⃣ أو اكتب: `/import @user1 @user2 @user3`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # استخراج اليوزرنيمات
    import re
    usernames = re.findall(r'@(\w+)', content)
    
    if not usernames:
        await update.message.reply_text("❌ لم أجد أي يوزرنيمات في النص المرسل.")
        return
    
    added = 0
    for username in usernames:
        temp_id = f"username_{username.lower()}"
        if temp_id not in group_members[chat_id]:
            group_members[chat_id][temp_id] = {
                "username": username,
                "first_name": username,
                "full_name": username,
                "multiplier": 1
            }
            added += 1
    
    if added > 0:
        save_data(group_members, chat_id)
        await update.message.reply_text(f"✅ تم استيراد {added} عضو جديد!")
    else:
        await update.message.reply_text("⚠️ كل الأعضاء المذكورين موجودين مسبقاً.")


async def schedule_mention(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """جدولة منشن يومي في وقت محدد"""
    if not await is_user_admin(update, context):
        return
    
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    if context.job_queue is None:
        await update.message.reply_text(
            "❌ الجدولة غير مدعومة في وضع Webhook الحالي. شغّل البوت بنظام Polling أو فعّل JobQueue أولاً."
        )
        return
    
    if not context.args:
        current_schedule = group_settings.get(chat_id, {}).get("schedule_time")
        if current_schedule:
            await update.message.reply_text(
                f"⏰ الجدولة الحالية: **{current_schedule}**\n\n"
                f"لإلغاء: `/schedule off`\n"
                f"لتغيير: `/schedule 18:00`",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                "⏰ **جدولة المنشن التلقائي**\n\n"
                "استخدم: `/schedule HH:MM`\n"
                "مثال: `/schedule 18:00`\n\n"
                "سيتم عمل @all يومياً في هذا الوقت.",
                parse_mode=ParseMode.MARKDOWN
            )
        return
    
    time_arg = context.args[0].lower()
    
    # إلغاء الجدولة
    if time_arg in ["off", "cancel", "stop", "الغاء"]:
        if chat_id in group_settings and "schedule_time" in group_settings[chat_id]:
            del group_settings[chat_id]["schedule_time"]
            save_settings(group_settings, chat_id)
            
            # إلغاء الـ Job إذا كان موجوداً
            job_name = f"schedule_{chat_id}"
            current_jobs = context.job_queue.get_jobs_by_name(job_name)
            for job in current_jobs:
                job.schedule_removal()
            
            await update.message.reply_text("✅ تم إلغاء الجدولة.")
        else:
            await update.message.reply_text("⚠️ لا توجد جدولة نشطة.")
        return
    
    # تحليل الوقت
    import re
    match = re.match(r'^(\d{1,2}):(\d{2})$', time_arg)
    if not match:
        await update.message.reply_text("❌ صيغة الوقت غير صحيحة. استخدم: `HH:MM`", parse_mode=ParseMode.MARKDOWN)
        return
    
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        await update.message.reply_text("❌ الوقت غير صحيح.")
        return
    
    # حفظ الإعدادات
    if chat_id not in group_settings:
        group_settings[chat_id] = {}
    group_settings[chat_id]["schedule_time"] = time_arg
    save_settings(group_settings, chat_id)
    
    # إعداد الـ Job
    from datetime import time as dt_time
    import pytz
    
    # إلغاء الـ Job القديم إذا كان موجوداً
    job_name = f"schedule_{chat_id}"
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()
    
    # إنشاء Job جديد (توقيت الأردن/السعودية UTC+3)
    try:
        tz = pytz.timezone('Asia/Riyadh')
        context.job_queue.run_daily(
            scheduled_mention_callback,
            time=dt_time(hour=hour, minute=minute, tzinfo=tz),
            chat_id=int(chat_id),
            name=job_name,
            data={"chat_id": chat_id}
        )
        await update.message.reply_text(f"✅ تم جدولة المنشن يومياً الساعة **{time_arg}** (توقيت الرياض)")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ في الجدولة: {e}")


async def scheduled_mention_callback(context):
    """تنفيذ المنشن المجدول"""
    chat_id = context.job.data["chat_id"]
    init_data(chat_id)
    
    if chat_id not in group_members or not group_members[chat_id]:
        return
    
    # بناء قائمة الأعضاء
    members = group_members.get(chat_id, {})
    excluded = group_settings.get(chat_id, {}).get("excluded", [])
    custom_msg = group_settings.get(chat_id, {}).get("mention_message", "📣")
    
    valid_members = []
    for uid, data in members.items():
        if uid in excluded:
            continue
        valid_members.append((uid, data))
    
    if not valid_members:
        return
    
    batch_size = 5
    total = len(valid_members)
    
    for i in range(0, total, batch_size):
        batch = valid_members[i:i + batch_size]
        mentions = []
        
        for uid, data in batch:
            if data.get("username"):
                mentions.append(f"@{data['username']}")
            else:
                name = html.escape(data.get('first_name', 'User'))
                mentions.append(f'<a href="tg://user?id={uid}">{name}</a>')
        
        batch_num = (i // batch_size) + 1
        total_batches = (total + batch_size - 1) // batch_size
        message = f"⏰ {custom_msg} [{batch_num}/{total_batches}]\n" + " ".join(mentions)
        
        try:
            await context.bot.send_message(
                chat_id=int(chat_id),
                text=message,
                parse_mode=ParseMode.HTML
            )
            await asyncio.sleep(2.0)
        except Exception as e:
            logger.error(f"Scheduled mention error: {e}")


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
    
    # تتبع عدد الرسائل - حفظ كل MESSAGE_SAVE_THRESHOLD رسالة (يقلل ضغط MongoDB 80%)
    if user_id in group_members[chat_id]:
        current_count = group_members[chat_id][user_id].get("message_count", 0) + 1
        group_members[chat_id][user_id]["message_count"] = current_count
        if chat_id not in message_count_cache:
            message_count_cache[chat_id] = {}
        cache_val = message_count_cache[chat_id].get(user_id, 0) + 1
        message_count_cache[chat_id][user_id] = cache_val
        if cache_val >= MESSAGE_SAVE_THRESHOLD:
            message_count_cache[chat_id][user_id] = 0
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
        quiet = bool(__import__("re").search(r"\bquiet\b", text, __import__("re").IGNORECASE))
        await mention_all(update, context, rounds, quiet=quiet)
        return

    # 2. التحقق من التاجات المخصصة (#tagname)
    chat_id = str(update.effective_chat.id)
    init_tags(chat_id)
    for tag in group_tags.get(chat_id, {}):
        if tag in text.lower():
            await mention_tag(update, context, tag)
            return


async def mention_all(update: Update, context: ContextTypes.DEFAULT_TYPE, total_rounds=1, quiet=False):
    """منشن الجميع مع دعم لعدة جولات والـ Boost"""
    if not await is_user_admin(update, context):
        await update.message.reply_text("⚠️ المعذرة، هذا الأمر متاح للمشرفين فقط.")
        return

    # منع التنفيذ المزدوج لنفس الرسالة
    msg_id = update.message.message_id
    chat_id = str(update.effective_chat.id)
    lock_key = f"{chat_id}_{msg_id}"
    
    # التأكد من وجود القفل بشكل صحيح
    if 'mention_locks' not in context.bot_data:
        context.bot_data['mention_locks'] = set()
    
    if lock_key in context.bot_data['mention_locks']:
        logger.warning(f"⚠️ تم تخطي منشن مكرر للرسالة {msg_id}")
        return
    
    context.bot_data['mention_locks'].add(lock_key)
    
    # تنظيف الأقفال القديمة (الاحتفاظ بآخر 100 قفل فقط)
    if len(context.bot_data['mention_locks']) > 100:
        context.bot_data['mention_locks'] = set(list(context.bot_data['mention_locks'])[-50:])

    # تحقق من blocked_mention
    user_id_str = str(update.effective_user.id)
    if user_id_str in group_settings.get(chat_id, {}).get("blocked_mention", []):
        await update.message.reply_text("❌ ليس لديك صلاحية استخدام @all.")
        return

    # حفظ سجل الاستخدام
    _save_history(chat_id, update.effective_user.id, update.effective_user.username or "")

    init_data(chat_id)
    
    if chat_id not in group_members or not group_members[chat_id]:
        await update.message.reply_text("📭 القائمة فارغة!")
        return

    # بناء القائمة مع مراعاة الـ Multiplier والتحقق من الوجود
    valid_members = []
    unique_uids = list(group_members[chat_id].keys())
    
    # تخطي فحص الوجود لزيادة السرعة في المجموعات الكبيرة على Vercel
    # يمكن للمدراء استخدام /clean لتنظيف القائمة يدوياً
    
    excluded_list = group_settings.get(chat_id, {}).get("excluded", [])
    for uid in unique_uids:
        # تخطي المستثنين
        if uid in excluded_list:
            continue
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

    # تحسين السرعة لـ Vercel (Timeouts)
    is_vercel = "VERCEL" in os.environ or "VERCEL_URL" in os.environ
    batch_size = 10 if is_vercel else 5  # زيادة الحجم في فيرسيل لتقليل الرسائل
    sleep_time = 0.5 if is_vercel else 2.0  # تقليل التأخير لتفادي الـ Timeout
    
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
                        name = html.escape(data.get('first_name') or data.get('full_name') or 'User')
                        mentions.append(f'<a href="tg://user?id={uid}">{name}</a>')
                
                batch_num = (i // batch_size) + 1
                progress = f"{round_prefix}[{batch_num}/{total_batches}]"
                message = f"{custom_msg} {progress}\n" + " ".join(mentions)
                
                # محاولة إرسال الدفعة - استمرار للمحاولة حتى النجاح
                batch_sent = False
                
                while not batch_sent:
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
                        err_msg = str(e).lower()
                        logger.error(f"❌ Error Batch {batch_num}: {e}")
                        
                        if "retry after" in err_msg or "flood" in err_msg:
                            import re
                            match = re.search(r'(\d+)', err_msg)
                            seconds = int(match.group(1)) if match else 15
                            wait_time = seconds + 2  # بافر أقل
                            logger.warning(f"⏳ Rate limited! Waiting {wait_time}s...")
                            await asyncio.sleep(wait_time)
                        else:
                            # خطأ آخر - انتظر وأعد المحاولة
                            await asyncio.sleep(3)
                
                # تأخير (حل وسط بين السرعة والثبات)
                await asyncio.sleep(sleep_time)
    except Exception as global_e:
        logger.error(f"🔴 CRITICAL ERROR in mention_all: {global_e}")
    finally:
        # إرسال رسالة الإكمال دائماً
        completion_msgs = [
            # رسائل ترحيب خليجية
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
            "حياكم الله، الجود من الموجود 👋❤️",
            # رسائل ترحيب عربية عامة
            "أهلاً وسهلاً بالجميع 🌺",
            "نورتوا المجموعة يا أحباب 💕",
            "تشرفنا بوجودكم معانا 🌹",
            "يا مرحبا بكل اللي هنا 🎉",
            "حللتم أهلاً ونزلتم سهلاً 🏡",
            "منورين والله يا جماعة ✨",
            "أسعدنا وجودكم معنا 💖",
            "الف هلا ومرحبا فيكم 🌸",
            "سعيدين بوجودكم 😊🌟",
            "حياكم الله يا أحلى ناس 💫",
            # رسائل مع إيموجي متنوعة
            "🔔 تم تنبيه الجميع! نورتوا",
            "📣 وصل الصوت للكل! حياكم",
            "🎯 تم المنشن بنجاح! نورتوا",
            "✅ اكتمل التنبيه! حياكم الله",
            "🚀 تم إشعار الجميع! منورين",
            # رسائل مرحة
            "صحيت العزبة كلها 😂🎉",
            "الكل استيقظ! نورتوا 😄",
            "ها قد اجتمعنا! حياكم 🤝",
            "الحضور كامل! يا هلا 👋",
            "الجميع حاضر! نورتونا 🌟",
            # رسائل قصيرة
            "حياكم! 🫡",
            "نورتوا! ✨",
            "منورين! 💫",
            "أهلين! 👋",
            "هلا بيكم! 💕",
            # رسائل طويلة جميلة
            "شرفتونا بوجودكم الكريم، نتمنى لكم يوماً سعيداً 🌹✨",
            "أسعد الله أوقاتكم بكل خير، حياكم الله 🌺💫",
            "بارك الله في وقتكم وجهدكم، نورتوا المجموعة 🙏✨",
            "تحية عطرة لكل الحاضرين، دمتم بخير 🌸💕",
            "نسأل الله أن يبارك في اجتماعنا هذا 🤲✨",
            # رسائل موسمية
            "صباح/مساء الخير للجميع 🌅",
            "أسعد الله صباحكم/مساءكم 🌙",
            "يوم سعيد للجميع 🌞",
            "تحياتي لكل الأعزاء 💐"
        ]
        import random
        if not quiet:
            try:
                await update.message.reply_text(random.choice(completion_msgs))
            except Exception as final_e:
                logger.error(f"Could not send completion message: {final_e}")


async def list_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة الأعضاء مع دعم البحث (/list محمد)"""
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)

    if chat_id not in group_members or not group_members[chat_id]:
        await update.message.reply_text("📭 القائمة فارغة!")
        return

    search_term = " ".join(context.args).lower().strip() if context.args else ""

    lines = []
    for uid, data in group_members[chat_id].items():
        boost = f" (x{data['multiplier']})" if data.get("multiplier", 1) > 1 else ""
        display = f"@{data['username']}" if data.get("username") else (data.get("full_name") or data.get("first_name") or "Unknown")
        if search_term and search_term not in display.lower():
            continue
        lines.append(f"• {display}{boost}")

    if not lines:
        await update.message.reply_text(f"🔍 لم يُعثر على '{search_term}' في القائمة.")
        return

    title = f"📌 نتائج '{search_term}'" if search_term else f"📋 الأعضاء المحفوظين ({len(lines)})"
    text = title + ":\n\n" + "\n".join(lines[:100])
    if len(lines) > 100:
        text += f"\n\n… و{len(lines)-100} آخرين."
    await update.message.reply_text(text)


async def count_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض عدد الأعضاء في القائمة"""
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    
    members = group_members.get(chat_id, {})
    excluded = group_settings.get(chat_id, {}).get("excluded", [])
    
    total = len(members)
    excluded_count = len(excluded)
    active = total - excluded_count
    
    await update.message.reply_text(
        f"👥 **عدد الأعضاء**\n\n"
        f"📊 الإجمالي: {total}\n"
        f"✅ النشطين: {active}\n"
        f"🚫 المستثنين: {excluded_count}",
        parse_mode=ParseMode.MARKDOWN
    )


async def ping_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منشن شخص واحد مع رسالة مخصصة"""
    if not await is_user_admin(update, context): return
    msg = update.effective_message
    custom_text = " ".join(context.args[1:]) if len(context.args) > 1 else ""
    mention = None
    if msg.reply_to_message:
        replied_msg = msg.reply_to_message
        target_user = replied_msg.from_user
        target_chat = replied_msg.sender_chat
        
        if target_user:
            mention = f"@{target_user.username}" if target_user.username else f'<a href="tg://user?id={target_user.id}">{html.escape(target_user.full_name or "User")}</a>'
        elif target_chat:
            mention = f"@{target_chat.username}" if target_chat.username else f'<a href="tg://user?id={target_chat.id}">{html.escape(target_chat.title or "Anonymous Admin")}</a>'
        else:
            await msg.reply_text("❌ لم يمكن تحديد صاحب الرسالة. (تأكد من صلاحيات البوت)")
            return
    elif context.args:
        mention = f"@{context.args[0].replace('@','').strip()}"
    else:
        await msg.reply_text("❌ الاستخدام: /ping @user رسالة\nأو رُد على رسالة شخص بـ /ping رسالة")
        return
    out_msg = f"📣 {mention}"
    if custom_text:
        out_msg += f"\n{custom_text}"
    await msg.reply_text(out_msg, parse_mode=ParseMode.HTML)


async def mention_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منشن شخص بالآيدي الرقمي"""
    if not await is_user_admin(update, context): return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("❌ الاستخدام: /mention_id 123456 الاسم")
        return
    uid = context.args[0]
    name = " ".join(context.args[1:]) or "User"
    mention = f'<a href="tg://user?id={uid}">{html.escape(name)}</a>'
    await update.message.reply_text(f"📣 {mention}", parse_mode=ParseMode.HTML)


def _save_history(chat_id: str, user_id: int, username: str):
    """حفظ سجل استخدام @all"""
    if history_collection is None:
        return
    from datetime import datetime, timezone
    try:
        history_collection.insert_one({
            "chat_id": str(chat_id),
            "user_id": str(user_id),
            "username": username,
            "timestamp": datetime.now(timezone.utc)
        })
        count = history_collection.count_documents({"chat_id": str(chat_id)})
        if count > 100:
            oldest = list(history_collection.find({"chat_id": str(chat_id)}).sort("timestamp", 1).limit(count - 100))
            history_collection.delete_many({"_id": {"$in": [d["_id"] for d in oldest]}})
    except Exception as e:
        logger.error(f"History error: {e}")


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض آخر 5 استخدامات @all"""
    if not await is_user_admin(update, context): return
    chat_id = str(update.effective_chat.id)
    if history_collection is None:
        await update.message.reply_text("⚠️ السجل يتطلب اتصال MongoDB.")
        return
    records = list(history_collection.find({"chat_id": chat_id}).sort("timestamp", -1).limit(5))
    if not records:
        await update.message.reply_text("📭 لا يوجد سجل لاستخدام @all بعد.")
        return
    lines = ["📜 **آخر استخدامات @all:**\n"]
    from datetime import timezone
    for i, r in enumerate(records, 1):
        ts = r["timestamp"]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        who = f"@{r['username']}" if r.get("username") else f"ID:{r.get('user_id','?')}"
        lines.append(f"{i}. {who} — {ts.strftime('%Y-%m-%d %H:%M')} UTC")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def backup_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصدير كل بيانات المجموعة كملف JSON"""
    if not await is_user_admin(update, context): return
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    from io import BytesIO
    import json as _json
    payload = {
        "members": group_members.get(chat_id, {}),
        "settings": group_settings.get(chat_id, {}),
        "tags": group_tags.get(chat_id, {})
    }
    file = BytesIO(_json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    file.name = f"backup_{chat_id}.json"
    await update.message.reply_document(file, caption=f"💾 نسخة احتياطية | {len(payload['members'])} عضو")


async def block_mention(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منع مستخدم من تشغيل @all"""
    if not await is_telegram_admin(update, context):
        await update.message.reply_text("❌ هذا الأمر للمشرفين الفعليين فقط.")
        return
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    if not context.args:
        blocked = group_settings.get(chat_id, {}).get("blocked_mention", [])
        if not blocked:
            await update.message.reply_text("📭 لا يوجد ممنوعون حالياً.")
        else:
            names = [f"• {group_members.get(chat_id,{}).get(uid,{}).get('first_name', uid)}" for uid in blocked]
            await update.message.reply_text("🚫 **الممنوعون من @all:**\n" + "\n".join(names), parse_mode=ParseMode.MARKDOWN)
        return
    username = context.args[0].replace("@", "").lower()
    found_uid = next((uid for uid, d in group_members.get(chat_id, {}).items() if (d.get("username") or "").lower() == username), None)
    if not found_uid:
        await update.message.reply_text(f"❌ @{username} غير موجود في القائمة.")
        return
    if chat_id not in group_settings: group_settings[chat_id] = {}
    if "blocked_mention" not in group_settings[chat_id]: group_settings[chat_id]["blocked_mention"] = []
    if found_uid not in group_settings[chat_id]["blocked_mention"]:
        group_settings[chat_id]["blocked_mention"].append(found_uid)
        save_settings(group_settings, chat_id)
        await update.message.reply_text(f"✅ تم منع @{username} من @all.")
    else:
        await update.message.reply_text(f"⚠️ @{username} ممنوع مسبقاً.")


async def unblock_mention(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رفع الحظر عن استخدام @all"""
    if not await is_telegram_admin(update, context):
        await update.message.reply_text("❌ هذا الأمر للمشرفين الفعليين فقط.")
        return
    chat_id = str(update.effective_chat.id)
    init_data(chat_id)
    if not context.args:
        await update.message.reply_text("❌ الاستخدام: /unblock_mention @username")
        return
    username = context.args[0].replace("@", "").lower()
    found_uid = next((uid for uid, d in group_members.get(chat_id, {}).items() if (d.get("username") or "").lower() == username), None)
    blocked = group_settings.get(chat_id, {}).get("blocked_mention", [])
    if found_uid and found_uid in blocked:
        blocked.remove(found_uid)
        group_settings[chat_id]["blocked_mention"] = blocked
        save_settings(group_settings, chat_id)
        await update.message.reply_text(f"✅ تم رفع الحظر عن @{username}.")
    else:
        await update.message.reply_text(f"⚠️ @{username} غير ممنوع أصلاً.")



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
        f"🚀 الاستضافة: {env_type}\n"
        f"🔖 الإصدار: `{BOT_VERSION}`",
        parse_mode=ParseMode.MARKDOWN
    )


def create_app(chat_id=None):
    """إنشاء التطبيق وإضافة المعالجات"""
    if not BOT_TOKEN: return None
    
    # Vercel bypass JobQueue & Updater
    is_vercel = "VERCEL" in os.environ or "VERCEL_URL" in os.environ or os.getenv("USE_WEBHOOK") == "True"
    if is_vercel:
        app = Application.builder().token(BOT_TOKEN).updater(None).job_queue(None).build()
    else:
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
        CommandHandler("setmsg", set_mention_message),
        CommandHandler("exclude", exclude_member),
        CommandHandler("unexclude", unexclude_member),
        CommandHandler("stats", show_stats),
        CommandHandler("export", export_members),
        CommandHandler("count", count_members),
        CommandHandler("id", get_user_id),
        CommandHandler("import", import_members),
        CommandHandler("schedule", schedule_mention),
        CommandHandler("setadmin", set_admin),
        CommandHandler("removeadmin", remove_admin),
        CommandHandler("listadmins", list_admins),
        CommandHandler("ping", ping_user),
        CommandHandler("mention_id", mention_by_id),
        CommandHandler("history", show_history),
        CommandHandler("backup", backup_data),
        CommandHandler("block_mention", block_mention),
        CommandHandler("unblock_mention", unblock_mention),
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, auto_add_new_member),
        MessageHandler(~filters.COMMAND, handle_message),
        CallbackQueryHandler(clear_confirm_callback, pattern=r"^clear_(confirm|cancel)"),
    ]
    
    # إضافة track_user في البداية (لتتبع كل الرسائل)
    app.add_handler(MessageHandler(filters.ALL, track_user), group=-1)
    
    for handler in handlers:
        app.add_handler(handler)

    # استعادة الجداول المحفوظة عند إعادة التشغيل
    try:
        from datetime import time as dt_time
        import pytz
        all_settings = load_settings()
        if app.job_queue is not None:
            for cid, sett in all_settings.items():
                sched = sett.get("schedule_time")
                if sched:
                    m = re.match(r'^(\d{1,2}):(\d{2})$', sched)
                    if m:
                        h, mi = int(m.group(1)), int(m.group(2))
                        tz = pytz.timezone('Asia/Riyadh')
                        app.job_queue.run_daily(
                            scheduled_mention_callback,
                            time=dt_time(hour=h, minute=mi, tzinfo=tz),
                            chat_id=int(cid),
                            name=f"schedule_{cid}",
                            data={"chat_id": cid}
                        )
                    logger.info(f"⏰ استعادة جدولة {cid} - {sched}")
    except Exception as e:
        logger.error(f"خطأ في استعادة الجداول: {e}")

    return app


def main():
    """تشغيل البوت بنظام Polling (محلياً أو Render)"""
    # منع التشغيل إذا كان الـ Webhook مفعلاً (لمنع التداخل)
    if os.getenv("USE_WEBHOOK") == "True" or "VERCEL" in os.environ:
        print("⚠️ تم اكتشاف بيئة Webhook (Vercel). سيتم إيقاف الـ Polling لمنع التعارض.")
        return

    application = create_app()
    if not application:
        return

    print("🚀 جاري تشغيل البوت...")
    print(f"📊 تم تحميل بيانات {len(group_members)} مجموعة")
    
    print("✅ البوت يعمل الآن!")
    print("📌 الأوامر: /add, /remove, /list, /count, /clear, @all")
    
    # تشغيل سيرفر الويب الوهمي (Keep Alive)
    # keep_alive()

    # بدء تشغيل البوت (مع حذف الويب هوك القديم لضمان العمل على Render)
    print("🚀 جاري تشغيل البوت بنظام Polling...")
    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
