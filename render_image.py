import io
import os
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFont
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


def render_card(headline, body, status, kind="feed", step=""):
    """Branded JPEG. Confirmed items get no badge; unconfirmed and speculation are labelled.
    Every card carries the Tri News mark and the TriBridge Services endorsement."""
    W, H = SIZES[kind]
    pad = 80
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 16], fill=ACCENT)
    x = pad
    mk = _asset("trinews-mark-white.png", 92)
    if mk:
        img.paste(mk, (pad, 56), mk)
        x = pad + mk.width + 22
    d.text((x, 74), BRAND, font=_font(FONT_BOLD, 50), fill="#FFFFFF")
    if step:
        sf = _font(FONT_BOLD, 34)
        d.text((W - pad - d.textlength(step, font=sf), 82), step, font=sf, fill="#A9BCB2")
    y = 250
    if status in BADGE:
        label, col = BADGE[status]
        bf = _font(FONT_BOLD, 34)
        bw = d.textlength(label, font=bf) + 44
        d.rounded_rectangle([pad, y, pad + bw, y + 62], 31, fill=col)
        d.text((pad + 22, y + 12), label, font=bf, fill="white")
        y += 100
    else:
        y += 20
    for size in (96, 84, 72, 62, 54):
        f = _font(FONT_HEAD, size)
        lines = _wrap(d, headline or "", f, W - 2 * pad)
        if len(lines) <= 6:
            break
    for ln in lines:
        d.text((pad, y), ln, font=f, fill="white")
        y += int(size * 1.22)
    if body:
        y += 36
        bfont = _font(FONT_REG, 40)
        limit = 420 if kind == "feed" else 300
        txt = body if len(body) <= limit else body[:limit].rsplit(" ", 1)[0] + "…"
        for ln in _wrap(d, txt, bfont, W - 2 * pad)[:11]:
            d.text((pad, y), ln, font=bfont, fill="#C9D6CF")
            y += 56
    fy = H - 130
    d.line([pad, fy - 26, W - pad, fy - 26], fill="#25483B", width=2)
    d.text((pad, fy), HANDLE, font=_font(FONT_BOLD, 34), fill="#A9BCB2")
    tf = _font(FONT_REG, 28)
    label = f"A {PARENT} company"
    tw = d.textlength(label, font=tf)
    right = W - pad
    d.text((right - tw, fy + 8), label, font=tf, fill="#A9BCB2")
    pm = _asset("tribridge-mark.png", 64)
    if pm:
        img.paste(pm, (int(right - tw - 18 - pm.width), fy - 12), pm)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def make_reel(jpg, seconds=8):
    """v1 Reel = the story card as a short silent video (needs ffmpeg)."""
    with tempfile.TemporaryDirectory() as d:
        src, out = os.path.join(d, "a.jpg"), os.path.join(d, "a.mp4")
        with open(src, "wb") as fh:
            fh.write(jpg)
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", src, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
             "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
             "-vf", "scale=1080:1920", "-c:a", "aac", "-shortest", out],
            check=True, capture_output=True)
        with open(out, "rb") as fh:
            return fh.read()


def upload_media(sb, data, name, ctype="image/jpeg"):
    bucket = sb.storage.from_("media")
    bucket.upload(name, data, {"content-type": ctype, "upsert": "true"})
    return bucket.get_public_url(name)
