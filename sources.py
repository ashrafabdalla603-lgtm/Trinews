from urllib.parse import urljoin
import datetime as dt
import feedparser
import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (compatible; NewsdeskBot/1.0)"}

# (name, url, type, category, trust 1-5)
# 'watch' = official pages with no RSS: we flag NEW links on the page. Point each at the
# site's news/announcements page when you can (less noise).
# The RSS URLs are best guesses. Open each in a browser, then fix or disable it in the
# `sources` table. A dead feed only logs an error; it never stops the run.
SEED = [
    ("KNEC", "https://www.knec.ac.ke/", "watch", "official", 5),
    ("HELB", "https://www.helb.co.ke/", "watch", "official", 5),
    ("KUCCPS", "https://www.kuccps.net/", "watch", "official", 5),
    ("KRA", "https://www.kra.go.ke/", "watch", "official", 5),
    ("eCitizen", "https://www.ecitizen.go.ke/", "watch", "official", 5),
    ("TSC", "https://www.tsc.go.ke/", "watch", "official", 5),
    ("NTSA", "https://ntsa.go.ke/", "watch", "official", 5),
    ("Capital FM", "https://www.capitalfm.co.ke/news/feed/", "rss", "news", 3),
    ("Kenyans.co.ke", "https://www.kenyans.co.ke/feeds/news", "rss", "news", 3),
    ("The Star", "https://www.the-star.co.ke/rss", "rss", "news", 3),
    ("Tuko", "https://www.tuko.co.ke/rss/all.rss", "rss", "celebrity", 2),
    ("Pulse Kenya", "https://www.pulselive.co.ke/rss", "rss", "celebrity", 2),
    ("Mpasho", "https://mpasho.co.ke/feed/", "rss", "celebrity", 2),
    ("Capital FM Lifestyle", "https://www.capitalfm.co.ke/lifestyle/feed/", "rss", "entertainment", 3),
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


def fetch_source(s, sb):
    return fetch_watch(s, sb) if s["type"] == "watch" else fetch_rss(s)
