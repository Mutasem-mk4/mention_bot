import requests, os, json
from dotenv import load_dotenv

load_dotenv()
token = "8117961022:AAG645K_cA6BZZdNQeH4CoQlt9VNSSUslhE"
url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
r = requests.get(url).json()

with open("webhook_debug.json", "w") as f:
    json.dump(r, f, indent=2)

if r['ok']:
    res = r['result']
    print(f"URL: {res.get('url')}")
    print(f"Pending: {res.get('pending_update_count')}")
    print(f"Last Error Date: {res.get('last_error_date')}")
    print(f"Last Error Msg: {res.get('last_error_message')}")
