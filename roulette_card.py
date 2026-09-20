import io
import math
import os
from pathlib import Path
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ──────────────────────────────────────────────────────────────────────────────
#  Константы и стилевая палитра из stats_card.py
# ──────────────────────────────────────────────────────────────────────────────
W, H = 1200, 675

BG_TOP     = (13, 17, 23)
BG_BOTTOM  = (8, 11, 16)
WHITE      = (245, 247, 250, 255)
MUTED      = (148, 156, 168, 255)
RED        = (239, 68, 68, 255)
GOLD       = (255, 193, 7, 255)
SILVER     = (203, 213, 225, 255)
BRONZE     = (217, 119, 6, 255)
GREEN_WIN  = (34, 197, 94, 255)    # Победители (1, 2, 3 место) - ЗЕЛЕНЫЙ
GRAY_REST  = (55, 65, 81, 230)     # Остальные - СЕРЫЙ
CARD       = (18, 22, 29, 235)
BORDER     = (55, 61, 72, 150)

# Разноцветная палитра для колеса ДО ЗАПУСКА
SECTOR_PALETTE = [
    (239, 68, 68),    # Красный
    (37, 99, 235),    # Синий
    (245, 158, 11),   # Янтарный / Жёлтый
    (236, 72, 153),   # Розовый
    (147, 51, 234),   # Пурпурный
    (16, 185, 129),   # Изумрудный
    (14, 165, 233),   # Голубой
    (217, 119, 6),    # Оранжевый
    (139, 92, 246),   # Фиолетовый
]

# ──────────────────────────────────────────────────────────────────────────────
#  Загрузка шрифтов из stats_card.py
# ──────────────────────────────────────────────────────────────────────────────
def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/Montserrat-Bold.ttf" if bold else "C:/Windows/Fonts/Montserrat-Regular.ttf",
        "C:/Windows/Fonts/montserrat.ttf",
        "Montserrat-Bold.ttf" if bold else "Montserrat-Regular.ttf",
        "montserrat.ttf",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "montserrat.ttf"),
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


import re

def _clean_display_name(name: str) -> str:
    if not name:
        return ""
    cleaned = re.sub(r"^([!\[].*?\]\s*)+", "", name).strip()
    return cleaned if cleaned else name


def _gradient(size: Tuple[int, int], top=BG_TOP, bottom=BG_BOTTOM) -> Image.Image:
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


def _add_glow(base: Image.Image, center: Tuple[int, int], radius: int, color: Tuple[int, int, int], blur: int = 40, alpha: int = 80):
    glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    x, y = center
    gd.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*color, alpha))
    glow = glow.filter(ImageFilter.GaussianBlur(blur))
    base.alpha_composite(glow)


