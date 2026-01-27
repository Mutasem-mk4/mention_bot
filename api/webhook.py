from flask import Flask, request
from bot import create_app
import asyncio
from telegram import Update
import os

app = Flask(__name__)

# Initialize bot app
@app.route('/api/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == "GET":
        try:
            bot_app = create_app()
            if not bot_app:
                return "Config Error: BOT_TOKEN improperly set"
            return f"Bot Initialized Successfully. Token: {bot_app.bot.token[:5]}..."
        except Exception as e:
            return f"Initialization Error: {str(e)}"

    if request.method == "POST":
        async def process():
            try:
                bot_app = create_app()
                await bot_app.initialize()
                
                update_json = request.get_json(force=True)
                update = Update.de_json(update_json, bot_app.bot)
                
                await bot_app.process_update(update)
            except Exception as e:
                print(f"Error processing update: {e}")
                return "Error"
            finally:
                try:
                    await bot_app.shutdown()
                except:
                    pass
        
        try:
            asyncio.run(process())
            return "OK"
        except Exception as e:
            return f"Runtime Error: {str(e)}"
    
    return "OK"

@app.route('/')
def index():
    return "Bot is running on Vercel! 🚀"
