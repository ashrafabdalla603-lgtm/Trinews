"""Free media from Pixabay (photos + short videos). Needs PIXABAY_API_KEY secret.
Pixabay Content License allows commercial use. Cache results ≥ 24 h and never hotlink permanently."""
import os
import time
import hashlib
import json
import requests
from pathlib import Path

API = "https://pixabay.com/api"
CACHE_DIR = Path(__file__).parent / "pixabay_cache"
CACHE_TTL = 24 * 60 * 60  # 24 hours


def _key():
    return os.getenv("PIXABAY_API_KEY") or ""


def _cache_path(query: str, kind: str) -> Path:
    CACHE_DIR.mkdir(exist_ok=True)
    h = hashlib.md5(f"{kind}:{query.lower().strip()}".encode()).hexdigest()
    return CACHE_DIR / f"{h}.json"


def _get_cached(query: str, kind: str):
    p = _cache_path(query, kind)
    if p.exists() and (time.time() - p.stat().st_mtime) < CACHE_TTL:
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return None


def _set_cache(query: str, kind: str, data):
    try:
        _cache_path(query, kind).write_text(json.dumps(data))
    except Exception as ex:
        print(f"[pixabay] cache write failed: {ex}")


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

    cached = _get_cached(query, "photo")
    if cached is None:
        r = requests.get(
            f"{API}/",
            params={
                "key": _key(),
                "q": query,
                "image_type": "photo",
                "orientation": "vertical",   # good for Instagram
                "safesearch": "true",
                "per_page": 5,
            },
            timeout=20,
        )
        r.raise_for_status()
        cached = r.json()
        _set_cache(query, "photo", cached)

    for hit in cached.get("hits", []):
        try:
            # Prefer largeImageURL, fall back to webformatURL
            url = hit.get("largeImageURL") or hit.get("webformatURL")
            if not url:
                continue
            data = download(url)
            # Pixabay does not require attribution, but we keep a light credit
            credit = f"{hit.get('user') or 'Pixabay'} / Pixabay"
            return data, credit
        except Exception:
            continue
    return None, ""


def stock_video(query):
    """Returns (mp4 link, still image bytes or None, credit), or None."""
    if not (_key() and query):
        return None

    cached = _get_cached(query, "video")
    if cached is None:
        r = requests.get(
            f"{API}/videos/",
            params={
                "key": _key(),
                "q": query,
                "video_type": "film",
                "safesearch": "true",
                "per_page": 5,
            },
            timeout=20,
        )
        r.raise_for_status()
        cached = r.json()
        _set_cache(query, "video", cached)

    for hit in cached.get("hits", []):
        videos = hit.get("videos") or {}
        # Prefer medium → large → small
        for size in ("medium", "large", "small"):
            file = videos.get(size)
            if file and file.get("url"):
                try:
                    still = None
                    credit = f"{hit.get('user') or 'Pixabay'} / Pixabay"
                    return file["url"], still, credit
                except Exception:
                    continue
    return None


def get_media(it, fmt):
    """Returns (photo bytes, video bytes, credit, loop).
    Your own upload wins, then the stock media picked when the draft was made,
    then a fresh stock search. loop is True for short stock clips."""
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
                    video_url, still, credit = found
                    video = download(video_url)
                    photo = still
            else:
                photo, credit = stock_photo(it["image_query"])
        except Exception as ex:
            print(f"[media] stock search failed: {ex}")

    return photo, video, credit, bool(video) and bool(credit)
