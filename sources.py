import os
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin
import datetime as dt
import feedparser
import requests
from notifier import notify
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (compatible; NewsdeskBot/1.0)"}

def _gn(q):
    return f"https://news.google.com/rss/search?q={q}&hl=en-KE&gl=KE&ceid=KE:en"


# (name, url, type, category, trust 1-5)
# 'rss' = a news feed. 'watch' = an official page with no feed (flags NEW links). 'tips' = messages you send
# to your Telegram bot. Instagram and Facebook pages cannot be read automatically (it breaks their rules and
# gets accounts banned), so use tips for those. Feed addresses can go dead: check the sources table.
SEED = [
    ("Your tips (Telegram)", "telegram://tips", "tips", "tips", 4),
    ("Tuko", "https://www.tuko.co.ke/rss/all.rss", "rss", "gossip", 2),
    ("Kenyans.co.ke", "https://www.kenyans.co.ke/feeds/news", "rss", "news", 3),
    ("Capital FM Lifestyle", "https://www.capitalfm.co.ke/lifestyle/feed/", "rss", "entertainment", 3),
    ("News: gossip pages", _gn("%22Nairobi+Gossip+Club%22+OR+%22Kenya+Gossip+Club%22+OR+%22Buzz+Room%22+OR+Mpashogram+OR+%22Kenya+Times+News%22+OR+%22Migori+Gossip+Club%22+when:3d"), "rss", "gossip", 2),
    ("News: Kenya celebrity gossip", _gn("Kenya+celebrity+OR+gossip+OR+%22baby+mama%22+OR+wedding+OR+breakup+when:1d"), "rss", "gossip", 2),
    ("News: Kenya viral and trending", _gn("Kenya+viral+OR+trending+OR+%22went+viral%22+OR+backlash+when:1d"), "rss", "viral", 2),
    ("News: music and comedy", _gn("Kenyan+musician+OR+gengetone+OR+%22gospel+artiste%22+OR+comedian+OR+influencer+when:2d"), "rss", "entertainment", 2),
    ("News: watchlist", _gn("Bahati+OR+%22Oga+Obinna%22+OR+Lodwar+when:2d"), "rss", "watchlist", 2),
]


def seed_sources(sb):
    rows = [{"name": n, "url": u, "type": t, "category": c, "trust_level": tr} for n, u, t, c, tr in SEED]
    sb.table("sources").upsert(rows, on_conflict="url").execute()


def _clean(html):
    return BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)


def _page_text(url):
    try:
        r = requests.get(url, headers=UA, timeout=20)
        if "html" not in r.headers.get("content-type", ""):
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script", "style", "nav", "footer", "header"]):
            t.decompose()
        return soup.get_text(" ", strip=True)[:2500]
    except Exception:
        return ""


def fetch_rss(s):
    out = []
    for e in feedparser.parse(s["url"], request_headers=UA).entries[:30]:
        pub = None
        if getattr(e, "published_parsed", None):
            pub = dt.datetime(*e.published_parsed[:6], tzinfo=dt.timezone.utc)
        out.append({
            "title": e.get("title", ""),
            "url": e.get("link"),
            "text": _clean(e.get("summary") or e.get("description") or ""),
            "published": pub,
        })
    return [o for o in out if o["url"]]


