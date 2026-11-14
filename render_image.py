import io
import os
import subprocess
import tempfile
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps
from config import BRAND, HANDLE, PARENT, BG, ACCENT

SIZES = {"feed": (1080, 1350), "story": (1080, 1920)}
BADGE = {"unverified": ("Unconfirmed", "#B7791F"), "speculation": ("Speculation", "#7C3AED")}
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_D, _L = "/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/truetype/liberation/"


def _pick(env, *paths):
    for p in (os.getenv(env), *paths):
        if p and os.path.exists(p):
            return p
    return None


FONT_HEAD = _pick("FONT_HEAD", _L + "LiberationSerif-Bold.ttf", _D + "DejaVuSerif-Bold.ttf", _D + "DejaVuSans-Bold.ttf")
FONT_BOLD = _pick("FONT_BOLD", _L + "LiberationSans-Bold.ttf", _D + "DejaVuSans-Bold.ttf")
FONT_REG = _pick("FONT_REG", _L + "LiberationSans-Regular.ttf", _D + "DejaVuSans.ttf")


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except (OSError, TypeError):
        return ImageFont.load_default(size=size)


def _asset(name, height):
    p = os.path.join(ASSETS, name)
    if not os.path.exists(p):
        return None
    im = Image.open(p).convert("RGBA")
    return im.resize((max(1, round(im.width * height / im.height)), height), Image.LANCZOS)


def _wrap(d, text, font, width):
    lines, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if d.textlength(t, font=font) <= width:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])


def render_card(headline, body, status, kind="feed", step="", photo=None, overlay=False):
    """Branded card. With a photo it becomes a full-bleed photo with a dark fade under the text.
    overlay=True returns a transparent PNG of the same design, to lay on top of a video."""
    W, H = SIZES[kind]
    pad = 80
    bg = ImageColor.getrgb(BG)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0) if overlay else bg + (255,))
    if photo:
        try:
            img.alpha_composite(ImageOps.fit(ImageOps.exif_transpose(Image.open(io.BytesIO(photo))).convert("RGBA"), (W, H), Image.LANCZOS))
        except Exception as ex:
            print(f"[render] photo ignored: {ex}")
            photo = None
    covered = bool(photo) or overlay
    if covered:                               # fade into the brand colour so the text stays readable
        shade = Image.new("L", (W, H), 0)
        sd = ImageDraw.Draw(shade)
        for y in range(H):
            t = max(0.0, (y - H * 0.25) / (H * 0.75))
            top = max(0.0, 1 - y / 300) * 0.55
            sd.line([(0, y), (W, y)], fill=int(255 * min(1.0, max(top, 0.93 * t ** 0.85))))
        fade = Image.new("RGBA", (W, H), bg + (0,))
        fade.putalpha(shade)
        img = Image.alpha_composite(img, fade)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 16], fill=ACCENT)
    x = pad
    mk = _asset("trinews-mark-white.png", 92)
    if mk:
        img.alpha_composite(mk, (pad, 56))
        x = pad + mk.width + 22
    d.text((x, 74), BRAND, font=_font(FONT_BOLD, 50), fill="#FFFFFF")
    if step:
        sf = _font(FONT_BOLD, 34)
        d.text((W - pad - d.textlength(step, font=sf), 82), step, font=sf, fill="#E5ECE8")

    badge = None   # the claim tag is private to you: it is never printed on a post
    size, lines = 96, []
    for size in (96, 84, 72, 62, 54):
        hf = _font(FONT_HEAD, size)
        lines = _wrap(d, headline or "", hf, W - 2 * pad)
        if len(lines) <= 6:
            break
    bfont = _font(FONT_REG, 40)
    blines = []
    if body:
        limit = (200 if covered else 420) if kind == "feed" else (160 if covered else 300)
        txt = body if len(body) <= limit else body[:limit].rsplit(" ", 1)[0] + "…"
        blines = _wrap(d, txt, bfont, W - 2 * pad)[: (4 if covered else 11)]
    block = (100 if badge else 20) + len(lines) * int(size * 1.22) + ((36 + len(blines) * 56) if blines else 0)
    y = max(250, H - 200 - block) if covered else 250
    if badge:
        label, col = badge
        bf = _font(FONT_BOLD, 34)
        bw = d.textlength(label, font=bf) + 44
        d.rounded_rectangle([pad, y, pad + bw, y + 62], 31, fill=col)
        d.text((pad + 22, y + 12), label, font=bf, fill="white")
        y += 100
    else:
        y += 20
    for ln in lines:
        d.text((pad, y), ln, font=hf, fill="white")
        y += int(size * 1.22)
    if blines:
        y += 36
        for ln in blines:
            d.text((pad, y), ln, font=bfont, fill="#E5ECE8" if covered else "#C9D6CF")
            y += 56
    fy = H - 130
    d.line([pad, fy - 26, W - pad, fy - 26], fill="#4A6A5C" if covered else "#25483B", width=2)
    d.text((pad, fy), HANDLE, font=_font(FONT_BOLD, 34), fill="#E5ECE8" if covered else "#A9BCB2")
    tf = _font(FONT_REG, 28)
    label = f"A {PARENT} company"
    tw = d.textlength(label, font=tf)
    right = W - pad
    d.text((right - tw, fy + 8), label, font=tf, fill="#E5ECE8" if covered else "#A9BCB2")
    pm = _asset("tribridge-mark.png", 64)
    if pm:
        img.alpha_composite(pm, (int(right - tw - 18 - pm.width), fy - 12))
    buf = io.BytesIO()
    if overlay:
        img.save(buf, "PNG")
    else:
        img.convert("RGB").save(buf, "JPEG", quality=95, subsampling=0, optimize=True)
    return buf.getvalue()


