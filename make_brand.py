"""Regenerates every Tri News logo file from code.
Run from the repo root:  python brand/make_brand.py   (needs Pillow)
Change NAME, PARENT or the colours, run it again, and all exports update."""
import os
import sys
import shutil
from PIL import Image, ImageChops, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out")
ASSETS = os.path.join(ROOT, "worker", "assets")
ADMIN = os.path.join(ROOT, "admin")
for p in (OUT, ASSETS, ADMIN):
    os.makedirs(p, exist_ok=True)

NAME, PARENT = "Tri News", "TriBridge Services"
INK, LEAF, MINT, SIGNAL, PAPER, SLATE = "#0A2A1F", "#14804E", "#4FB283", "#FF5A36", "#F3F6F4", "#5F6F78"


def mark(size, bubble=LEAF, bars="#FFFFFF", dot=SIGNAL, S=4):
    """The Tri News mark: message bubble, headline lines, alert dot. Real transparency, no fringe."""
    N = 512 * S

    def r(*v):
        return [x * S for x in v]

    body = Image.new("L", (N, N), 0)
    d = ImageDraw.Draw(body)
    d.rounded_rectangle(r(64, 96, 448, 376), radius=80 * S, fill=255)
    d.polygon(r(243.6, 360, 92, 448, 155.6, 360), fill=255)      # speech-bubble tail
    d.ellipse(r(306, 60, 466, 220), fill=0)                      # ring cut around the dot
    lines = Image.new("L", (N, N), 0)
    d = ImageDraw.Draw(lines)
    for x0, y0, x1, y1 in ((120, 168, 288, 200), (120, 232, 392, 264), (120, 296, 328, 328)):
        d.rounded_rectangle(r(x0, y0, x1, y1), radius=16 * S, fill=255)
    dt = Image.new("L", (N, N), 0)
    ImageDraw.Draw(dt).ellipse(r(328, 82, 444, 198), fill=255)
    base = Image.new("RGB", (N, N), bubble)
    base.paste(Image.new("RGB", (N, N), bars), mask=lines)
    base.paste(Image.new("RGB", (N, N), dot), mask=dt)
    alpha = ImageChops.lighter(ImageChops.lighter(body, lines), dt)
    base = base.resize((size, size), Image.LANCZOS)
    base.putalpha(alpha.resize((size, size), Image.LANCZOS))
    return base


REV = dict(bubble="#FFFFFF", bars=INK)