def fetch_watch(s, sb):
    r = requests.get(s["url"], headers=UA, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    links = {}
    for a in soup.find_all("a", href=True):
        t = a.get_text(" ", strip=True)
        if len(t) >= 25:                      # skips menu items
            links[urljoin(s["url"], a["href"])] = t
    seen = set((s.get("state") or {}).get("seen", []))
    first_run = not seen
    new = {u: t for u, t in links.items() if u not in seen}
    keep = list(links) + [u for u in seen if u not in links]
    sb.table("sources").update({"state": {"seen": keep[:1000]}}).eq("id", s["id"]).execute()
    if first_run:                             # first run only learns what is already there
        return []
    return [{"title": t, "url": u, "text": _page_text(u) or t, "published": None}
            for u, t in list(new.items())[:5]]


def _tg_file(tok, file_id):
    r = requests.get(f"https://api.telegram.org/bot{tok}/getFile", params={"file_id": file_id}, timeout=20)
    r.raise_for_status()
    path = r.json()["result"]["file_path"]
    f = requests.get(f"https://api.telegram.org/file/bot{tok}/{path}", timeout=90)
    f.raise_for_status()
    return f.content, path.rsplit(".", 1)[-1].lower()


def _store(sb, data, name, ctype):
    bucket = sb.storage.from_("media")
    bucket.upload(name, data, {"content-type": ctype, "upsert": "true"})
    return bucket.get_public_url(name)


_TIPS = {"source": None, "ids": [], "last": 0}   # what the last fetch_tips call returned, confirmed after drafting


def fetch_tips(s, sb):
    """Messages you send to your Tri News Alerts bot become story tips. Send text, or just screenshots of gossip
    stories (up to 10 at a time, as photos or files): the AI reads each one and credits the page. A photo or video is
    only posted when the caption says 'use photo' or 'use video', so someone else's screenshot is never republished."""
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), str(os.getenv("TELEGRAM_CHAT_ID") or "")
    if not (tok and chat):
        return []
    offset = (s.get("state") or {}).get("offset", 0)
    r = requests.get(f"https://api.telegram.org/bot{tok}/getUpdates",
                     params={"offset": offset, "timeout": 0}, timeout=20)
    r.raise_for_status()
    out, ids, last = [], [], offset - 1
    use_rx = re.compile(r"\buse (this |my |the )?(photo|pic|picture|image|video|clip|it)\b", re.I)
    for u in r.json().get("result", []):
        last = max(last, u["update_id"])
        m = u.get("message") or {}
        raw = (m.get("text") or m.get("caption") or "").strip()
        photo, video, doc = m.get("photo"), m.get("video"), m.get("document") or {}
        image_id = photo[-1]["file_id"] if photo else (doc.get("file_id") if str(doc.get("mime_type", "")).startswith("image/") else None)
        if str((m.get("chat") or {}).get("id")) != chat or raw.startswith("/"):
            continue                          # only you
        use = bool(use_rx.search(raw))
        text = use_rx.sub("", raw).strip()
        if len(text) < 25 and not image_id:
            continue                          # real text, or a screenshot
        link = re.search(r"https?://\S+", text)
        entry = {"title": text.split("\n")[0][:140] if text else f"Screenshot tip {u['update_id']}",
                 "url": link.group(0) if link else f"tip://{u['update_id']}",
                 "text": text,
                 "published": dt.datetime.fromtimestamp(m.get("date", 0), dt.timezone.utc),
                 "force": True, "tip_id": u["update_id"]}
        try:
            if image_id:
                data, ext = _tg_file(tok, image_id)
                entry["image"] = data         # read by the AI
                if use:
                    entry["photo_url"] = _store(sb, data, f"tip-{u['update_id']}.{ext}", "image/png" if ext == "png" else "image/jpeg")
            elif video and use and (video.get("file_size") or 0) < 19_000_000:
                data, ext = _tg_file(tok, video["file_id"])
                entry["video_url"] = _store(sb, data, f"tip-{u['update_id']}.{ext}", "video/mp4")
        except Exception as ex:
            print(f"[tips] attachment skipped: {ex}")
        ids.append(u["update_id"])
        out.append(entry)
    _TIPS.update(source=s, ids=ids, last=last)
    return out


