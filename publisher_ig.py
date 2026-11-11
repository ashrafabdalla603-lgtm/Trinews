import os
import time
import requests

G = f"{os.getenv('GRAPH_HOST') or 'https://graph.facebook.com'}/{os.getenv('GRAPH_VERSION') or 'v23.0'}"   # GRAPH_HOST=https://graph.instagram.com for Instagram Login tokens
IG = os.environ["IG_USER_ID"]
TOKEN = os.environ["IG_ACCESS_TOKEN"]


def _post(path, **data):
    r = requests.post(f"{G}/{path}", data={**data, "access_token": TOKEN}, timeout=60)
    if not r.ok:
        raise RuntimeError(f"Graph API {r.status_code}: {r.text[:400]}")
    return r.json()


def _wait(container_id, tries=36):
    for _ in range(tries):
        r = requests.get(f"{G}/{container_id}",
                         params={"fields": "status_code", "access_token": TOKEN}, timeout=30).json()
        code = r.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Media container {code}: {r}")
        time.sleep(5)
    raise RuntimeError("Media container timed out")


def publish(kind, caption, image_urls, video_url=None):
    """kind: feed | carousel | reel | story. Returns the Instagram media id."""
    if kind == "story":
        if video_url:
            c = _post(f"{IG}/media", video_url=video_url, media_type="STORIES")
        else:
            c = _post(f"{IG}/media", image_url=image_urls[0], media_type="STORIES")
    elif kind == "reel":
        c = _post(f"{IG}/media", video_url=video_url, media_type="REELS", caption=caption, share_to_feed="true")
    elif kind == "carousel":
        kids = [_post(f"{IG}/media", image_url=u, is_carousel_item="true")["id"] for u in image_urls]
        for k in kids:
            _wait(k)
        c = _post(f"{IG}/media", media_type="CAROUSEL", children=",".join(kids), caption=caption)
    else:
        c = _post(f"{IG}/media", image_url=image_urls[0], caption=caption)
    _wait(c["id"])
    return _post(f"{IG}/media_publish", creation_id=c["id"])["id"]
