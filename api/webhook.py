from flask import Flask, request
from bot import create_app
import asyncio
from telegram import Update
import os

app = Flask(__name__)

# Initialize bot app
bot_app = create_app()

@app.route('/api/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        # Retrieve the update object from the request data
        update = Update.de_json(request.get_json(force=True), bot_app.bot)
        
        # Process the update asynchronously
        asyncio.run(bot_app.process_update(update))
        
        return "OK"
    return "OK"

@app.route('/')
def index():
    return "Bot is running on Vercel! 🚀"