def confirm_tips(sb, handled, failed):
    """Tells Telegram which tips are finished. A tip that failed stays in line and is tried again, up to three times.
    A tip that has not had its turn yet simply waits, so a busy AI or an empty quota never loses one."""
    s = _TIPS["source"]
    if not s:
        return
    state = dict(s.get("state") or {})
    tries = {str(k): v for k, v in (state.get("tries") or {}).items()}
    keep = []
    for uid in _TIPS["ids"]:
        if uid in handled:
            tries.pop(str(uid), None)
        elif uid in failed:
            tries[str(uid)] = tries.get(str(uid), 0) + 1
            if tries[str(uid)] >= 3:
                tries.pop(str(uid), None)
                notify("⚠️ I gave up on one of your tips after three tries. Please send it again.")
            else:
                keep.append(uid)
        else:
            keep.append(uid)
    sb.table("sources").update({"state": {**state, "offset": min(keep) if keep else _TIPS["last"] + 1, "tries": tries}}).eq("id", s["id"]).execute()
    _TIPS["source"] = None


def fetch_trends(s):
    """Google Trends 'trending now' for Kenya: what people are searching right now, with the news behind it."""
    r = requests.get(s["url"], headers=UA, timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.content)

    def local(el):
        return el.tag.split("}")[-1]

    def grab(el, name):
        for ch in el.iter():
            if local(ch) == name and (ch.text or "").strip():
                return ch.text.strip()
        return ""

    out = []
    for item in root.iter("item"):
        term = (item.findtext("title") or "").strip()
        news = [n for n in item.iter() if local(n) == "news_item"]
        if not term or not news:
            continue
        heads = " ".join(f"{grab(n, 'news_item_source')}: {grab(n, 'news_item_title')}. {grab(n, 'news_item_snippet')}"
                         for n in news[:3])
        try:
            pub = parsedate_to_datetime(item.findtext("pubDate"))
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=dt.timezone.utc)
        except Exception:
            pub = dt.datetime.now(dt.timezone.utc)
        out.append({"title": f"Trending in Kenya: {term}",
                    "url": grab(news[0], "news_item_url") or (item.findtext("link") or ""),
                    "text": _clean(f"Trending search in Kenya right now: {term} ({grab(item, 'approx_traffic') or 'many'} searches). {heads}"),
                    "published": pub})
    return [o for o in out if o["url"]]


def fetch_youtube(s, sb):
    """New uploads from a YouTube channel through YouTube's own public feed. Add a channel link or @handle in Sources."""
    state = s.get("state") or {}
    cid = state.get("channel_id")
    if not cid:
        m = re.search(r"channel/(UC[\w-]{22})", s["url"])
        if not m:
            page = requests.get(s["url"], headers={**UA, "Accept-Language": "en"}, timeout=30)
            page.raise_for_status()
            m = (re.search(r"feeds/videos\.xml\?channel_id=(UC[\w-]{22})", page.text)
                 or re.search(r'"(?:channelId|externalId)":"(UC[\w-]{22})"', page.text))
        if not m:
            raise RuntimeError("could not find the channel id, paste the full channel link")
        cid = m.group(1)
        sb.table("sources").update({"state": {**state, "channel_id": cid}}).eq("id", s["id"]).execute()
    feed = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}", request_headers=UA)
    out = []
    for e in feed.entries[:15]:
        pub = dt.datetime(*e.published_parsed[:6], tzinfo=dt.timezone.utc) if getattr(e, "published_parsed", None) else None
        desc = _clean(e.get("summary") or e.get("media_description") or "")
        out.append({"title": e.get("title", ""), "url": e.get("link"), "published": pub,
                    "text": f"New YouTube video from {s['name']}: {e.get('title', '')}. {desc[:700]}"})
    return [o for o in out if o["url"]]


def fetch_source(s, sb):
    if s["type"] == "watch":
        return fetch_watch(s, sb)
    if s["type"] == "tips":
        return fetch_tips(s, sb)
    if s["type"] == "trends":
        return fetch_trends(s)
    if s["type"] == "youtube":
        return fetch_youtube(s, sb)
    return fetch_rss(s)