def _circle_avatar(base: Image.Image, avatar_img: Image.Image, center: Tuple[int, int], diameter: int):
    avatar = avatar_img.convert("RGBA").resize((diameter, diameter), Image.Resampling.LANCZOS)
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter - 1, diameter - 1), fill=255)
    x = center[0] - diameter // 2
    y = center[1] - diameter // 2

    ring = Image.new("RGBA", base.size, (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    rd.ellipse((x - 4, y - 4, x + diameter + 4, y + diameter + 4), outline=RED, width=4)
    base.alpha_composite(ring)
    base.paste(avatar, (x, y), mask)


def _radial_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, center: Tuple[int, int], mid_angle_deg: float, radius: float, fill: Tuple[int, int, int, int]):
    angle_rad = math.radians(mid_angle_deg)
    tx = center[0] + radius * math.cos(angle_rad)
    ty = center[1] + radius * math.sin(angle_rad)

    bbox = font.getbbox(text)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    txt_img = Image.new("RGBA", (tw + 20, th + 20), (0, 0, 0, 0))
    td = ImageDraw.Draw(txt_img)
    td.text((10 + 1, 10 + 1), text, font=font, fill=(0, 0, 0, 200))
    td.text((10, 10), text, font=font, fill=fill)

    rot_angle = mid_angle_deg + 180 if 90 < (mid_angle_deg % 360) < 270 else mid_angle_deg
    rotated = txt_img.rotate(-rot_angle, expand=True, resample=Image.Resampling.BICUBIC)

    rx, ry = rotated.size
    px = int(tx - rx / 2)
    py = int(ty - ry / 2)
    return rotated, (px, py)


# ──────────────────────────────────────────────────────────────────────────────
#  Основная функция генерации рулетки
# ──────────────────────────────────────────────────────────────────────────────
def generate_roulette_image(
    participants: List[str],
    winners: Optional[List[str]] = None,
    bot_logo_path: str = "bot_logo.png"
) -> io.BytesIO:
    """
    Генерирует карточку рулетки в стиле stats_card.py.
    - Красное фоновое свечение как за рулеткой, так и за заголовком УЧАСТНИКИ (без синего!).
    - До запуска: сектора разноцветные.
    - После запуска: 3 победителя — ЗЕЛЁНЫЕ, остальные — СЕРЫЕ.
    - Текст и обводка плашки участников — БЕЛЫЕ / СТАНДАРТНЫЕ.
    """
    if not participants:
        participants = ["Участник 1", "Участник 2"]

    top_winners = winners[:3] if winners else []

    scale = 2
    sw, sh = W * scale, H * scale

    base = _gradient((W, H))

    # КРАСНОЕ фоновое свечение за колесом и за заголовком «УЧАСТНИКИ» (убрано синее!)
    _add_glow(base, (370, 337), 290, RED[:3], blur=50, alpha=80)
    _add_glow(base, (900, 180), 240, RED[:3], blur=60, alpha=50)

    hi_res = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    draw = ImageDraw.Draw(hi_res)

    cx, cy = 370 * scale, 337 * scale
    outer_r = 270 * scale

    n = len(participants)
    angle_per_sector = 360.0 / n

    winner_index = None
    if top_winners:
        try:
            winner_index = participants.index(top_winners[0])
        except ValueError:
            winner_index = 0

    if winner_index is not None and 0 <= winner_index < n:
        offset_angle = -90.0 - (winner_index + 0.5) * angle_per_sector
    else:
        offset_angle = -90.0

    # 1. Отрисовка секторов рулетки
    for i, name in enumerate(participants):
        start_deg = offset_angle + i * angle_per_sector
        end_deg = start_deg + angle_per_sector

        if top_winners:
            if name in top_winners:
                fill_col = GREEN_WIN
            else:
                fill_col = GRAY_REST
        else:
            color = SECTOR_PALETTE[i % len(SECTOR_PALETTE)]
            fill_col = color + (240,)

        box = [cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r]
        draw.pieslice(box, start=start_deg, end=end_deg, fill=fill_col, outline=(15, 23, 42, 255), width=int(2 * scale))

    wheel_down = hi_res.resize((W, H), Image.Resampling.LANCZOS)
    base.alpha_composite(wheel_down)

    # Текст на секторах
    draw_base = ImageDraw.Draw(base)
    font_sec_base = _font(12 if n > 12 else 14, bold=True)
    text_r = 170

    for i, name in enumerate(participants):
        mid_deg = offset_angle + (i + 0.5) * angle_per_sector
        disp_name = _clean_display_name(name)
        clean_name = disp_name[:14] + "..." if len(disp_name) > 14 else disp_name

        if top_winners and name in top_winners:
            fill_c = (13, 17, 23, 255)
        elif top_winners:
            fill_c = (209, 213, 219, 255)
        else:
            fill_c = (13, 17, 23, 255) if (i % len(SECTOR_PALETTE)) in (2, 5) else WHITE

        rot_img, pos = _radial_text(draw_base, clean_name, font_sec_base, (370, 337), mid_deg, text_r, fill_c)
        base.paste(rot_img, pos, rot_img)

    # 2. Центральный круг логотипа бота
    logo_img = None
    if os.path.exists(bot_logo_path):
        try:
            logo_img = Image.open(bot_logo_path)
        except Exception:
            logo_img = None

    if not logo_img:
        logo_img = Image.new("RGBA", (130, 130), (18, 22, 29, 255))
        ld = ImageDraw.Draw(logo_img)
        ld.ellipse((10, 10, 120, 120), outline=RED, width=4)
        ld.text((38, 48), "SWAG", font=_font(18, bold=True), fill=WHITE)

    _circle_avatar(base, logo_img, center=(370, 337), diameter=110)

    # 3. Стрелка-указатель сверху
    pointer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pointer)
    ptr_cx, ptr_cy = 370, 337 - 270
    pd.polygon([(ptr_cx - 16, ptr_cy - 18), (ptr_cx + 16, ptr_cy - 18), (ptr_cx, ptr_cy + 14)], fill=RED, outline=WHITE, width=2)
    base.alpha_composite(pointer)

    # ──────────────────────────────────────────────────────────────────────────
    #  ПРАВАЯ ЧАСТЬ: ИНФОРМАЦИОННАЯ ПАНЕЛЬ (БЕЛЫЙ ТЕКСТ И СТАНДАРТНАЯ ОБВОДКА)
    # ──────────────────────────────────────────────────────────────────────────

    if top_winners:
        draw_base.text((690, 45), "ПРИЗОВЫЕ МЕСТА", font=_font(22, bold=True), fill=GREEN_WIN)

        y_offset = 105
        place_labels = ["1 МЕСТО", "2 МЕСТО", "3 МЕСТО"]
        border_colors = [GOLD, SILVER, BRONZE]

        for idx, p_name in enumerate(top_winners):
            title = place_labels[idx] if idx < 3 else f"{idx+1} МЕСТО"
            b_col = border_colors[idx] if idx < 3 else BORDER

            draw_base.rounded_rectangle([680, y_offset, 1145, y_offset + 95], radius=14, fill=CARD, outline=b_col, width=2)

            badge_box = [705, y_offset + 22, 755, y_offset + 72]
            draw_base.rounded_rectangle(badge_box, radius=10, fill=(30, 41, 59, 255), outline=b_col, width=1)
            draw_base.text((722, y_offset + 32), str(idx + 1), font=_font(22, bold=True), fill=b_col)

            draw_base.text((775, y_offset + 22), title, font=_font(13, bold=True), fill=b_col)
            p_disp = _clean_display_name(p_name)
            draw_base.text((775, y_offset + 46), p_disp[:24], font=_font(20, bold=True), fill=WHITE)

            y_offset += 115

    else:
        draw_base.text((690, 45), f"УЧАСТНИКИ ({len(participants)})", font=_font(22, bold=True), fill=WHITE)

        draw_base.rounded_rectangle([680, 95, 1145, 600], radius=14, fill=CARD, outline=BORDER, width=1)

        max_show = 14
        display_list = participants[:max_show]
        y_p = 115

        for idx, p_name in enumerate(display_list):
            num_str = f"{idx + 1}."
            p_disp = _clean_display_name(p_name)
            draw_base.text((710, y_p), num_str, font=_font(14, bold=True), fill=MUTED)
            draw_base.text((745, y_p), p_disp[:26], font=_font(14, bold=True), fill=WHITE)
            y_p += 33

        if len(participants) > max_show:
            rem = len(participants) - max_show
            draw_base.text((710, y_p + 5), f"... и ещё {rem} участников", font=_font(13, bold=False), fill=MUTED)

    buf = io.BytesIO()
    base.save(buf, format="PNG")
    buf.seek(0)
    return buf
