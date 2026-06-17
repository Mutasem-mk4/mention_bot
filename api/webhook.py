import asyncio
import html
import json
import logging
import os
import re
import time
from threading import Lock

from flask import Flask, request
from dotenv import load_dotenv
import requests

app = Flask(__name__)
logger = logging.getLogger(__name__)
load_dotenv()
bot_app = None
bot_app_initialized = False
bot_app_lock = Lock()
create_app = None
init_data = None
Update = None
mongo_client = None

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
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    attempts = 0
    while attempts < 3:
        try:
            response = requests.post(url, json=payload, timeout=6)
            if response.status_code == 200:
                return True
            elif response.status_code == 429:
                res_data = response.json()
                retry_after = res_data.get("parameters", {}).get("retry_after", 5)
                logger.warning(f"Telegram 429! Sleeping for {retry_after}s...")
                time.sleep(retry_after + 1)
                attempts += 1
            else:
                response.raise_for_status()
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            time.sleep(1)
            attempts += 1
    return False


def telegram_get(method, params, timeout=4):
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is missing")

    response = requests.get(
        f"https://api.telegram.org/bot{token}/{method}",
        params=params,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def get_chat_member_count(chat_id):
    try:
        data = telegram_get("getChatMemberCount", {"chat_id": chat_id}, timeout=4)
        if data.get("ok"):
            return data.get("result")
    except Exception as exc:
        logger.warning("Telegram member count failed: %s", exc)
    return None


def load_settings_for_chat(chat_id):
    chat_key = str(chat_id)
    from bot import github_client
    if github_client is not None:
        try:
            data, _ = github_client.get_file("settings.json")
            if data:
                return data.get(chat_key) or {}
        except Exception as exc:
            logger.warning("Fast settings load from GitHub failed: %s", exc)
        return {}

    try:
        with open("settings.json", "r", encoding="utf-8") as file:
            settings = json.load(file).get(chat_key) or {}
            if settings:
                return settings
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.warning("Fast settings load from JSON failed: %s", exc)

    return {}


def load_members_from_json(chat_key):
    try:
        with open("members_data.json", "r", encoding="utf-8") as file:
            return json.load(file).get(chat_key) or {}
    except Exception as exc:
        logger.warning("Fast member load from JSON failed: %s", exc)
        return {}


def load_members_from_mongo(chat_key):
    global mongo_client
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        return {}

    try:
        import certifi
        from pymongo import MongoClient

        if mongo_client is None:
            mongo_client = MongoClient(
                mongo_uri,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=1800,
                connectTimeoutMS=1800,
            )
        doc = mongo_client.get_database("telegram_bot_db").members.find_one({"_id": chat_key})
        if doc:
            return doc.get("members", {}) or {}
    except Exception as exc:
        logger.warning("Fast member load from MongoDB failed: %s", exc)

    return {}


def load_members_for_chat(chat_id):
    chat_key = str(chat_id)
    from bot import github_client
    if github_client is not None:
        try:
            data, _ = github_client.get_file("members_data.json")
            if data:
                return data.get(chat_key) or {}
        except Exception as exc:
            logger.warning("Fast member load from GitHub failed: %s", exc)
        return {}

    if os.getenv("VERCEL") or os.getenv("VERCEL_URL"):
        local_members = load_members_from_json(chat_key)
        mongo_members = load_members_from_mongo(chat_key)
        return {**local_members, **mongo_members}

    return load_members_from_json(chat_key)


def save_member_to_mongo(chat_id, user):
    chat_key = str(chat_id)
    user_id = str(user.get("id"))
    if not user_id or user.get("is_bot"):
        return

    current = load_members_from_mongo(chat_key)
    existing = current.get(user_id, {})
    current[user_id] = {
        "username": user.get("username"),
        "first_name": user.get("first_name") or "User",
        "full_name": " ".join(
            part for part in [user.get("first_name"), user.get("last_name")] if part
        ) or user.get("first_name") or "User",
        "multiplier": existing.get("multiplier", 1),
        "message_count": existing.get("message_count", 0),
    }
    try:
        load_members_from_mongo(chat_key)
        if mongo_client is not None:
            mongo_client.get_database("telegram_bot_db").members.update_one(
                {"_id": chat_key},
                {"$set": {"members": current}},
                upsert=True,
            )
    except Exception as exc:
        logger.warning("Fast member save to MongoDB failed: %s", exc)


def format_member(data):
    username = data.get("username")
    if username:
        return f"@{username}"
    return data.get("full_name") or data.get("first_name") or "Unknown"


def is_anonymous_group_admin(message, chat_id):
    sender_chat = message.get("sender_chat") or {}
    return sender_chat.get("id") == chat_id


def is_telegram_admin(message, chat_id):
    if is_anonymous_group_admin(message, chat_id):
        return True

    user = message.get("from") or {}
    user_id = user.get("id")
    if not user_id:
        return False

    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is missing")

    result = telegram_get(
        "getChatMember",
        {"chat_id": chat_id, "user_id": user_id},
        timeout=4,
    ).get("result") or {}
    return result.get("status") in {"creator", "administrator"}


def mention_text(uid, data):
    username = data.get("username")
    if username:
        return f"@{username}"
    name = html.escape(data.get("full_name") or data.get("first_name") or "User")
    return f'<a href="tg://user?id={uid}">{name}</a>'


def try_fast_mention_all(message, chat_id, text):
    match = re.search(r"(?:^|\s)@(?:all|everyone)(?:\s+(\d+))?\b", text, re.IGNORECASE)
    if not match:
        return False

    if not is_telegram_admin(message, chat_id):
        send_message(
            chat_id,
            "⚠️ المعذرة، هذا الأمر متاح للمشرفين فقط.",
            reply_to_message_id=message.get("message_id"),
        )
        return True

    rounds = int(match.group(1) or 1)
    rounds = max(1, min(rounds, 10))
    quiet = bool(re.search(r"\bquiet\b", text, re.IGNORECASE))
    members = load_members_for_chat(chat_id)
    settings = load_settings_for_chat(chat_id)
    actual_count = get_chat_member_count(chat_id)
    excluded = set(settings.get("excluded", []))
    custom_msg = html.escape(settings.get("mention_message", "📣"))

    valid_members = []
    for uid, data in members.items():
        if uid in excluded:
            continue
        multiplier = min(data.get("multiplier", 1), 5)
        for _ in range(multiplier):
            valid_members.append((uid, data))

    if not valid_members:
        suffix = f"\n👥 عدد أعضاء المجموعة في تيليجرام: {actual_count}" if actual_count else ""
        send_message(chat_id, "📭 قائمة المنشن المحفوظة فارغة!" + suffix, reply_to_message_id=message.get("message_id"))
        return True

    unique_saved = len({uid for uid, _ in valid_members})
    if actual_count and unique_saved < max(5, actual_count // 2):
        send_message(
            chat_id,
            f"⚠️ المجموعة فيها {actual_count} عضو، لكن البوت حافظ {unique_saved} فقط للمنشن.\n"
            "تيليجرام لا يسمح للبوت بجلب كل الأعضاء تلقائياً. خلي الأعضاء يرسلوا رسالة، أو أضفهم بـ /add أو /import.",
            reply_to_message_id=message.get("message_id"),
        )

    batch_size = 5
    total_batches = (len(valid_members) + batch_size - 1) // batch_size
    reply_to = message.get("reply_to_message", {}).get("message_id") or message.get("message_id")

    batches = []
    host_url = request.host_url
    api_url = f"{host_url}api/send_batch"
    token = os.getenv("BOT_TOKEN")

    for round_num in range(1, rounds + 1):
        round_prefix = f"({round_num}/{rounds}) " if rounds > 1 else ""
        for index in range(0, len(valid_members), batch_size):
            batch = valid_members[index:index + batch_size]
            batch_num = (index // batch_size) + 1
            mentions = " ".join(mention_text(uid, data) for uid, data in batch)
            batches.append(f"{custom_msg} {round_prefix}[{batch_num}/{total_batches}]\n{mentions}")

    if not quiet:
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
        batches.append(random.choice(completion_msgs))

    # Trigger the first batch asynchronously
    first_payload = {
        "token": token,
        "chat_id": chat_id,
        "batches": batches,
        "reply_to_message_id": reply_to,
        "current_index": 0
    }

    try:
        requests.post(api_url, json=first_payload, timeout=0.25)
    except requests.exceptions.Timeout:
        pass
    except Exception as e:
        logger.error(f"Failed to trigger first batch: {e}")

    return True


def try_fast_command(update_json):
    message = update_json.get("message") or {}
    text = message.get("text") or ""
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    command = text.split(maxsplit=1)[0].split("@", 1)[0].lower() if text else ""
    if not chat_id:
        return False

    if try_fast_mention_all(message, chat_id, text):
        return True

    if command in {"/start", "/help"}:
        send_message(chat_id, START_TEXT)
        return True

    if command == "/count":
        members = load_members_for_chat(chat_id)
        actual_count = get_chat_member_count(chat_id)
        text_out = f"👥 أعضاء المنشن المحفوظين: {len(members)}"
        if actual_count is not None:
            text_out += f"\n👥 أعضاء المجموعة في تيليجرام: {actual_count}"
        send_message(chat_id, text_out)
        return True

    if command == "/list":
        args = text.split(maxsplit=1)
        search_term = args[1].lower().strip() if len(args) > 1 else ""
        members = load_members_for_chat(chat_id)
        actual_count = get_chat_member_count(chat_id)
        if not members:
            suffix = f"\n👥 أعضاء المجموعة في تيليجرام: {actual_count}" if actual_count is not None else ""
            send_message(chat_id, "📭 قائمة المنشن المحفوظة فارغة!" + suffix)
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

        title = f"📌 نتائج '{search_term}'" if search_term else f"📋 أعضاء المنشن المحفوظين ({len(lines)})"
        out = title + ":\n\n" + "\n".join(lines[:100])
        if len(lines) > 100:
            out += f"\n\n... و{len(lines) - 100} آخرين."
        if actual_count is not None:
            out += f"\n\n👥 أعضاء المجموعة في تيليجرام: {actual_count}"
            if len(members) < actual_count:
                out += f"\n⚠️ البوت لا يملك إلا {len(members)} عضو محفوظ للمنشن."
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

@app.route('/api/send_batch', methods=['POST'])
def send_batch():
    try:
        data = request.get_json(force=True, silent=True) or {}
        token = data.get("token")
        if not token or token != os.getenv("BOT_TOKEN"):
            return "Unauthorized", 401

        chat_id = data.get("chat_id")
        batches = data.get("batches")
        reply_to_id = data.get("reply_to_message_id")
        current_index = data.get("current_index", 0)

        if not batches or not isinstance(batches, list) or current_index >= len(batches):
            return "Invalid index or empty batches", 400

        text = batches[current_index]

        # Send this batch with retry handling
        send_message(
            chat_id,
            text,
            reply_to_message_id=reply_to_id,
            parse_mode="HTML"
        )

        # If there are more batches, sleep and trigger the next one
        if current_index + 1 < len(batches):
            # Sleep 2.5 seconds to respect Telegram's rate limit per group
            time.sleep(2.5)

            next_payload = {
                "token": token,
                "chat_id": chat_id,
                "batches": batches,
                "reply_to_message_id": reply_to_id,
                "current_index": current_index + 1
            }

            host_url = request.host_url
            api_url = f"{host_url}api/send_batch"

            try:
                requests.post(api_url, json=next_payload, timeout=0.25)
            except requests.exceptions.Timeout:
                pass
            except Exception as e:
                logger.error(f"Failed to trigger next batch: {e}")

        return "OK", 200
    except Exception as e:
        logger.error(f"Error in send_batch: {e}")
        return str(e), 500

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

            # Ignore old messages to prevent spamming old queued mentions
            message = update_json.get("message")
            if message:
                msg_date = message.get("date")
                if msg_date and (time.time() - msg_date) > 90:
                    logger.info(f"Skipping old message from {msg_date} (current: {time.time()})")
                    return "OK", 200

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