def on_tile(size, bg, mark_px, rounded=False, **kw):
    if rounded:
        t = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        m = Image.new("L", (size * 4, size * 4), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, size * 4 - 1, size * 4 - 1], radius=int(size * 4 * 0.22), fill=255)
        t.paste(Image.new("RGB", (size, size), bg), mask=m.resize((size, size), Image.LANCZOS))
    else:
        t = Image.new("RGBA", (size, size), bg)
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    layer.paste(mark(mark_px, **kw), ((size - mark_px) // 2, (size - mark_px) // 2 - round(9 * mark_px / 512)))
    return Image.alpha_composite(t, layer)


def key_parent():
    """Cuts the TriBridge logo off its dark background so it can sit on our post images."""
    path = os.path.join(HERE, "source", "tribridge-services-logo.png")
    if not os.path.exists(path):
        return None, None
    src = Image.open(path).convert("RGB")
    bg = src.getpixel((5, 5))
    r, g, b = ImageChops.difference(src, Image.new("RGB", src.size, bg)).split()
    dmax = ImageChops.lighter(ImageChops.lighter(r, g), b)
    alpha = dmax.point(lambda v: 0 if v < 14 else min(255, int((v - 14) * 255 / 76)))
    rgba = src.convert("RGBA")
    rgba.putalpha(alpha)
    k = src.size[0] / 1200

    def part(box, pad=10):
        box = tuple(int(v * k) for v in box)
        x0, y0, x1, y1 = alpha.crop(box).getbbox()
        return rgba.crop((box[0] + x0 - pad, box[1] + y0 - pad, box[0] + x1 + pad, box[1] + y1 + pad))

    return part((380, 60, 820, 335)), part((260, 60, 950, 466))


DEFS = ('<defs><mask id="c" maskUnits="userSpaceOnUse" x="0" y="0" width="512" height="512">'
        '<rect width="512" height="512" fill="#fff"/><circle cx="386" cy="140" r="80" fill="#000"/></mask></defs>')
FONT = "Plus Jakarta Sans, Segoe UI, Arial, sans-serif"


def grp(bubble, bars):
    return (f'<path mask="url(#c)" fill="{bubble}" d="M144 96H368A80 80 0 0 1 448 176V296A80 80 0 0 1 368 376H216L92 448L144 376A80 80 0 0 1 64 296V176A80 80 0 0 1 144 96Z"/>'
            f'<g fill="{bars}"><rect x="120" y="168" width="168" height="32" rx="16"/><rect x="120" y="232" width="272" height="32" rx="16"/><rect x="120" y="296" width="208" height="32" rx="16"/></g>'
            f'<circle cx="386" cy="140" r="58" fill="{SIGNAL}"/>')


def lockup(bubble, bars, tri, news, sub):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 200">{DEFS}'
            f'<g transform="translate(0 8) scale(0.36)">{grp(bubble, bars)}</g>'
            f'<text x="206" y="104" font-family="{FONT}" font-weight="800" font-size="84" letter-spacing="-2">'
            f'<tspan fill="{tri}">Tri</tspan><tspan fill="{news}"> News</tspan></text>'
            f'<text x="210" y="150" font-family="{FONT}" font-weight="600" font-size="26" fill="{sub}">A {PARENT} company</text></svg>')


def write(name, text):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
        fh.write(text)


def sheet():
    sys.path.insert(0, os.path.join(ROOT, "worker"))
    from render_image import render_card, _font, FONT_BOLD, FONT_REG
    W, H = 1600, 1120
    s = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(s)
    d.rounded_rectangle([60, 60, 880, 380], 28, fill="#FFFFFF")
    mk = mark(210)
    s.paste(mk, (100, 115), mk)
    f = _font(FONT_BOLD, 104)
    d.text((350, 124), "Tri", font=f, fill=LEAF)
    d.text((350 + d.textlength("Tri ", font=f), 124), "News", font=f, fill=INK)
    d.text((354, 262), f"A {PARENT} company", font=_font(FONT_REG, 34), fill=SLATE)
    av = Image.open(os.path.join(OUT, "avatar-1080.png")).convert("RGB").resize((340, 340), Image.LANCZOS)
    circ = Image.new("L", (340, 340), 0)
    ImageDraw.Draw(circ).ellipse([0, 0, 339, 339], fill=255)
    s.paste(av, (60, 430), circ)
    ic = Image.open(os.path.join(OUT, "icon-512.png")).convert("RGBA").resize((340, 340), Image.LANCZOS)
    s.paste(ic, (460, 430), ic)
    cf = _font(FONT_REG, 28)
    d.text((60, 790), "Instagram profile", font=cf, fill=SLATE)
    d.text((460, 790), "App icon", font=cf, fill=SLATE)
    d.rounded_rectangle([920, 60, 1540, 520], 28, fill=INK)
    pl = Image.open(os.path.join(OUT, "tribridge-lockup.png")).convert("RGBA") if os.path.exists(os.path.join(OUT, "tribridge-lockup.png")) else None
    if pl:
        w = 480
        pl = pl.resize((w, round(pl.height * w / pl.width)), Image.LANCZOS)
        s.paste(pl, (920 + (620 - w) // 2, 90), pl)
    d.text((960, 470), "Parent brand, shown on every post", font=_font(FONT_REG, 26), fill="#A9BCB2")
    card = render_card("Sample: your first Tri News post", "This is where the rewritten story goes.", "confirmed", "feed")
    card = Image.open(__import__("io").BytesIO(card)).convert("RGB").resize((400, 500), Image.LANCZOS)
    s.paste(card, (920, 580))
    d.text((1340, 600), "Sample post", font=cf, fill=SLATE)
    s.save(os.path.join(OUT, "brand-sheet.png"))


def main():
    mark(512).save(os.path.join(OUT, "mark-512.png"))
    white = mark(512, **REV)
    white.save(os.path.join(OUT, "mark-white-512.png"))
    white.save(os.path.join(ASSETS, "trinews-mark-white.png"))
    on_tile(1080, INK, 690, **REV).convert("RGB").save(os.path.join(OUT, "avatar-1080.png"))
    for n in (192, 512):
        on_tile(n, INK, round(n * 0.62), rounded=True, **REV).save(os.path.join(OUT, f"icon-{n}.png"))
    on_tile(512, INK, 300, **REV).convert("RGB").save(os.path.join(OUT, "icon-maskable-512.png"))
    on_tile(180, INK, 108, **REV).convert("RGB").save(os.path.join(OUT, "apple-touch-icon.png"))
    write("mark.svg", f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">{DEFS}{grp(LEAF, "#fff")}</svg>')
    write("mark-white.svg", f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">{DEFS}{grp("#fff", INK)}</svg>')
    write("lockup.svg", lockup(LEAF, "#fff", LEAF, INK, SLATE))
    write("lockup-reversed.svg", lockup("#fff", INK, MINT, "#fff", "#A9BCB2"))
    pm, pl = key_parent()
    if pm:
        for name, im in (("tribridge-mark.png", pm), ("tribridge-lockup.png", pl)):
            im.save(os.path.join(OUT, name))
        pm.save(os.path.join(ASSETS, "tribridge-mark.png"))
    for f in ("icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png"):
        shutil.copy(os.path.join(OUT, f), os.path.join(ADMIN, f))
    sheet()
    print("brand files written to", OUT)


if __name__ == "__main__":
    main()
