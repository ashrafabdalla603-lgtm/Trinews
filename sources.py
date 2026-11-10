import os
import re
from urllib.parse import urljoin
import datetime as dt
import feedparser
import requests
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


def fetch_tips(s, sb):
    """Messages you send to your Tri News Alerts bot become story tips. This is the safe way to use gossip
    pages we cannot read ourselves: paste the post text, start with the page name."""
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), str(os.getenv("TELEGRAM_CHAT_ID") or "")
    if not (tok and chat):
        return []
    offset = (s.get("state") or {}).get("offset", 0)
    r = requests.get(f"https://api.telegram.org/bot{tok}/getUpdates",
                     params={"offset": offset, "timeout": 0}, timeout=20)
    r.raise_for_status()
    out, last = [], offset - 1
    for u in r.json().get("result", []):
        last = max(last, u["update_id"])
        m = u.get("message") or {}
        text = (m.get("text") or m.get("caption") or "").strip()
        if str((m.get("chat") or {}).get("id")) != chat or text.startswith("/") or len(text) < 25:
            continue                          # only you, only real text
        link = re.search(r"https?://\S+", text)
        out.append({"title": text.split("\n")[0][:140],
                    "url": link.group(0) if link else f"tip://{u['update_id']}",
                    "text": text,
                    "published": dt.datetime.fromtimestamp(m.get("date", 0), dt.timezone.utc),
                    "force": True})
    if last >= offset:
        sb.table("sources").update({"state": {"offset": last + 1}}).eq("id", s["id"]).execute()
    return out


def fetch_source(s, sb):
    if s["type"] == "watch":
        return fetch_watch(s, sb)
    if s["type"] == "tips":
        return fetch_tips(s, sb)
    return fetch_rss(s)
