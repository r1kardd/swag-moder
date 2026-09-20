from io import BytesIO
from pathlib import Path
from typing import Dict, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1200, 675
BG = (13, 17, 23, 255)
WHITE = (245, 247, 250, 255)
MUTED = (148, 156, 168, 255)
RED = (239, 68, 68, 255)
GOLD = (255, 193, 7, 255)
CARD = (18, 22, 29, 235)
BORDER = (55, 61, 72, 150)


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


def _gradient(size, top=(13, 17, 23), bottom=(8, 11, 16)):
    w, h = size
    im = Image.new("RGBA", (1, h))
    px = im.load()
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        px[0, y] = (r, g, b, 255)
    return im.resize((w, h), Image.Resampling.NEAREST)


def _add_glow(base, center, radius, color, blur=35, alpha=100):
    glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    x, y = center
    gd.ellipse((x-radius, y-radius, x+radius, y+radius), fill=(*color, alpha))
    glow = glow.filter(ImageFilter.GaussianBlur(blur))
    base.alpha_composite(glow)


def _circle_avatar(base, avatar_img, center=(105, 100), diameter=112):
    avatar = avatar_img.convert("RGBA").resize((diameter, diameter), Image.Resampling.LANCZOS)
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter-1, diameter-1), fill=255)
    x = center[0] - diameter // 2
    y = center[1] - diameter // 2
    ring = Image.new("RGBA", base.size, (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    rd.ellipse((x-5, y-5, x+diameter+5, y+diameter+5), outline=RED, width=5)
    base.alpha_composite(ring)
    base.paste(avatar, (x, y), mask)


def render_vector_icon(kind: str, size: int = 28, color: Tuple[int, int, int, int] = RED) -> Image.Image:
    """Renders a smooth 4x supersampled anti-aliased vector icon."""
    scale = 4
    canvas_size = size * scale
    im = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    c = color
    w = 7  # stroke width at 4x scale

    if kind == "ticket":
        d.rounded_rectangle((12, 20, 100, 92), radius=14, outline=c, width=w)
        d.ellipse((-10, 44, 20, 68), fill=(0, 0, 0, 0), outline=c, width=w)
        d.ellipse((92, 44, 122, 68), fill=(0, 0, 0, 0), outline=c, width=w)
        d.line((44, 20, 44, 92), fill=c, width=w)
        d.line((58, 40, 86, 40), fill=c, width=w)
        d.line((58, 72, 86, 72), fill=c, width=w)

    elif kind == "muted":
        d.rounded_rectangle((42, 12, 70, 54), radius=14, outline=c, width=w)
        d.arc((28, 32, 84, 76), 0, 180, fill=c, width=w)
        d.line((56, 76, 56, 96), fill=c, width=w)
        d.line((36, 96, 76, 96), fill=c, width=w)
        d.line((16, 16, 96, 96), fill=c, width=w + 2)

    elif kind == "kick":
        d.rounded_rectangle((16, 12, 64, 100), radius=8, outline=c, width=w)
        d.line((64, 56, 100, 56), fill=c, width=w)
        d.polygon([(90, 40), (112, 56), (90, 72)], fill=c)

    elif kind == "ban":
        d.ellipse((12, 12, 100, 100), outline=c, width=w)
        d.line((28, 28, 84, 84), fill=c, width=w)

    elif kind == "warn":
        d.polygon([(56, 10), (104, 98), (8, 98)], outline=c, width=w)
        d.line((56, 40, 56, 68), fill=c, width=w)
        d.ellipse((50, 78, 62, 90), fill=c)

    elif kind == "message":
        d.rounded_rectangle((12, 16, 100, 80), radius=16, outline=c, width=w)
        d.polygon([(28, 80), (20, 104), (48, 80)], fill=c)
        d.line((32, 40, 80, 40), fill=c, width=w - 2)
        d.line((32, 56, 64, 56), fill=c, width=w - 2)

    elif kind == "voice" or kind == "oral":
        d.rounded_rectangle((12, 16, 100, 80), radius=16, outline=c, width=w)
        d.polygon([(68, 80), (92, 104), (84, 80)], fill=c)
        d.line((56, 32, 56, 54), fill=c, width=w)
        d.ellipse((50, 62, 62, 74), fill=c)

    elif kind == "strict":
        d.polygon([(56, 8), (98, 28), (88, 76), (56, 104), (24, 76), (14, 28)], outline=c, width=w)
        d.line((56, 32, 56, 62), fill=c, width=w)
        d.ellipse((50, 72, 62, 84), fill=c)

    elif kind == "coin":
        d.ellipse((8, 8, 104, 104), outline=GOLD, width=w)
        d.ellipse((22, 22, 90, 90), outline=GOLD, width=4)
        font_c = _font(36, True)
        d.text((32, 34), "SC", font=font_c, fill=GOLD)

    return im.resize((size, size), Image.Resampling.LANCZOS)


def _get_stat(stats: Dict, *keys):
    for key in keys:
        if key in stats:
            return stats[key]
    return 0


def _fit_text(draw, text, font, max_width, min_size=14, bold=False):
    size = font.size if hasattr(font, "size") else 24
    while size > min_size and draw.textbbox((0, 0), str(text), font=font)[2] > max_width:
        size -= 1
        font = _font(size, bold)
    return font


def generate_stats_card(username: str, role_title: str, avatar_img: Image.Image, stats: dict, coins: int) -> BytesIO:
    """Generate a 1200x675 premium moderator profile/stats card as PNG in BytesIO."""
    img = _gradient((W, H))
    _add_glow(img, (880, 125), 260, (155, 25, 40), blur=100, alpha=70)
    _add_glow(img, (530, 520), 300, (65, 18, 32), blur=110, alpha=55)
    draw = ImageDraw.Draw(img)

    # Header
    _circle_avatar(img, avatar_img, (105, 100), 112)

    # Username
    name_font = _fit_text(draw, username, _font(30, True), 610, 18, True)
    draw.text((187, 48), username, font=name_font, fill=WHITE)

    # Role Title Badge with accurate padding
    role_font = _fit_text(draw, role_title, _font(14, False), 330, 10, False)
    role_bbox = draw.textbbox((0, 0), role_title, font=role_font)
    tw = role_bbox[2] - role_bbox[0]
    th = role_bbox[3] - role_bbox[1]
    badge_w = tw + 28
    badge_h = max(28, th + 12)
    badge_y = 94
    _rounded(draw, (187, badge_y, 187 + badge_w, badge_y + badge_h), 10, (39, 18, 25, 210), outline=(110, 30, 42, 180), width=1)
    draw.text((187 + 14, badge_y + (badge_h - th) // 2 - 2), role_title, font=role_font, fill=(235, 99, 105, 255))

    # Coins badge (Top Right)
    _rounded(draw, (820, 52, 1152, 120), 18, (29, 24, 13, 225), outline=(106, 82, 25, 190), width=1)
    coin_icon = render_vector_icon("coin", size=36)
    img.paste(coin_icon, (838, 68), coin_icon)
    draw.text((886, 65), "SWAG COINS", font=_font(12, True), fill=(200, 180, 130, 255))
    draw.text((886, 83), f"{int(coins):,} SC", font=_font(22, True), fill=WHITE)

    # Divider line
    draw.line((48, 178, 1152, 178), fill=(43, 48, 57, 180), width=1)

    # Section title
    draw.text((48, 202), "СТАТИСТИКА МОДЕРАТОРА", font=_font(18, True), fill=WHITE)
    draw.text((48, 230), "Актуальные показатели активности", font=_font(13), fill=MUTED)

    items = [
        ("Тикеты", _get_stat(stats, "tickets", "тикеты", "ticket"), "ticket"),
        ("Муты", _get_stat(stats, "mutes", "муты", "mute"), "muted"),
        ("Кики", _get_stat(stats, "kicks", "кики", "kick"), "kick"),
        ("Баны", _get_stat(stats, "bans", "баны", "ban"), "ban"),
        ("Варны", _get_stat(stats, "warns", "варны", "warn", "warnings"), "warn"),
        ("Сообщения", _get_stat(stats, "deleted_msgs", "messages", "сообщения", "message"), "message"),
        ("Устные выговоры", _get_stat(stats, "oral_vigs", "oral_reprimands", "oral_warnings", "устные"), "oral"),
        ("Строгие выговоры", _get_stat(stats, "strict_vigs", "strict_reprimands", "strict_warnings", "строгие"), "strict"),
    ]

    card_w, card_h = 264, 119
    gap_x, gap_y = 16, 14
    start_x, start_y = 48, 270

    for i, (label, value, icon_kind) in enumerate(items):
        col, row = i % 4, i // 4
        x = start_x + col * (card_w + gap_x)
        y = start_y + row * (card_h + gap_y)

        # Base Card
        _rounded(draw, (x, y, x + card_w, y + card_h), 16, CARD, outline=BORDER, width=1)
        # Top Red Accent line
        draw.line((x + 18, y + 1, x + 70, y + 1), fill=(180, 35, 50, 220), width=2)

        # Smooth anti-aliased vector icon
        icon_img = render_vector_icon(icon_kind, size=26, color=RED)
        img.paste(icon_img, (x + 18, y + 18), icon_img)

        # Label perfectly aligned with icon center
        draw.text((x + 52, y + 23), label.upper(), font=_font(11, True), fill=MUTED)

        # Large Stat Value
        value_font = _font(32, True)
        value_text = f"{int(value):,}" if isinstance(value, (int, float)) else str(value)
        draw.text((x + 18, y + 58), value_text, font=value_font, fill=WHITE)

    out = BytesIO()
    out.name = "stats_card.png"
    img.convert("RGB").save(out, format="PNG", optimize=True)
    out.seek(0)
    return out


__all__ = ["generate_stats_card"]
