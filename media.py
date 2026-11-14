"""Free, licensed stock photos and short clips from Pexels or Pixabay (set PEXELS_API_KEY and/or PIXABAY_API_KEY).
Nothing is ever copied from Instagram, TikTok, YouTube or other publishers."""
import os
import requests

PEXELS = "https://api.pexels.com"


def _pexels_key():
    return os.getenv("PEXELS_API_KEY") or ""


def _pixabay_key():
    return os.getenv("PIXABAY_API_KEY") or ""


def stock_enabled():
    return bool(_pexels_key() or _pixabay_key())


def download(url, limit=60_000_000):
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    if len(r.content) > limit:
        raise ValueError("file is too large")
    return r.content


def _pexels_photo(query):
    r = requests.get(f"{PEXELS}/v1/search", headers={"Authorization": _pexels_key()},
                     params={"query": query, "orientation": "portrait", "per_page": 5}, timeout=20)
    r.raise_for_status()
    for p in r.json().get("photos", []):
        try:
            data = download(p["src"].get("large2x") or p["src"]["large"])
            return data, f"{p.get('photographer') or 'Pexels photographer'} / Pexels"
        except Exception:
            continue
    return None, ""


def _pixabay_photo(query):
    r = requests.get("https://pixabay.com/api/",
                     params={"key": _pixabay_key(), "q": query[:100], "image_type": "photo", "orientation": "vertical",
                             "safesearch": "true", "per_page": 5, "min_width": 800}, timeout=20)
    r.raise_for_status()
    for h in r.json().get("hits", []):
        try:
            data = download(h.get("largeImageURL") or h["webformatURL"])
            return data, f"{h.get('user') or 'Pixabay contributor'} / Pixabay"
        except Exception:
            continue
    return None, ""


def stock_photo(query):
    """Returns (photo bytes, credit) or (None, ""). Tries Pexels, then Pixabay, then a shorter phrase."""
    if not query:
        return None, ""
    for fn, key in ((_pexels_photo, _pexels_key()), (_pixabay_photo, _pixabay_key())):
        if not key:
            continue
        try:
            data, credit = fn(query)
            if data:
                return data, credit
        except Exception as ex:
            print(f"[media] {fn.__name__} failed: {ex}")
    words = query.split()
    return stock_photo(" ".join(words[:2])) if len(words) > 2 else (None, "")


def _pexels_video(query):
    r = requests.get(f"{PEXELS}/videos/search", headers={"Authorization": _pexels_key()},
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


def _pixabay_video(query):
    r = requests.get("https://pixabay.com/api/videos/",
                     params={"key": _pixabay_key(), "q": query[:100], "safesearch": "true", "per_page": 5}, timeout=20)
    r.raise_for_status()
    for h in r.json().get("hits", []):
        pick = (h.get("videos") or {}).get("large") or (h.get("videos") or {}).get("medium") or {}
        if not pick.get("url"):
            continue
        still = None
        if h.get("picture_id"):
            try:
                still = download(f"https://i.vimeocdn.com/video/{h['picture_id']}_640x360.jpg")
            except Exception:
                still = None
        return pick["url"], still, f"{h.get('user') or 'Pixabay contributor'} / Pixabay"
    return None


def stock_video(query):
    """Returns (mp4 link, still image bytes or None, credit), or None."""
    if not query:
        return None
    for fn, key in ((_pexels_video, _pexels_key()), (_pixabay_video, _pixabay_key())):
        if not key:
            continue
        try:
            found = fn(query)
            if found:
                return found
        except Exception as ex:
            print(f"[media] {fn.__name__} failed: {ex}")
    words = query.split()
    return stock_video(" ".join(words[:2])) if len(words) > 2 else None


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
