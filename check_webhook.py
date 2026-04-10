import os
import sys

import requests
from dotenv import load_dotenv


def mask_token(token: str) -> str:
    if not token or len(token) < 8:
        return "MISSING"
    return f"{token[:10]}...{token[-5:]}"


def main() -> int:
    load_dotenv()

    token = os.getenv("BOT_TOKEN")
    webhook_url = os.getenv("WEBHOOK_URL", "https://telegram-mention-bot.vercel.app/api/webhook")

    if not token:
        print("FAIL: BOT_TOKEN is missing in .env")
        return 1

    print(f"Token: {mask_token(token)}")
    print(f"Webhook URL: {webhook_url}")

    api_base = f"https://api.telegram.org/bot{token}"
    checks = []

    try:
        me = requests.get(f"{api_base}/getMe", timeout=20).json()
        ok = bool(me.get("ok"))
        checks.append(("getMe", ok, me))
    except Exception as e:
        checks.append(("getMe", False, str(e)))

    try:
        webhook = requests.get(f"{api_base}/getWebhookInfo", timeout=20).json()
        ok = bool(webhook.get("ok"))
        checks.append(("getWebhookInfo", ok, webhook))
    except Exception as e:
        checks.append(("getWebhookInfo", False, str(e)))
        webhook = {}

    try:
        health = requests.get(webhook_url, timeout=20)
        ok = health.status_code == 200
        checks.append(("healthcheck", ok, {"status_code": health.status_code, "body": health.text[:200]}))
    except Exception as e:
        checks.append(("healthcheck", False, str(e)))

    print()
    all_ok = True
    for name, ok, data in checks:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        if name == "getWebhookInfo" and isinstance(data, dict) and data.get("ok"):
            result = data.get("result", {})
            current_url = result.get("url")
            last_error = result.get("last_error_message")
            pending = result.get("pending_update_count")
            print(f"  current_url: {current_url}")
            print(f"  pending_updates: {pending}")
            print(f"  last_error_message: {last_error or 'NONE'}")
            if current_url != webhook_url:
                all_ok = False
                print("  FAIL: webhook URL does not match expected deployment URL")
            if last_error:
                all_ok = False
        elif name == "getMe" and isinstance(data, dict) and data.get("ok"):
            result = data.get("result", {})
            print(f"  bot_username: @{result.get('username')}")
            print(f"  bot_name: {result.get('first_name')}")
        elif name == "healthcheck" and isinstance(data, dict):
            print(f"  status_code: {data['status_code']}")
            print(f"  body: {data['body']}")
            if data["status_code"] != 200:
                all_ok = False
        else:
            print(f"  detail: {data}")
            all_ok = False

    print()
    if all_ok:
        print("OVERALL: PASS")
        return 0

    print("OVERALL: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
