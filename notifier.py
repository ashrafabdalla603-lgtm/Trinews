import os
import requests


def notify(text, link=""):
    """Sends a Telegram message. Returns True when Telegram accepted it, and prints the reason when it did not."""
    msg = f"{text}\n{link}".strip()
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        print("[notify] Telegram is NOT configured (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is empty):", msg[:200])
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          json={"chat_id": chat, "text": msg[:4000], "disable_web_page_preview": True},
                          timeout=20)
        if not r.ok:
            print(f"[notify] Telegram refused the message: {r.status_code} {r.text[:200]}")
            return False
        return True
    except Exception as ex:
        print("[notify failed]", ex)
        return False