def make_reel(jpg, seconds=8):
    """Reel from a still card: the story card as a short silent video (needs ffmpeg)."""
    with tempfile.TemporaryDirectory() as d:
        src, out = os.path.join(d, "a.jpg"), os.path.join(d, "a.mp4")
        with open(src, "wb") as fh:
            fh.write(jpg)
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", src, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
             "-t", str(seconds), "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart",
             "-vf", "scale=1080:1920", "-c:a", "aac", "-b:a", "128k", "-shortest", out],
            check=True, capture_output=True)
        with open(out, "rb") as fh:
            return fh.read()


def make_video(clip, overlay_png, seconds=10, loop=True):
    """Lays the branded overlay on a video, cropped to 9:16. Short stock clips loop; your own video plays through
    and keeps its sound. Needs ffmpeg."""
    with tempfile.TemporaryDirectory() as d:
        src, ov, out = (os.path.join(d, n) for n in ("in.mp4", "ov.png", "out.mp4"))
        with open(src, "wb") as fh:
            fh.write(clip)
        with open(ov, "wb") as fh:
            fh.write(overlay_png)
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                                "-of", "csv=p=0", src], capture_output=True, text=True)
        has_audio = bool(probe.stdout.strip())
        cmd = ["ffmpeg", "-y"] + (["-stream_loop", "-1"] if loop else []) + ["-i", src, "-i", ov]
        if not has_audio:
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        cmd += ["-t", str(seconds), "-filter_complex",
                "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[bg];"
                "[bg][1:v]overlay=0:0:format=auto[v]",
                "-map", "[v]", "-map", "0:a:0" if has_audio else "2:a:0",
                "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "128k", "-shortest", out]
        subprocess.run(cmd, check=True, capture_output=True)
        with open(out, "rb") as fh:
            return fh.read()


def raw_image(photo, kind="feed"):
    """Your picture exactly as it is: upright, never stretched, never cropped. Only when Instagram would refuse its
    shape is it centred on a soft blurred copy of itself."""
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(photo))).convert("RGB")
    w, h = im.size
    ratio = w / h
    if kind == "story":
        ok, size = abs(ratio - 9 / 16) < 0.02, (1080, 1920)
    else:
        ok, size = 0.8 <= ratio <= 1.91, ((1080, 1350) if ratio < 0.8 else (1080, 566))
    if ok:
        out = im if w <= 1440 else im.resize((1440, round(h * 1440 / w)), Image.LANCZOS)
    else:
        cw, ch = size
        out = ImageOps.fit(im, (cw, ch), Image.LANCZOS).filter(ImageFilter.GaussianBlur(40))
        scale = min(cw / w, ch / h)
        fg = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
        out.paste(fg, ((cw - fg.width) // 2, (ch - fg.height) // 2))
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=95, subsampling=0, optimize=True)
    return buf.getvalue()


def make_video_raw(clip):
    """Your video as it is: same shape, never cropped, only converted to the H.264 MP4 Instagram accepts."""
    with tempfile.TemporaryDirectory() as d:
        src, out = os.path.join(d, "in.mp4"), os.path.join(d, "out.mp4")
        with open(src, "wb") as fh:
            fh.write(clip)
        subprocess.run(
            ["ffmpeg", "-y", "-i", src, "-t", "90", "-vf", "scale='min(1080,iw)':-2", "-c:v", "libx264", "-crf", "18",
             "-preset", "medium", "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart",
             "-c:a", "aac", "-b:a", "128k", out],
            check=True, capture_output=True)
        with open(out, "rb") as fh:
            return fh.read()


def upload_media(sb, data, name, ctype="image/jpeg"):
    bucket = sb.storage.from_("media")
    bucket.upload(name, data, {"content-type": ctype, "upsert": "true"})
    return bucket.get_public_url(name)
