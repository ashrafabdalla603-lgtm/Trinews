"""Publishes ONLY rows with status = 'approved' (by you in the app, or by the auto-publish rules you switched on)."""
import os
import time
import datetime as dt
from supabase import create_client
from config import BRAND
from render_image import render_card, make_reel, make_video, upload_media
from media import get_media
from publisher_ig import publish
from notifier import notify, notify_media

MAX = int(os.getenv("MAX_POSTS_PER_RUN") or 2)


def blobs_for(it, fmt, photo=None):
    st, h, body = it["claim_status"], it["headline"] or "", it["rewritten_text"] or ""
    if fmt == "carousel":
        slides = [x for x in (it.get("slides") or []) if str(x).strip()] or [body]
        n = len(slides) + 2
        out = [render_card(h, "", st, "feed", f"1/{n}", photo=photo)]
        out += [render_card(x, "", st, "feed", f"{i}/{n}") for i, x in enumerate(slides, 2)]
        out.append(render_card(f"Follow {BRAND}", f"Source: {it['source_name']}", st, "feed", f"{n}/{n}"))
        return out
    if fmt in ("story", "reel"):
        return [render_card(h, body, st, "story", photo=photo)]
    return [render_card(h, body, st, "feed", photo=photo)]


def main():
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    nowz = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = (sb.table("items").select("*").eq("status", "approved")
            .or_(f"publish_after.is.null,publish_after.lte.{nowz}")     # auto-approved items wait out their delay
            .order("priority_score", desc=True).limit(MAX).execute().data)
    for it in rows:
        # claim the row first so two overlapping runs can never post the same item twice
        if not sb.table("items").update({"status": "publishing"}).eq("id", it["id"]).eq("status", "approved").execute().data:
            continue
        fmt = it["suggested_format"] or "feed"
        chans = it.get("channels") or ["instagram"]
        stamp = int(time.time())
        try:
            photo, video, credit, loop = get_media(it, fmt)
            if video and fmt not in ("reel", "story"):
                fmt = "reel"                      # Instagram publishes video posts as Reels
            blobs = blobs_for(it, fmt, photo)
            vid = None
            if video:
                overlay = render_card(it["headline"] or "", it["rewritten_text"] or "", it["claim_status"], "story", overlay=True)
                clip = make_video(video, overlay, seconds=10 if loop else 60, loop=loop)
                vid = upload_media(sb, clip, f"{it['id']}-{stamp}.mp4", "video/mp4")
            elif fmt == "reel":
                vid = upload_media(sb, make_reel(blobs[0]), f"{it['id']}-{stamp}.mp4", "video/mp4")
            urls = [upload_media(sb, b, f"{it['id']}-{stamp}-{i}.jpg") for i, b in enumerate(blobs)]
            caption = f"{it['caption'] or ''}\n\n{' '.join(it['hashtags'] or [])}".strip()
            if credit:                            # Pexels asks for a credit on its free media
                caption += f"\n\n{'Video' if video else 'Photo'}: {credit}"
            ig_id, note = None, None
            if "manual" in chans:                 # you post it by hand so you can add Instagram's own audio
                notify_media(urls, vid, it["headline"] or "")
                notify("🎧 Post this one by hand so you can add Instagram audio.\n"
                       f"Audio idea: {it.get('audio_idea') or 'a trending sound that fits the mood'}\n\n"
                       f"Caption, tap to copy:\n\n{caption}")
                note = "Sent to Telegram for manual posting"
            elif "instagram" in chans:
                ig_id = publish(fmt, caption, urls, vid)
            sb.table("items").update({
                "status": "published", "ig_media_id": ig_id, "media_url": urls[0], "note": note,
                "published_at": dt.datetime.now(dt.timezone.utc).isoformat()}).eq("id", it["id"]).execute()
            if ig_id:
                notify(f"✅ Posted on Instagram ({fmt}): {it['headline']}")
            if "whatsapp" in chans:   # WhatsApp Channels have no posting API, so you forward this one yourself
                notify(f"📲 WhatsApp post ready. Copy it into your Channel:\n\n*{it['headline']}*\n\n"
                       f"{it['rewritten_text']}\n\n{BRAND}\n\nImage: {urls[0]}" + (f"\nVideo: {vid}" if vid else ""))
        except Exception as ex:
            sb.table("items").update({"status": "failed", "note": str(ex)[:500]}).eq("id", it["id"]).execute()
            notify(f"⚠️ Publish failed: {it['headline']}\n{str(ex)[:300]}")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        notify(f"⚠️ Publish job crashed: {str(ex)[:300]}")
        raise
