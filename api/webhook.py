import asyncio
import logging
import os
from threading import Lock

from flask import Flask, request
from telegram import Update

from bot import create_app, init_data

app = Flask(__name__)
logger = logging.getLogger(__name__)
bot_app = create_app()
bot_app_initialized = False
bot_app_lock = Lock()

async def _initialize_app():
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
        asyncio.run(_initialize_app())
        bot_app_initialized = True


async def _process_update(update_json, chat_id):
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
