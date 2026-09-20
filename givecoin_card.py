from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1200, 650

BG_TOP = (18, 4, 7, 255)
BG_BOTTOM = (8, 2, 4, 255)
WHITE = (255, 255, 255, 255)
MUTED = (160, 140, 145, 255)
CRIMSON_GLOW = (220, 30, 45)
CARD_BG = (35, 7, 12, 220)
CARD_BORDER = (160, 28, 40, 180)
RED_TEXT = (255, 60, 75, 255)
GOLD = (255, 193, 7, 255)


def _font(size: int, bold: bool = False):
    candidates = [
        "C:/Windows/Fonts/Montserrat-Bold.ttf" if bold else "C:/Windows/Fonts/Montserrat-Regular.ttf",
        "C:/Windows/Fonts/montserrat.ttf",
        "Montserrat-Bold.ttf" if bold else "Montserrat-Regular.ttf",
        "montserrat.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf",
        "/usr/share/fonts/truetype/montserrat/Montserrat-Bold.ttf" if bold else "/usr/share/fonts/truetype/montserrat/Montserrat-Regular.ttf",
        "/usr/share/fonts/truetype/inter/Inter-Bold.ttf" if bold else "/usr/share/fonts/truetype/inter/Inter-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for path in candidates:
        try:
            if Path(path).exists():
                return ImageFont.truetype(path, size)
        except Exception:
            pass
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        pass
    return ImageFont.load_default()


def _rounded(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _gradient(size):
    w, h = size
    im = Image.new("RGBA", (1, h))
    px = im.load()
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(BG_TOP[0] * (1 - t) + BG_BOTTOM[0] * t)
        g = int(BG_TOP[1] * (1 - t) + BG_BOTTOM[1] * t)
        b = int(BG_TOP[2] * (1 - t) + BG_BOTTOM[2] * t)
        px[0, y] = (r, g, b, 255)
    return im.resize((w, h), Image.Resampling.NEAREST)


def _glow(base, center, radius, color, blur=70, alpha=80):
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y = center
    d.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*color, alpha))
    base.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


def _avatar(base, avatar_img, center=(100, 92), diameter=110):
    avatar = avatar_img.convert("RGBA").resize((diameter, diameter), Image.Resampling.LANCZOS)
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter - 1, diameter - 1), fill=255)
    x, y = center[0] - diameter // 2, center[1] - diameter // 2
    ring = Image.new("RGBA", base.size, (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    rd.ellipse((x - 6, y - 6, x + diameter + 6, y + diameter + 6), outline=RED_TEXT, width=5)
    base.alpha_composite(ring)
    base.paste(avatar, (x, y), mask)


def render_vector_icon(kind: str, size: int = 24, color: tuple = MUTED) -> Image.Image:
    scale = 4
    canvas_size = size * scale
    im = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = 7

    if kind == "wallet":
        d.rounded_rectangle((12, 24, 100, 88), radius=14, outline=color, width=w)
        d.line((12, 44, 100, 44), fill=color, width=w)
        d.ellipse((72, 58, 88, 74), fill=color)

    elif kind == "admin" or kind == "user":
        d.ellipse((36, 12, 76, 52), outline=color, width=w)
        d.arc((16, 56, 96, 116), 180, 360, fill=color, width=w)

    return im.resize((size, size), Image.Resampling.LANCZOS)


def generate_givecoin_card(
    user_name: str,
    role_title: str,
    admin_name: str,
    amount: int,
    new_balance: int,
    avatar_img: Image.Image,
) -> BytesIO:
    """Generate a 1200x650 red-glow premium card with Montserrat font matching Screenshot 2."""
    img = _gradient((W, H))

    _glow(img, (100, 92), 220, CRIMSON_GLOW, blur=90, alpha=90)
    _glow(img, (600, 310), 300, CRIMSON_GLOW, blur=110, alpha=70)
    _glow(img, (1050, 90), 180, CRIMSON_GLOW, blur=80, alpha=50)

    draw = ImageDraw.Draw(img)

    # 1. Header (Avatar + Username + Role Pill)
    _avatar(img, avatar_img, (100, 92), 110)

    draw.text((178, 44), user_name, font=_font(30, True), fill=WHITE)

    # Role Pill under nickname
    sub_font = _font(13, True)
    pill_w = min(450, draw.textbbox((0, 0), role_title, font=sub_font)[2] + 28)
    _rounded(draw, (178, 88, 178 + pill_w, 118), 12, (50, 10, 16, 220), outline=(140, 28, 40, 180), width=1)
    draw.text((192, 94), role_title, font=sub_font, fill=RED_TEXT)

    # Top Right Server Brand Header
    draw.text((980, 44), "SWAG MODER", font=_font(22, True), fill=WHITE)
    draw.text((980, 74), "ИЗМЕНЕНИЕ БАЛАНСА", font=_font(12, True), fill=MUTED)

    draw.line((48, 160, 1152, 160), fill=(50, 16, 22, 180), width=1)

    # 2. Middle Main Card (+ X КОИНОВ)
    _rounded(draw, (48, 180, 1152, 440), 24, CARD_BG, outline=CARD_BORDER, width=2)

    sign = "+" if amount >= 0 else "-"
    amount_str = f"{sign} {abs(int(amount))} КОИНОВ"

    main_font = _font(56, True)
    text_box = draw.textbbox((0, 0), amount_str, font=main_font)
    tw = text_box[2] - text_box[0]
    th = text_box[3] - text_box[1]
    tx = (W - tw) // 2
    ty = 180 + (260 - th) // 2 - 6

    draw.text((tx, ty), amount_str, font=main_font, fill=WHITE)

    # 3. Bottom Row Cards (Left: Balance Change, Right: Admin)
    old_balance = max(0, new_balance - amount)

    # Bottom Left Card (Balance Transition)
    _rounded(draw, (48, 465, 585, 595), 20, (26, 6, 10, 230), outline=(100, 20, 30, 160), width=1)
    wallet_icon = render_vector_icon("wallet", size=22, color=MUTED)
    img.paste(wallet_icon, (72, 485), wallet_icon)
    draw.text((102, 488), "ИЗМЕНЕНИЕ БАЛАНСА", font=_font(11, True), fill=MUTED)

    bal_trans_text = f"{old_balance:,}  →  {new_balance:,}".replace(",", " ")
    draw.text((72, 525), bal_trans_text, font=_font(28, True), fill=WHITE)

    # Bottom Right Card (Admin)
    _rounded(draw, (615, 465, 1152, 595), 20, (26, 6, 10, 230), outline=(100, 20, 30, 160), width=1)
    admin_icon = render_vector_icon("admin", size=22, color=MUTED)
    img.paste(admin_icon, (639, 485), admin_icon)
    draw.text((669, 488), "ВЫДАЛ", font=_font(11, True), fill=MUTED)

    draw.text((639, 525), admin_name, font=_font(24, True), fill=WHITE)

    out = BytesIO()
    out.name = "givecoin_card.png"
    img.convert("RGB").save(out, format="PNG", optimize=True)
    out.seek(0)
    return out


__all__ = ["generate_givecoin_card"]
