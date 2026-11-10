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
MAX_AI = int(os.getenv("MAX_AI_PER_RUN") or 10)
PENDING_CAP = int(os.getenv("PENDING_CAP") or 25)   # stop drafting when this many items wait for review
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
    problems = []

    cands, ok_sources = [], 0
    for s in srcs:
        try:
            entries = fetch_source(s, sb)
            if not entries and s["type"] == "rss":
                raise RuntimeError("no stories found, check the feed address")
            ok_sources += 1
            for e in entries:
                if e["published"] and now - e["published"] > dt.timedelta(days=3):
                    continue
                cands.append({**e, "source": s})
        except Exception as ex:
            print(f"[fetch] {s['name']}: {ex}")
            problems.append(f"{s['name']}: {str(ex)[:90]}")

    # dedupe: same URL already stored, or a near-identical headline from the last 3 days
    urls = list({c["url"] for c in cands})
    known = set()
    for i in range(0, len(urls), 100):
        rows = sb.table("items").select("source_url").in_("source_url", urls[i:i + 100]).execute().data
        known |= {r["source_url"] for r in rows}
    since = (now - dt.timedelta(days=3)).isoformat()
    recent = [r["original_title"] or "" for r in
              sb.table("items").select("original_title").gte("fetched_at", since).execute().data]

    scored, fresh = [], 0
    for c in cands:
        if c["url"] in known:
            continue
        known.add(c["url"])
        title = c["title"].lower()
        if any(difflib.SequenceMatcher(None, title, r.lower()).ratio() > 0.85 for r in recent):
            continue
        recent.append(c["title"])
        fresh += 1
        sc, topic, hint = score(f"{c['title']} {c['text'][:600]}", c["source"]["trust_level"], c["published"])
        if c.get("force"):                    # a tip you sent yourself always gets drafted, near the top
            sc, topic = max(sc, 60) + 15, (topic if topic != "OTHER" else "TIP")
        if sc >= MIN_SCORE:
            scored.append((sc, topic, hint, c))
    scored.sort(key=lambda x: -x[0])

    pending = sb.table("items").select("id", count="exact").eq("status", "pending").execute().count or 0
    budget = max(0, min(MAX_AI, PENDING_CAP - pending))
    new, ai_failed, skipped = [], 0, 0
    for sc, topic, hint, c in scored[:budget]:
        if ai_failed >= 3 and not new:
            problems.append("Stopped early: the AI keeps failing")
            break
        s = c["source"]
        try:
            r = rewrite(c["title"], c["text"], s["name"], s["trust_level"], topic, hint)
        except Exception as ex:
            ai_failed += 1
            print(f"[rewrite] {c['url']}: {ex}")
            if len(problems) < 8:
                problems.append(f"AI: {str(ex)[:140]}")
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
            if len(problems) < 8:
                problems.append(f"Saving to Supabase: {str(ex)[:120]}")
            continue
        if r["skip"]:
            skipped += 1
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

    summary = (f"Fetch report\nSources: {ok_sources} ok, {len(srcs) - ok_sources} failed\n"
               f"Stories seen: {len(cands)}, new: {fresh}, matched topics: {len(scored)}\n"
               f"Drafts saved: {len(new)}, skipped by the AI: {skipped}, AI errors: {ai_failed}\n"
               f"Waiting for review: {pending + len(new)}")
    if problems:
        summary += "\nProblems:\n- " + "\n- ".join(problems[:8])
    print(summary)
    # A manual run always reports. A scheduled run reports only when it looks broken.
    manual = os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"
    broken = ok_sources == 0 or (ai_failed and not new)
    if manual or broken or os.getenv("FETCH_REPORT") == "always":
        notify(summary)


if __name__ == "__main__":
    main()
