import os
import time
import difflib
import datetime as dt
from supabase import create_client
from sources import seed_sources, fetch_source
from scorer import score
from rewriter import rewrite
from render_image import render_card, upload_media
from notifier import notify

MIN_SCORE = int(os.getenv("MIN_SCORE") or 40)
MAX_AI = int(os.getenv("MAX_AI_PER_RUN") or 15)
NOTIFY_MIN = int(os.getenv("NOTIFY_MIN") or 70)
ADMIN_URL = os.getenv("ADMIN_URL") or ""
UTC = dt.timezone.utc


def main():
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    srcs = sb.table("sources").select("*").eq("active", True).execute().data
    if not srcs:
        seed_sources(sb)
        srcs = sb.table("sources").select("*").eq("active", True).execute().data
    now = dt.datetime.now(UTC)

    cands = []
    for s in srcs:
        try:
            for e in fetch_source(s, sb):
                if e["published"] and now - e["published"] > dt.timedelta(days=3):
                    continue
                cands.append({**e, "source": s})
        except Exception as ex:
            print(f"[fetch] {s['name']}: {ex}")

    # dedupe: same URL already stored, or a near-identical headline from the last 3 days
    urls = list({c["url"] for c in cands})
    known = set()
    for i in range(0, len(urls), 100):
        rows = sb.table("items").select("source_url").in_("source_url", urls[i:i + 100]).execute().data
        known |= {r["source_url"] for r in rows}
    since = (now - dt.timedelta(days=3)).isoformat()
    recent = [r["original_title"] or "" for r in
              sb.table("items").select("original_title").gte("fetched_at", since).execute().data]

    scored = []
    for c in cands:
        if c["url"] in known:
            continue
        known.add(c["url"])
        title = c["title"].lower()
        if any(difflib.SequenceMatcher(None, title, r.lower()).ratio() > 0.85 for r in recent):
            continue
        recent.append(c["title"])
        sc, topic, hint = score(f"{c['title']} {c['text'][:600]}", c["source"]["trust_level"], c["published"])
        if sc >= MIN_SCORE:
            scored.append((sc, topic, hint, c))
    scored.sort(key=lambda x: -x[0])

    new = []
    for sc, topic, hint, c in scored[:MAX_AI]:
        s = c["source"]
        try:
            r = rewrite(c["title"], c["text"], s["name"], s["trust_level"], topic, hint)
        except Exception as ex:
            print(f"[rewrite] {c['url']}: {ex}")
            continue
        row = {"source_id": s["id"], "source_name": s["name"], "source_url": c["url"],
               "original_title": c["title"], "original_text": c["text"][:6000], "topic": r["topic"]}
        if r["skip"]:
            row.update(status="rejected", note=r["skip_reason"] or "Skipped by the editor AI")
        else:
            row.update(claim_status=r["claim_status"], risk=r["risk"],
                       priority_score=max(0, min(100, sc + r["priority_adjust"])),
                       headline=r["headline"], rewritten_text=r["rewritten_text"], caption=r["caption"],
                       hashtags=r["hashtags"], suggested_format=r["suggested_format"],
                       media_suggestion=r["media_suggestion"], deadline=r["deadline"], slides=r["slides"])
        try:
            row["id"] = sb.table("items").insert(row).execute().data[0]["id"]
        except Exception as ex:
            print(f"[insert] {c['url']}: {ex}")
            continue
        if r["skip"]:
            continue
        try:   # preview image; it is rendered again from your edited text when you publish
            kind = "story" if row["suggested_format"] in ("story", "reel") else "feed"
            jpg = render_card(row["headline"], row["rewritten_text"], row["claim_status"], kind)
            url = upload_media(sb, jpg, f"{row['id']}-preview-{int(time.time())}.jpg")
            sb.table("items").update({"media_url": url}).eq("id", row["id"]).execute()
        except Exception as ex:
            print(f"[preview] {row['id']}: {ex}")
        new.append(row)

    hot = [r for r in new if r["priority_score"] >= NOTIFY_MIN]
    for r in hot:
        link = f"{ADMIN_URL}#item={r['id']}" if ADMIN_URL else ""
        notify(f"🔔 {r['priority_score']} | {r['topic']} | {r['claim_status']}\n{r['headline']}\n"
               f"Suggested format: {r['suggested_format']}", link)
    rest = len(new) - len(hot)
    if rest:
        notify(f"📥 {rest} more item(s) waiting for review", ADMIN_URL)
    print(f"done: {len(new)} new, {len(hot)} urgent")


if __name__ == "__main__":
    main()
