from flask import Flask, request
from bot import create_app
import asyncio
from telegram import Update
import os

app = Flask(__name__)

@app.route('/api/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == "GET":
        token = os.getenv("BOT_TOKEN", "MISSING")
        masked_token = f"{token[:10]}...{token[-5:]}" if token != "MISSING" else "MISSING"
        db_uri = "SET" if os.getenv("MONGO_URI") else "MISSING"
        return f"Bot Status: Active (v6-diagnostic) | Token: {masked_token} | DB: {db_uri} 🚀"

    if request.method == "POST":
        async def process():
            try:
                # NUCLEAR DEBUG: Raw message before anything else
                import requests
                token = os.getenv("BOT_TOKEN")
                requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                             json={"chat_id": 1616533142, "text": "☢️ Vercel Executing Webhook..."})

                update_json = request.get_json(force=True)
                
                # Identify chat_id for optimized loading
                chat_id = None
                if "message" in update_json:
                    chat_id = update_json["message"]["chat"]["id"]
                elif "callback_query" in update_json:
                    chat_id = update_json["callback_query"]["message"]["chat"]["id"]

                bot_app = create_app(chat_id)
                await bot_app.initialize()
                
                update = Update.de_json(update_json, bot_app.bot)
                await bot_app.process_update(update)
                
                return "OK", 200
            except Exception as e:
                import traceback
                error_msg = f"❌ Execution Error: {e}\n{traceback.format_exc()}"
                requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                             json={"chat_id": 1616533142, "text": error_msg[:300]})
                return f"Error: {str(e)}", 500
        
        return asyncio.run(process())
    
    return "OK"

@app.route('/')
def index():
    return "Bot is running on Vercel! 🚀"
