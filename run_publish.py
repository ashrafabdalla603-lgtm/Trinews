"""Publishes ONLY rows with status = 'approved'. That status is set by your signed-in admin session."""
import os
import time
import datetime as dt
from supabase import create_client
from config import BRAND
from render_image import render_card, make_reel, upload_media
from publisher_ig import publish
from notifier import notify

MAX = int(os.getenv("MAX_POSTS_PER_RUN") or 2)


def blobs_for(it, fmt):
    st, h, body = it["claim_status"], it["headline"] or "", it["rewritten_text"] or ""
    if fmt == "carousel":
        slides = [x for x in (it.get("slides") or []) if str(x).strip()] or [body]
        n = len(slides) + 2
        out = [render_card(h, "", st, "feed", f"1/{n}")]
        out += [render_card(x, "", st, "feed", f"{i}/{n}") for i, x in enumerate(slides, 2)]
        out.append(render_card(f"Follow {BRAND}", f"Source: {it['source_name']}", st, "feed", f"{n}/{n}"))
        return out
    if fmt in ("story", "reel"):
        return [render_card(h, body, st, "story")]
    return [render_card(h, body, st, "feed")]


def main():
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    rows = (sb.table("items").select("*").eq("status", "approved")
            .order("priority_score", desc=True).limit(MAX).execute().data)
    for it in rows:
        # claim the row first so two overlapping runs can never post the same item twice
        if not sb.table("items").update({"status": "publishing"}).eq("id", it["id"]).eq("status", "approved").execute().data:
            continue
        fmt = it["suggested_format"] or "feed"
        chans = it.get("channels") or ["instagram"]
        stamp = int(time.time())
        try:
            blobs = blobs_for(it, fmt)
            video = None
            if fmt == "reel":
                video = upload_media(sb, make_reel(blobs[0]), f"{it['id']}-{stamp}.mp4", "video/mp4")
            urls = [upload_media(sb, b, f"{it['id']}-{stamp}-{i}.jpg") for i, b in enumerate(blobs)]
            ig_id = None
            if "instagram" in chans:
                caption = f"{it['caption'] or ''}\n\n{' '.join(it['hashtags'] or [])}".strip()
                ig_id = publish(fmt, caption, urls, video)
            sb.table("items").update({
                "status": "published", "ig_media_id": ig_id, "media_url": urls[0],
                "published_at": dt.datetime.now(dt.timezone.utc).isoformat()}).eq("id", it["id"]).execute()
            if ig_id:
                notify(f"✅ Posted on Instagram ({fmt}): {it['headline']}")
            if "whatsapp" in chans:   # WhatsApp Channels have no posting API, so you forward this one yourself
                notify(f"📲 WhatsApp post ready. Copy it into your Channel:\n\n*{it['headline']}*\n\n"
                       f"{it['rewritten_text']}\n\n{BRAND}\n\nImage: {urls[0]}")
        except Exception as ex:
            sb.table("items").update({"status": "failed", "note": str(ex)[:500]}).eq("id", it["id"]).execute()
            notify(f"⚠️ Publish failed: {it['headline']}\n{str(ex)[:300]}")


if __name__ == "__main__":
    main()
