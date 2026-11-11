import os
import time
import difflib
import datetime as dt
from supabase import create_client
from sources import seed_sources, fetch_source
from scorer import score
from rewriter import rewrite
from render_image import render_card, upload_media
from media import stock_photo, stock_video, download
from notifier import notify

MIN_SCORE = int(os.getenv("MIN_SCORE") or 40)
MAX_AI = int(os.getenv("MAX_AI_PER_RUN") or 10)
PENDING_CAP = int(os.getenv("PENDING_CAP") or 25)   # stop drafting when this many items wait for review
NOTIFY_MIN = int(os.getenv("NOTIFY_MIN") or 70)
MAX_AGE = int(os.getenv("MAX_AGE_HOURS") or 24)   # older stories are ignored
PENDING_TTL = 36   # hours: drafts you never reviewed expire, so stale news cannot clog the queue
ONLY_TIPS = os.getenv("ONLY_TIPS") == "1"           # the 5-minute run only reads your Telegram tips
ADMIN_URL = os.getenv("ADMIN_URL") or ""
UTC = dt.timezone.utc


AUTO_SKIP = {"HOT-TOPIC", "CELEBRITY", "RELATIONSHIPS", "VIRAL"}   # never posted without you


def load_settings(sb):
    cfg = {"auto_publish": "off", "auto_min_score": "70", "auto_min_trust": "3",
           "auto_daily_cap": "6", "auto_delay_min": "10"}
    try:
        for r in sb.table("settings").select("key,value").execute().data:
            cfg[r["key"]] = str(r["value"])
    except Exception as ex:
        print(f"[settings] using the defaults (did you run the 004 SQL?): {ex}")
    return cfg


def auto_count(sb, now):
    try:
        since = (now - dt.timedelta(hours=24)).isoformat()
        return sb.table("items").select("id", count="exact").eq("auto_approved", True).gte("approved_at", since).execute().count or 0
    except Exception:
        return 0


def auto_ok(cfg, row, source, c, label):
    """Only confirmed, low-risk, well-sourced stories qualify. Your own tips and touchy topics never do."""
    try:
        return (not c.get("force") and label not in AUTO_SKIP
                and row.get("claim_status") == "confirmed" and row.get("risk") == "low"
                and row.get("priority_score", 0) >= int(cfg["auto_min_score"])
                and source["trust_level"] >= int(cfg["auto_min_trust"]))
    except Exception:
        return False


def note_once(sb, now, key, hours, text, link=""):
    """Sends a Telegram notice at most once every `hours` hours (remembered in the settings table)."""
    try:
        rows = sb.table("settings").select("value").eq("key", key).execute().data
        last = dt.datetime.fromisoformat(rows[0]["value"]) if rows else None
        if last and now - last < dt.timedelta(hours=hours):
            return
        notify(text, link)
        sb.table("settings").upsert({"key": key, "value": now.isoformat()}, on_conflict="key").execute()
    except Exception as ex:
        print(f"[notice] {ex}")


