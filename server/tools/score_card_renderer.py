from __future__ import annotations

import datetime
import io
import os
import threading
import time
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from discord_bot_core import ScoreCardData, format_score_arcaea


SERVER_ROOT = Path(
    os.environ.get("LYGUS_SERVER_ROOT", Path(__file__).resolve().parents[1])
)
JACKETS_DIR = Path(
    os.environ.get("AKAINE_JACKETS_DIR", SERVER_ROOT / "assets" / "jackets")
)
CHAR_DIR = Path(
    os.environ.get("AKAINE_CHAR_DIR", SERVER_ROOT / "assets" / "char")
)
IMG_DIR = Path(
    os.environ.get("AKAINE_IMG_DIR", SERVER_ROOT / "assets" / "img")
)
THEME_DIR = Path(
    os.environ.get("AKAINE_CARD_THEME_DIR", SERVER_ROOT / "assets" / "card_theme")
)
FALLBACK_OTF = SERVER_ROOT / "tools" / "b30tools" / "WantedSans-SemiBold.otf"

_CARD_RENDER_SLOT = threading.BoundedSemaphore(2)
_FONT_CACHE: dict[tuple[str, int], ImageFont.ImageFont] = {}

DIFF_FULL_NAMES = {
    0: "Past",
    1: "Present",
    2: "Future",
    3: "Beyond",
    4: "Eternal",
}

DIFF_TEXT_COLORS = {
    0: (20, 165, 215, 255),
    1: (90, 145, 55, 255),
    2: (118, 35, 112, 255),
    3: (166, 20, 49, 255),
    4: (172, 118, 22, 255),
}

DIFF_PILL_COLORS = {
    0: (48, 162, 224, 235),
    1: (78, 165, 82, 235),
    2: (136, 62, 178, 235),
    3: (182, 36, 68, 235),
    4: (186, 134, 34, 235),
}


def _get_font(filename: str, size: int) -> ImageFont.ImageFont:
    key = (filename, int(size))
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached
    candidates = [
        THEME_DIR / "font" / filename,
        THEME_DIR / "font" / "NotoSansCJK-Regular.otf",
        FALLBACK_OTF,
    ]
    for path in candidates:
        if path.is_file():
            try:
                font = ImageFont.truetype(str(path), size)
                _FONT_CACHE[key] = font
                return font
            except Exception:
                continue
    font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def find_jacket_path(song_id: str) -> Optional[Path]:
    if not JACKETS_DIR.is_dir():
        return None
    for name in (
        f"{song_id}.jpg",
        f"{song_id}.png",
        f"dl_{song_id}.jpg",
        f"dl_{song_id}.png",
    ):
        candidate = JACKETS_DIR / name
        if candidate.is_file():
            return candidate
    return None


def find_partner_icon_path(
    character_id: Optional[int], is_uncapped: bool = False
) -> Optional[Path]:
    if character_id is None or not CHAR_DIR.is_dir():
        return None
    cid = str(character_id)
    names = (
        [f"{cid}u_icon.png", f"{cid}_icon.png"]
        if is_uncapped
        else [f"{cid}_icon.png", f"{cid}u_icon.png"]
    )
    for name in names:
        candidate = CHAR_DIR / name
        if candidate.is_file():
            return candidate
    return None


def _ptt_badge_filename(raw_ptt: int) -> str:
    if raw_ptt < 0:
        return "rating_off.png"
    if raw_ptt >= 1300:
        return "rating_7.png"
    if raw_ptt >= 1250:
        return "rating_6.png"
    if raw_ptt >= 1200:
        return "rating_5.png"
    if raw_ptt >= 1100:
        return "rating_4.png"
    if raw_ptt >= 1000:
        return "rating_3.png"
    if raw_ptt >= 700:
        return "rating_2.png"
    if raw_ptt >= 350:
        return "rating_1.png"
    return "rating_0.png"


def _clear_banner_filename(clear_type_id: int) -> str:
    if clear_type_id == 3:
        return "clear_pure.png"
    if clear_type_id == 2:
        return "clear_full.png"
    if clear_type_id == 0:
        return "clear_fail.png"
    return "clear_normal.png"


