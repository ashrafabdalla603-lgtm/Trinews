import os
import requests


def notify(text, link=""):
    """Telegram message. Without a token it just prints (handy for local runs)."""
    msg = f"{text}\n{link}".strip()
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        print("[notify]", msg)
        return
    try:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      json={"chat_id": chat, "text": msg[:4000], "disable_web_page_preview": True},
                      timeout=20)
    except Exception as ex:
        print("[notify failed]", ex)