def main():
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    srcs = sb.table("sources").select("*").eq("active", True).execute().data
    if not srcs:
        seed_sources(sb)
        srcs = sb.table("sources").select("*").eq("active", True).execute().data
    if ONLY_TIPS:
        srcs = [x for x in srcs if x["type"] == "tips"]
    now = dt.datetime.now(UTC)
    problems = []
    cfg = load_settings(sb)
    try:    # unreviewed drafts expire, which also keeps old news from being posted
        cutoff = (now - dt.timedelta(hours=PENDING_TTL)).isoformat()
        sb.table("items").update({"status": "rejected", "note": "Expired: not reviewed in time"}).eq("status", "pending").lt("fetched_at", cutoff).execute()
    except Exception as ex:
        print(f"[expire] {ex}")
    auto_used = auto_count(sb, now) if cfg["auto_publish"] == "on" else 0
    auto_ids = set()

    cands, ok_sources = [], 0
    for s in srcs:
        try:
            entries = fetch_source(s, sb)
            if not entries and s["type"] == "rss":
                raise RuntimeError("no stories found, check the feed address")
            ok_sources += 1
            for e in entries:
                if e["published"] and now - e["published"] > dt.timedelta(hours=MAX_AGE):
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
    if scored and budget == 0 and not ONLY_TIPS:
        note_once(sb, now, "last_full_notice", 6,
                  f"⏸ Drafting is paused: {pending} items are waiting for review. Approve or reject some and it carries on.", ADMIN_URL)
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
        extra = {"source_published": c["published"].isoformat() if c["published"] else None,
                 "image_query": r["image_query"] or None,
                 "audio_idea": r["audio_idea"] or None,
                 "photo_url": c.get("photo_url"), "video_url": c.get("video_url")}
        photo = None
        try:    # a photo or clip for the post: your own (sent with a tip) or a free stock one from Pexels
            if extra["photo_url"]:
                photo = download(extra["photo_url"])
            elif not extra["video_url"] and r["image_query"] and os.getenv("PEXELS_API_KEY"):
                credit = ""
                if row["suggested_format"] == "reel":
                    found = stock_video(r["image_query"])
                    if found:
                        extra["video_url"], photo, credit = found[0], found[1], found[2]
                else:
                    photo, credit = stock_photo(r["image_query"])
                if photo:
                    extra["photo_url"] = upload_media(sb, photo, f"{row['id']}-stock-{int(time.time())}.jpg")
                if credit:
                    extra["photo_credit"] = credit
        except Exception as ex:
            print(f"[media] {row['id']}: {ex}")
        try:
            sb.table("items").update({k: v for k, v in extra.items() if v is not None}).eq("id", row["id"]).execute()
        except Exception as ex:
            print(f"[extras] could not save the media fields (did you run the new SQL?): {ex}")
        try:   # preview image; it is rendered again from your edited text when you publish
            kind = "story" if row["suggested_format"] in ("story", "reel") else "feed"
            jpg = render_card(row["headline"], row["rewritten_text"], row["claim_status"], kind, photo=photo)
            url = upload_media(sb, jpg, f"{row['id']}-preview-{int(time.time())}.jpg")
            sb.table("items").update({"media_url": url}).eq("id", row["id"]).execute()
        except Exception as ex:
            print(f"[preview] {row['id']}: {ex}")
        if cfg["auto_publish"] == "on" and auto_used < int(cfg["auto_daily_cap"]) and auto_ok(cfg, row, s, c, topic):
            delay = max(1, int(cfg["auto_delay_min"]))
            try:
                stamp = dt.datetime.now(UTC)
                sb.table("items").update({"status": "approved", "auto_approved": True, "approved_at": stamp.isoformat(),
                                          "publish_after": (stamp + dt.timedelta(minutes=delay)).isoformat()}).eq("id", row["id"]).execute()
                auto_used += 1
                auto_ids.add(row["id"])
                notify(f"🤖 Auto-approved. Posts in about {delay} min unless you pull it back:\n{row['headline']}",
                       f"{ADMIN_URL}#item={row['id']}" if ADMIN_URL else "")
            except Exception as ex:
                print(f"[auto] could not auto-approve: {ex}")
        new.append(row)

    hot = [r for r in new if r["priority_score"] >= NOTIFY_MIN and r["id"] not in auto_ids]
    for r in hot:
        link = f"{ADMIN_URL}#item={r['id']}" if ADMIN_URL else ""
        notify(f"🔔 {r['priority_score']} | {r['topic']} | {r['claim_status']}\n{r['headline']}\n"
               f"Suggested format: {r['suggested_format']}", link)
    rest = len(new) - len(hot) - len(auto_ids)
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
    broken = (ok_sources == 0 and not ONLY_TIPS) or (ai_failed and not new)
    if manual or broken or os.getenv("FETCH_REPORT") == "always":
        notify(summary)
    if not ONLY_TIPS:       # a daily sign of life: if it ever stops arriving, something is wrong
        note_once(sb, dt.datetime.now(UTC), "last_heartbeat", 24,
                  f"✅ Tri News is running. Waiting for review: {pending + len(new)}. Auto-publish: {cfg['auto_publish']}.", ADMIN_URL)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        notify(f"⚠️ Fetch crashed: {str(ex)[:300]}")
        raise