def _grade_filename(grade: str) -> str:
    mapping = {
        "EX+": "grade_ex+.png",
        "EX": "grade_ex.png",
        "AA": "grade_aa.png",
        "A": "grade_a.png",
        "B": "grade_b.png",
        "C": "grade_c.png",
        "D": "grade_d.png",
    }
    return mapping.get(grade, "grade_d.png")


def _open_rgba(path: Path) -> Optional[Image.Image]:
    if not path.is_file():
        return None
    try:
        return Image.open(path).convert("RGBA")
    except Exception:
        return None


def _text_fit(
    draw: ImageDraw.ImageDraw, text: str, max_width: int, font: ImageFont.ImageFont
) -> str:
    value = str(text)
    if draw.textlength(value, font=font) <= max_width:
        return value
    suffix = "..."
    while value and draw.textlength(value + suffix, font=font) > max_width:
        value = value[:-1]
    return (value + suffix) if value else ""


def _relative_time(ts_seconds: int) -> str:
    if not ts_seconds:
        return "—"
    delta = max(0, int(time.time()) - int(ts_seconds))
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    if delta < 86400 * 30:
        return f"{delta // 86400}d ago"
    return datetime.datetime.fromtimestamp(ts_seconds, tz=datetime.timezone.utc).strftime(
        "%Y-%m-%d"
    )


def _draw_pill(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    fill: tuple[int, int, int, int],
    text_color: tuple[int, int, int, int],
    font: ImageFont.ImageFont,
    *,
    pad_x: int = 8,
    height: int = 22,
    radius: int = 6,
) -> int:
    w = int(draw.textlength(text, font=font)) + pad_x * 2
    draw.rounded_rectangle((x, y, x + w, y + height), radius=radius, fill=fill)
    bbox = draw.textbbox((0, 0), text, font=font)
    th = bbox[3] - bbox[1]
    ty = y + (height - th) // 2 - bbox[1]
    draw.text((x + pad_x, ty), text, fill=text_color, font=font)
    return w


