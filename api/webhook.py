import asyncio
import logging
import os

from flask import Flask, request
from telegram import Update

from bot import create_app

app = Flask(__name__)
logger = logging.getLogger(__name__)


async def _process_update(update_json, chat_id):
    bot_app = create_app(chat_id)
    if bot_app is None:
        raise RuntimeError("BOT_TOKEN is missing")

    await bot_app.initialize()
    try:
        update = Update.de_json(update_json, bot_app.bot)
        await bot_app.process_update(update)
    finally:
        await bot_app.shutdown()

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

            asyncio.run(_process_update(update_json, chat_id))
            return "OK", 200
        except Exception as e:
            logger.exception("Webhook processing failed")
            return f"Error: {str(e)}", 500
    
    return "OK"

@app.route('/')
def index():
    return "Bot is running on Vercel! 🚀"
