import os
import requests


def _configured():
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def _tg(method, **payload):
    """Calls the Telegram Bot API. Returns True when Telegram accepted it, and prints the reason when it did not."""
    try:
        r = requests.post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/{method}",
                          json={"chat_id": os.environ["TELEGRAM_CHAT_ID"], **payload}, timeout=60)
        if not r.ok:
            print(f"[notify] Telegram refused {method}: {r.status_code} {r.text[:200]}")
            return False
        return True
    except Exception as ex:
        print("[notify failed]", ex)
        return False


def notify(text, link=""):
    msg = f"{text}\n{link}".strip()
    if not _configured():
        print("[notify] Telegram is NOT configured (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is empty):", msg[:200])
        return False
    return _tg("sendMessage", text=msg[:4000], disable_web_page_preview=True)


def notify_media(photos, video, caption=""):
    """Sends the finished post to your Telegram so you can save it and post it by hand, for example with Instagram audio."""
    if not _configured():
        print("[notify] Telegram is NOT configured, so the finished media was not sent")
        return False
    if video:
        return _tg("sendVideo", video=video, caption=caption[:1000], supports_streaming=True)
    if len(photos) > 1:
        media = [{"type": "photo", "media": u, **({"caption": caption[:1000]} if i == 0 else {})}
                 for i, u in enumerate(photos[:10])]
        return _tg("sendMediaGroup", media=media)
    return _tg("sendPhoto", photo=photos[0], caption=caption[:1000])