def _render_score_card_sync(card: ScoreCardData) -> bytes:
    w, h = 600, 867
    image = Image.new("RGBA", (w, h), (230, 234, 244, 255))

    jacket_path = find_jacket_path(card.song_id)
    jacket = _open_rgba(jacket_path) if jacket_path is not None else None

    if jacket is not None:
        bg_cover = jacket.resize((868, 868), Image.Resampling.BILINEAR)
        image.alpha_composite(bg_cover, (-134, 0))
        image = image.filter(ImageFilter.GaussianBlur(radius=10))
        fog = Image.new("RGBA", (w, h), (255, 255, 255, 58))
        image = Image.alpha_composite(image, fog)
    else:
        bg_col = (210, 218, 236, 255) if card.difficulty_id < 3 else (225, 208, 222, 255)
        image = Image.new("RGBA", (w, h), bg_col)

    bg_frame_name = "RawV3Bg_1.png" if card.difficulty_id >= 3 else "RawV3Bg_0.png"
    frame = _open_rgba(THEME_DIR / "recent" / bg_frame_name)
    if frame is not None:
        if frame.size != (w, h):
            frame = frame.resize((w, h), Image.Resampling.LANCZOS)
        image = Image.alpha_composite(image, frame)
    else:
        fallback_panel = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        fdraw = ImageDraw.Draw(fallback_panel)
        fdraw.rounded_rectangle((36, 46, w - 36, h - 24), radius=18, fill=(250, 250, 254, 240))
        image = Image.alpha_composite(image, fallback_panel)

    # Center crisp 256x256 song jacket at (172, 245)
    jx, jy, js = 172, 245, 256
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle((jx - 2, jy + 3, jx + js + 4, jy + js + 7), fill=(20, 20, 35, 70))
    shadow = shadow.filter(ImageFilter.GaussianBlur(6))
    image = Image.alpha_composite(image, shadow)
    if jacket is not None:
        image.alpha_composite(jacket.resize((js, js), Image.Resampling.LANCZOS), (jx, jy))
    else:
        jdraw = ImageDraw.Draw(image)
        jdraw.rectangle((jx, jy, jx + js, jy + js), fill=(55, 62, 88, 255))
        f_no = _get_font("Exo-SemiBold.ttf", 22)
        nw = jdraw.textlength("NO JACKET", font=f_no)
        jdraw.text((jx + (js - nw) / 2, jy + js / 2 - 12), "NO JACKET", fill=(225, 230, 245, 240), font=f_no)

    # Partner icon + PTT badge
    partner_path = find_partner_icon_path(card.character_id, card.is_char_uncapped)
    if partner_path is None:
        partner_path = find_partner_icon_path(0, False)
    partner_img = _open_rgba(partner_path) if partner_path is not None else None
    if partner_img is not None:
        image.alpha_composite(partner_img.resize((100, 100), Image.Resampling.LANCZOS), (86, 86))

    ptt_path = IMG_DIR / _ptt_badge_filename(card.raw_ptt)
    ptt_badge = _open_rgba(ptt_path)
    if ptt_badge is not None:
        image.alpha_composite(ptt_badge.resize((74, 74), Image.Resampling.LANCZOS), (132, 132))

    draw = ImageDraw.Draw(image)
    f_ptt_hi = _get_font("Exo-SemiBold.ttf", 24)
    f_ptt_lo = _get_font("Exo-SemiBold.ttf", 19)
    if card.raw_ptt is not None and card.raw_ptt >= 0:
        hi, lo = f"{card.raw_ptt / 100:.2f}".split(".")
        draw.text((168, 179), hi, fill=(255, 255, 255, 255), font=f_ptt_hi, anchor="rs", stroke_width=2, stroke_fill=(20, 18, 28, 255))
        draw.text((168, 179), "." + lo, fill=(255, 255, 255, 255), font=f_ptt_lo, anchor="ls", stroke_width=2, stroke_fill=(20, 18, 28, 255))
    else:
        draw.text((169, 181), "--", fill=(255, 255, 255, 255), font=f_ptt_hi, anchor="ms", stroke_width=2, stroke_fill=(20, 18, 28, 255))

    # User info right of avatar
    f_user = _get_font("Andrea.otf", 33)
    f_uid = _get_font("Andrea.otf", 18)
    f_pill = _get_font("Exo-SemiBold.ttf", 12)
    ux = 212
    uname = _text_fit(draw, card.username, 520 - ux, f_user)
    draw.text((ux, 92), uname, fill=(22, 24, 34, 255), font=f_user)
    ucode_label = f"ArcID:  {card.user_code}" if card.user_code else f"PTT:  {card.user_ptt}"
    draw.text((ux, 134), ucode_label, fill=(75, 80, 96, 255), font=f_uid)

    # Status pills under ArcID
    px = ux
    py = 166
    mode_lbl = f"RECENT #{card.recent_index}/{card.recent_total}" if card.is_recent else "PERSONAL BEST"
    pill_col = DIFF_PILL_COLORS.get(card.difficulty_id, (118, 35, 112, 235))
    px += _draw_pill(draw, px, py, mode_lbl, pill_col, (255, 255, 255, 255), f_pill) + 6
    if card.chart_rank is not None:
        lb_fill = (218, 152, 28, 245) if card.chart_rank == 1 else (58, 66, 92, 230)
        px += _draw_pill(draw, px, py, f"#{card.chart_rank} LB", lb_fill, (255, 255, 255, 255), f_pill) + 6
    if card.b30_rank is not None:
        _draw_pill(draw, px, py, f"B30 #{card.b30_rank}", (72, 108, 178, 235), (255, 255, 255, 255), f_pill)

    # Song title + Difficulty
    f_title = _get_font("NotoSansCJK-Regular.otf", 26)
    f_diff = _get_font("Kazesawa-Regular.ttf", 23)
    title_str = _text_fit(draw, card.song_title, 490, f_title)
    draw.text((300, 512), title_str, fill=(22, 24, 34, 255), font=f_title, anchor="mt")

    diff_full = DIFF_FULL_NAMES.get(card.difficulty_id, card.difficulty)
    cc_str = f"{card.constant:.1f}" if card.constant else "?"
    diff_line = f"{diff_full} | {cc_str}"
    diff_col = DIFF_TEXT_COLORS.get(card.difficulty_id, (118, 35, 112, 255))
    draw.text((300, 549), diff_line, fill=diff_col, font=f_diff, anchor="mt")

    # Clear banner centered around y=586..626
    clear_img = _open_rgba(THEME_DIR / "recent" / _clear_banner_filename(card.clear_type_id))
    if clear_img is not None:
        cw = 360
        ch = max(24, int(cw / clear_img.width * clear_img.height))
        clear_resized = clear_img.resize((cw, ch), Image.Resampling.LANCZOS)
        image.alpha_composite(clear_resized, ((w - cw) // 2, 586))
        draw = ImageDraw.Draw(image)

    # Score + Grade icon centered horizontally at y=638..686
    f_score = _get_font("Exo-Regular.ttf", 38)
    score_str = format_score_arcaea(card.score)
    score_w = int(draw.textlength(score_str, font=f_score))
    grade_img = _open_rgba(THEME_DIR / "grade" / _grade_filename(card.grade))
    if grade_img is not None:
        gw, gh = 74, 36
        grade_resized = grade_img.resize((gw, gh), Image.Resampling.LANCZOS)
        total_w = score_w + 14 + gw
        sx = (w - total_w) // 2
        draw.text((sx, 642), score_str, fill=(22, 24, 34, 255), font=f_score)
        image.alpha_composite(grade_resized, (sx + score_w + 14, 647))
        draw = ImageDraw.Draw(image)
    else:
        draw.text((300, 642), f"{score_str} [{card.grade}]", fill=(22, 24, 34, 255), font=f_score, anchor="mt")

    # PB Delta + Clear short tag centered at y=698
    f_pb = _get_font("Exo-Medium.ttf", 16)
    if card.is_recent:
        if card.pb_score is None:
            pb_text = f"First Play · {card.clear_short}"
            pb_col = (90, 96, 114, 255)
        elif card.pb_delta is not None and card.pb_delta >= 0 and card.score >= card.pb_score:
            pb_text = f"NEW PERSONAL BEST · {card.clear_short}"
            pb_col = (24, 138, 86, 255)
        else:
            delta_val = card.score - card.pb_score
            pb_text = f"PB {format_score_arcaea(card.pb_score)} ({delta_val:+,}) · {card.clear_short}"
            pb_col = (176, 48, 62, 255)
    else:
        pb_text = (
            f"Server LB #{card.chart_rank} / {card.chart_total_players} · {card.clear_short}"
            if card.chart_rank
            else f"Personal Best · {card.clear_short}"
        )
        pb_col = (72, 82, 108, 255)
    draw.text((300, 700), pb_text, fill=pb_col, font=f_pb, anchor="mt")

    # Bottom two-column stats
    f_lbl = _get_font("Exo-Regular.ttf", 18)
    f_val = _get_font("Exo-Medium.ttf", 18)
    f_j_lbl = _get_font("Exo-Medium.ttf", 19)
    f_j_val = _get_font("Exo-Medium.ttf", 17)

    # Left column: Play Ptt, Play Time, Chart Rank
    draw.text((64, 752), "Play Ptt:", fill=(105, 108, 120, 255), font=f_lbl)
    draw.text((164, 752), f"{card.rating:.4f}", fill=(40, 44, 58, 255), font=f_val)

    draw.text((64, 785), "Play Time:", fill=(105, 108, 120, 255), font=f_lbl)
    draw.text((164, 785), _relative_time(card.time_played), fill=(40, 44, 58, 255), font=f_val)

    draw.text((64, 818), "Server LB:", fill=(105, 108, 120, 255), font=f_lbl)
    lb_str = f"#{card.chart_rank} / {card.chart_total_players}" if card.chart_rank else "Unranked"
    draw.text((164, 818), lb_str, fill=(40, 44, 58, 255), font=f_val)

    # Right column: Pure / Far / Lost
    draw.text((366, 752), "Pure", fill=(26, 28, 38, 255), font=f_j_lbl)
    draw.text((434, 754), f"{card.pure_count:,} (+{card.shiny_pure_count:,})", fill=(35, 38, 52, 255), font=f_j_val)

    draw.text((366, 785), "Far", fill=(26, 28, 38, 255), font=f_j_lbl)
    draw.text((434, 787), f"{card.near_count:,}", fill=(176, 112, 24, 255), font=f_j_val)

    draw.text((366, 818), "Lost", fill=(26, 28, 38, 255), font=f_j_lbl)
    draw.text((434, 820), f"{card.miss_count:,}", fill=(182, 42, 58, 255), font=f_j_val)

    out = io.BytesIO()
    image.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()


def render_score_card(card: ScoreCardData) -> bytes:
    with _CARD_RENDER_SLOT:
        return _render_score_card_sync(card)
