import asyncio
import json
import logging
import os
from threading import Lock

from flask import Flask, request
from dotenv import load_dotenv
import requests

app = Flask(__name__)
logger = logging.getLogger(__name__)
bot_app = None
bot_app_initialized = False
bot_app_lock = Lock()
create_app = None
init_data = None
Update = None

START_TEXT = (
    "🤖 مرحباً! أنا بوت المنشن\n\n"
    "📋 كيفية الاستخدام:\n"
    "• أضفني للمجموعة وامنحني صلاحيات أدمن\n"
    "• أرسل @all لمنشن جميع الأعضاء\n"
    "• أو استخدم /mention لمنشن جميع الأعضاء\n"
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


def send_message(chat_id, text, **extra):
    token = os.getenv("BOT_TOKEN")
    if not token:
        load_dotenv()
        token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is missing")

    payload = {"chat_id": chat_id, "text": text}
    payload.update(extra)
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json=payload,
        timeout=6,
    )
    response.raise_for_status()


def load_members_for_chat(chat_id):
    load_dotenv()
    chat_key = str(chat_id)
    mongo_uri = os.getenv("MONGO_URI")

    if mongo_uri:
        try:
            import certifi
            from pymongo import MongoClient

            client = MongoClient(
                mongo_uri,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=1200,
                connectTimeoutMS=1200,
            )
            doc = client.get_database("telegram_bot_db").members.find_one({"_id": chat_key})
            if doc:
                return doc.get("members", {}) or {}
        except Exception as exc:
            logger.warning("Fast member load from MongoDB failed: %s", exc)

    try:
        with open("members_data.json", "r", encoding="utf-8") as file:
            return (json.load(file).get(chat_key) or {})
    except Exception as exc:
        logger.warning("Fast member load from JSON failed: %s", exc)
        return {}


def format_member(data):
    username = data.get("username")
    if username:
        return f"@{username}"
    return data.get("full_name") or data.get("first_name") or "Unknown"


def try_fast_command(update_json):
    message = update_json.get("message") or {}
    text = message.get("text") or ""
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    command = text.split(maxsplit=1)[0].split("@", 1)[0].lower() if text else ""
    if not chat_id:
        return False

    if command in {"/start", "/help"}:
        send_message(chat_id, START_TEXT)
        return True

    if command == "/count":
        members = load_members_for_chat(chat_id)
        send_message(chat_id, f"👥 عدد الأعضاء المحفوظين: {len(members)}")
        return True

    if command == "/list":
        args = text.split(maxsplit=1)
        search_term = args[1].lower().strip() if len(args) > 1 else ""
        members = load_members_for_chat(chat_id)
        if not members:
            send_message(chat_id, "📭 القائمة فارغة!")
            return True

        lines = []
        for data in members.values():
            display = format_member(data)
            if search_term and search_term not in display.lower():
                continue
            multiplier = data.get("multiplier", 1)
            boost = f" (x{multiplier})" if multiplier > 1 else ""
            lines.append(f"• {display}{boost}")

        if not lines:
            send_message(chat_id, f"🔍 لم يُعثر على '{search_term}' في القائمة.")
            return True

        title = f"📌 نتائج '{search_term}'" if search_term else f"📋 الأعضاء المحفوظين ({len(lines)})"
        out = title + ":\n\n" + "\n".join(lines[:100])
        if len(lines) > 100:
            out += f"\n\n... و{len(lines) - 100} آخرين."
        send_message(chat_id, out)
        return True

    return False


def ensure_app_created():
    global bot_app, create_app, init_data, Update
    if bot_app is not None:
        return

    from telegram import Update as TelegramUpdate
    from bot import create_app as build_app, init_data as load_chat_data

    create_app = build_app
    init_data = load_chat_data
    Update = TelegramUpdate
    bot_app = create_app()

async def _initialize_app():
    ensure_app_created()
    if bot_app is None:
        raise RuntimeError("BOT_TOKEN is missing")
    await bot_app.initialize()


def ensure_initialized():
    global bot_app_initialized
    if bot_app_initialized:
        return
    with bot_app_lock:
        if bot_app_initialized:
            return
        ensure_app_created()
        asyncio.run(_initialize_app())
        bot_app_initialized = True


async def _process_update(update_json, chat_id):
    ensure_app_created()
    if bot_app is None:
        raise RuntimeError("BOT_TOKEN is missing")

    if chat_id is not None:
        init_data(chat_id)

    update = Update.de_json(update_json, bot_app.bot)
    await bot_app.process_update(update)

@app.route('/api/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == "GET":
        token = os.getenv("BOT_TOKEN", "MISSING")
        masked_token = f"{token[:10]}...{token[-5:]}" if token != "MISSING" else "MISSING"
        db_uri = "SET" if os.getenv("MONGO_URI") else "MISSING"
        return f"Bot Status: Active (v6-diagnostic) | Token: {masked_token} | DB: {db_uri} 🚀"

    if request.method == "POST":
        try:
            update_json = request.get_json(force=True, silent=False)

            chat_id = None
            if "message" in update_json:
                chat_id = update_json["message"]["chat"]["id"]
            elif "callback_query" in update_json:
                chat_id = update_json["callback_query"]["message"]["chat"]["id"]

            if not try_fast_command(update_json):
                ensure_initialized()
                asyncio.run(_process_update(update_json, chat_id))
            return "OK", 200
        except Exception as e:
            logger.exception("Webhook processing failed")
            return f"Error: {str(e)}", 500
    
    return "OK"

@app.route('/')
def index():
    return "Bot is running on Vercel! 🚀"
