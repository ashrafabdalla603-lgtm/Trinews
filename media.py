"""Free, licensed media from Pexels (photos and short clips). Needs the PEXELS_API_KEY secret.
Nothing is ever copied from Instagram, TikTok, YouTube or other publishers."""
import os
import requests

API = "https://api.pexels.com"


def _key():
    return os.getenv("PEXELS_API_KEY") or ""


def download(url, limit=60_000_000):
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    if len(r.content) > limit:
        raise ValueError("file is too large")
    return r.content


def stock_photo(query):
    """Returns (photo bytes, credit) or (None, "")."""
    if not (_key() and query):
        return None, ""
    r = requests.get(f"{API}/v1/search", headers={"Authorization": _key()},
                     params={"query": query, "orientation": "portrait", "per_page": 5}, timeout=20)
    r.raise_for_status()
    for p in r.json().get("photos", []):
        try:
            data = download(p["src"].get("large2x") or p["src"]["large"])
            return data, f"{p.get('photographer') or 'Pexels photographer'} / Pexels"
        except Exception:
            continue
    return None, ""


def stock_video(query):
    """Returns (mp4 link, still image bytes or None, credit), or None."""
    if not (_key() and query):
        return None
    r = requests.get(f"{API}/videos/search", headers={"Authorization": _key()},
                     params={"query": query, "orientation": "portrait", "size": "medium", "per_page": 5}, timeout=20)
    r.raise_for_status()
    for v in r.json().get("videos", []):
        files = [f for f in v.get("video_files", [])
                 if f.get("file_type") == "video/mp4" and (f.get("width") or 0) >= 540]
        if not files:
            continue
        best = min(files, key=lambda f: abs(f["width"] - 1080))
        try:
            still = download(v["image"]) if v.get("image") else None
        except Exception:
            still = None
        return best["link"], still, f"{(v.get('user') or {}).get('name') or 'Pexels videographer'} / Pexels"
    return None


def get_media(it, fmt):
    """Returns (photo bytes, video bytes, credit, loop). Your own upload wins, then the stock media picked when
    the draft was made, then a fresh stock search. loop is True for short stock clips."""
    photo = video = None
    credit = it.get("photo_credit") or ""
    try:
        if it.get("video_url"):
            video = download(it["video_url"])
        if it.get("photo_url"):
            photo = download(it["photo_url"])
    except Exception as ex:
        print(f"[media] could not download the saved media: {ex}")
    if not (photo or video) and it.get("use_stock", True) and it.get("image_query"):
        try:
            if fmt == "reel":
                found = stock_video(it["image_query"])
                if found:
                    video, photo, credit = download(found[0]), found[1], found[2]
            else:
                photo, credit = stock_photo(it["image_query"])
        except Exception as ex:
            print(f"[media] stock search failed: {ex}")
    return photo, video, credit, bool(video) and bool(credit)
