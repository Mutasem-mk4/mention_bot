import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("BOT_TOKEN")

def check_webhook():
    print(f"Checking token: {token[:10]}...{token[-5:]}")
    url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    r = requests.get(url).json()
    print(f"Webhook Info: {json.dumps(r, indent=2)}")
    
    url_me = f"https://api.telegram.org/bot{token}/getMe"
    r_me = requests.get(url_me).json()
    print(f"Bot Identity: {json.dumps(r_me, indent=2)}")

if __name__ == "__main__":
    check_webhook()
