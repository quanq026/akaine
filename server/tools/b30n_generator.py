from __future__ import annotations

import datetime
import io
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from discord_bot_core import (
    ValidationError,
    clear_type_short,
    difficulty_name,
    format_score_arcaea,
    normalize_timestamp_seconds,
)
from score_card_renderer import (
    CHAR_DIR,
    IMG_DIR,
    THEME_DIR,
    _get_font,
    _open_rgba,
    _ptt_badge_filename,
    _text_fit,
    find_jacket_path,
    find_partner_icon_path,
)
from PIL import ImageEnhance, ImageFilter


_B30N_SLOT = threading.BoundedSemaphore(1)
_FADE_MASK_CACHE: Optional[Image.Image] = None
_FADE_MASK_LANDSCAPE_CACHE: Optional[Image.Image] = None
_TILE_MASK_LANDSCAPE_CACHE: Optional[Image.Image] = None

DIFF_FILES = {
    0: "PST.png",
    1: "PRS.png",
    2: "FTR.png",
    3: "BYD.png",
}


def _get_fade_alpha_mask() -> Image.Image:
    """Precomputed 230x270 left-to-right fade mask (255 -> 0)."""
    global _FADE_MASK_CACHE
    if _FADE_MASK_CACHE is not None:
        return _FADE_MASK_CACHE
    ramp = Image.new("L", (230, 1), 0)
    px = ramp.load()
    for x in range(230):
        px[x, 0] = max(0, 255 - int(x * 255 / 212))
    _FADE_MASK_CACHE = ramp.resize((230, 270), Image.Resampling.NEAREST)
    return _FADE_MASK_CACHE


def _left_strip_avg_color(jacket: Image.Image) -> tuple[int, int, int]:
    w, h = jacket.size
    crop_w = max(1, w // 5)
    avg_img = jacket.crop((0, 0, crop_w, h)).convert("RGB").resize((1, 1), Image.Resampling.BOX)
    return avg_img.getpixel((0, 0))


def _is_dark_rgb(rgb: tuple[int, int, int]) -> bool:
    return (rgb[0] * 0.299 + rgb[1] * 0.587 + rgb[2] * 0.114) < 155


def _contrast_palette(avg_rgb: tuple[int, int, int]) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int], tuple[int, int, int, int]]:
    """Return (primary_text, secondary_text, panel_tint) for readable tile text."""
    if _is_dark_rgb(avg_rgb):
        return (255, 255, 255, 255), (218, 224, 240, 235), (22, 24, 34)
    return (24, 26, 36, 255), (58, 62, 78, 240), (242, 244, 250)


def _format_tile_date(ts: int) -> str:
    sec = normalize_timestamp_seconds(ts)
    if sec <= 0:
        return "—"
    return datetime.datetime.fromtimestamp(sec, tz=datetime.timezone.utc).strftime("%Y-%m-%d")


def _draw_tile(
    entry: dict,
    rank: int,
    mask: Image.Image,
    table_img: Optional[Image.Image],
) -> Image.Image:
    w, h = 560, 270
    jpath = find_jacket_path(entry["song_id"])
    jacket = _open_rgba(jpath) if jpath is not None else None

    if jacket is not None:
        avg_rgb = _left_strip_avg_color(jacket)
        jk_sq = jacket.resize((270, 270), Image.Resampling.LANCZOS)
    else:
        avg_rgb = (42, 48, 76)
        jk_sq = Image.new("RGBA", (270, 270), (54, 60, 92, 255))

    fg_main, fg_sub, _ = _contrast_palette(avg_rgb)

    tile = Image.new("RGBA", (w, h), (*avg_rgb, 255))
    tile.alpha_composite(jk_sq, (290, 0))
    fade_overlay = Image.new("RGBA", (230, 270), (*avg_rgb, 255))
    fade_overlay.putalpha(_get_fade_alpha_mask())
    tile.alpha_composite(fade_overlay, (290, 0))

    # Subtle contrast scrim on left text zone so bright or high-contrast jackets stay legible
    scrim = Image.new("RGBA", (315, h), (0, 0, 0, 28) if _is_dark_rgb(avg_rgb) else (255, 255, 255, 34))
    tile.alpha_composite(scrim, (0, 0))

    invisible = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    tile = Image.composite(tile, invisible, mask)

    # Difficulty bar (14x48 at 24, 24)
    diff_id = int(entry["difficulty"])
    diff_file = DIFF_FILES.get(diff_id)
    diff_bar = _open_rgba(THEME_DIR / "diff" / diff_file) if diff_file else None
    if diff_bar is not None:
        tile.alpha_composite(diff_bar.resize((14, 48), Image.Resampling.LANCZOS), (24, 24))
    else:
        bdraw = ImageDraw.Draw(tile)
        bar_col = (242, 198, 56, 255) if diff_id == 4 else (160, 120, 255, 255)
        bdraw.rounded_rectangle((24, 24, 38, 72), radius=4, fill=bar_col)

    draw = ImageDraw.Draw(tile)
    f_title = _get_font("NotoSansCJK-Regular.otf", 33)
    f_score = _get_font("Exo-Medium.ttf", 38)
    f_rank = _get_font("Exo-Medium.ttf", 26)
    f_pfl_lbl = _get_font("Andrea.otf", 24)
    f_pfl_val = _get_font("Kazesawa-Regular.ttf", 24)
    f_pfl_sh = _get_font("Kazesawa-Regular.ttf", 17)
    f_meta_lbl = _get_font("Exo-Medium.ttf", 19)
    f_meta_val = _get_font("Kazesawa-Regular.ttf", 22)
    f_arrow = _get_font("Andrea.otf", 26)
    f_pill = _get_font("Exo-SemiBold.ttf", 15)

    # Top-right rank pill (#1..#39) over jacket (jacket bottom-right stays clean)
    rank_str = f"#{rank}"
    draw.text((542, 16), rank_str, fill=(255, 255, 255, 255), font=f_rank, anchor="rt", stroke_width=2, stroke_fill=(15, 16, 26, 240))

    # Title + Score + DIFF & CLEAR pills beside score
    title_str = _text_fit(draw, entry["title"], 385, f_title)
    draw.text((46, 22), title_str, fill=fg_main, font=f_title)

    score_str = format_score_arcaea(entry["score"])
    is_max_pm = entry["score"] >= 10_000_000 and entry["near"] == 0 and entry["miss"] == 0
    if is_max_pm:
        draw.text((48, 72), score_str, fill=(0, 180, 210, 185), font=f_score)
    draw.text((46, 70), score_str, fill=fg_main, font=f_score)
    score_w = int(draw.textlength(score_str, font=f_score))

    pill_x = 46 + score_w + 12
    pill_y1, pill_y2 = 77, 102
    diff_lbl = difficulty_name(diff_id)
    diff_pill_colors = {
        0: (52, 168, 226, 235),
        1: (76, 174, 84, 235),
        2: (146, 68, 194, 235),
        3: (192, 42, 72, 235),
        4: (212, 158, 36, 235),
    }
    diff_fill = diff_pill_colors.get(diff_id, (120, 120, 140, 235))
    dw = int(draw.textlength(diff_lbl, font=f_pill)) + 14
    draw.rounded_rectangle((pill_x, pill_y1, pill_x + dw, pill_y2), radius=6, fill=diff_fill)
    draw.text((pill_x + dw / 2, (pill_y1 + pill_y2) / 2), diff_lbl, fill=(255, 255, 255, 255), font=f_pill, anchor="mm")

    ct_short = clear_type_short(entry["clear_type"])
    ct_colors = {
        "PM": (42, 185, 224, 235),
        "FR": (162, 82, 224, 235),
        "HC": (205, 55, 76, 235),
        "EC": (68, 178, 108, 235),
        "NC": (56, 118, 212, 235),
        "TL": (110, 114, 128, 230),
    }
    ct_fill = ct_colors.get(ct_short, (68, 74, 96, 230))
    cx = pill_x + dw + 6
    cw = int(draw.textlength(ct_short, font=f_pill)) + 14
    draw.rounded_rectangle((cx, pill_y1, cx + cw, pill_y2), radius=6, fill=ct_fill)
    draw.text((cx + cw / 2, (pill_y1 + pill_y2) / 2), ct_short, fill=(255, 255, 255, 255), font=f_pill, anchor="mm")

    # P / F / L counts with sleek 3px underlines cleanly beneath digits
    draw.text((48, 124), "P", fill=fg_main, font=f_pfl_lbl)
    p_str = str(entry["pure"])
    draw.text((76, 124), p_str, fill=fg_main, font=f_pfl_val)
    pw = int(draw.textlength(p_str, font=f_pfl_val))
    draw.text((82 + pw, 129), f"(+{entry['shiny']})", fill=fg_sub, font=f_pfl_sh)
    draw.rounded_rectangle((48, 155, 222, 158), radius=2, fill=(52, 196, 255, 225))

    draw.text((48, 166), "F", fill=fg_main, font=f_pfl_lbl)
    draw.text((76, 166), str(entry["near"]), fill=fg_main, font=f_pfl_val)
    draw.rounded_rectangle((48, 197, 222, 200), radius=2, fill=(235, 186, 86, 225))

    draw.text((48, 208), "L", fill=fg_main, font=f_pfl_lbl)
    draw.text((76, 208), str(entry["miss"]), fill=fg_main, font=f_pfl_val)
    draw.rounded_rectangle((48, 239, 222, 242), radius=2, fill=(216, 86, 118, 225))

    # PTT & Date on crisp aligned horizontal baseline
    draw.text((246, 126), "PTT", fill=fg_sub, font=f_meta_lbl)
    cc_lbl = f"{entry['constant']:.1f}" if entry["constant"] > 0 else "?"
    draw.text((246, 166), cc_lbl, fill=fg_main, font=f_meta_val, anchor="lm")
    cc_w = int(draw.textlength(cc_lbl, font=f_meta_val))
    draw.text((254 + cc_w, 165), ">", fill=fg_sub, font=f_arrow, anchor="lm")
    draw.text((274 + cc_w, 166), f"{entry['rating']:.3f}", fill=fg_main, font=f_meta_val, anchor="lm")

    draw.text((246, 196), "DATE", fill=fg_sub, font=f_meta_lbl)
    draw.text((246, 223), _format_tile_date(entry["time_played"]), fill=fg_main, font=f_meta_val)

    return tile


def _query_b30n_data(game_db_path: Path, user_id: int) -> dict:
    conn = sqlite3.connect(f"file:{game_db_path}?mode=ro", uri=True, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        user_cols = {r[1] for r in conn.execute("PRAGMA table_info(user)").fetchall()}
        hide_col = "COALESCE(is_hide_rating, 0)" if "is_hide_rating" in user_cols else "0"
        uncap_ov_col = "COALESCE(is_char_uncapped_override, 0)" if "is_char_uncapped_override" in user_cols else "0"
        uncap_col = "COALESCE(is_char_uncapped, 0)" if "is_char_uncapped" in user_cols else "0"
        row = conn.execute(
            f"""
            SELECT user_id, name, user_code, rating_ptt, character_id,
                   {hide_col} AS is_hide_rating,
                   {uncap_ov_col} AS is_char_uncapped_override,
                   {uncap_col} AS is_char_uncapped
            FROM user WHERE user_id = ?
            """,
            (int(user_id),),
        ).fetchone()
        if row is None:
            raise ValidationError("Account does not exist.")

        raw_ptt = -1 if int(row["is_hide_rating"]) == 1 or row["rating_ptt"] is None else int(row["rating_ptt"])
        rank_row = conn.execute(
            f"""
            SELECT COUNT(*) FROM user
            WHERE (CASE WHEN {hide_col} = 1 THEN -1 ELSE COALESCE(rating_ptt, -1) END)
                > (CASE WHEN ? < 0 THEN -1 ELSE ? END)
            """,
            (raw_ptt, raw_ptt),
        ).fetchone()
        server_rank = (int(rank_row[0]) + 1) if raw_ptt >= 0 else None

        if "best_score" not in tables:
            raise ValidationError("The account does not have enough score data for B30.")

        has_chart = "chart" in tables
        chart_join = "LEFT JOIN chart c ON c.song_id = b.song_id" if has_chart else ""
        chart_cols = (
            "c.name AS title, c.rating_pst, c.rating_prs, c.rating_ftr, c.rating_byn, c.rating_etr"
            if has_chart
            else "b.song_id AS title, -1 AS rating_pst, -1 AS rating_prs, -1 AS rating_ftr, -1 AS rating_byn, -1 AS rating_etr"
        )
        score_rows = conn.execute(
            f"""
            SELECT
                b.song_id, b.difficulty, b.score, COALESCE(b.best_clear_type, b.clear_type) AS ct,
                b.rating, b.perfect_count, b.shiny_perfect_count, b.near_count, b.miss_count, b.time_played,
                {chart_cols}
            FROM best_score b
            {chart_join}
            WHERE b.user_id = ? AND b.rating > 0
            ORDER BY b.rating DESC, b.score DESC
            LIMIT 39
            """,
            (int(user_id),),
        ).fetchall()
        if not score_rows:
            raise ValidationError("The account does not have enough score data for B30.")

        r10_avg = 0.0
        if "recent30" in tables:
            r10 = conn.execute(
                "SELECT rating FROM recent30 WHERE user_id = ? AND rating > 0 ORDER BY rating DESC LIMIT 10",
                (int(user_id),),
            ).fetchall()
            if r10:
                r10_avg = sum(float(r["rating"]) for r in r10) / len(r10)
    finally:
        conn.close()

    entries = []
    cc_cols = ("rating_pst", "rating_prs", "rating_ftr", "rating_byn", "rating_etr")
    for sr in score_rows:
        diff_id = int(sr["difficulty"])
        const = 0.0
        if 0 <= diff_id < len(cc_cols):
            raw_cc = sr[cc_cols[diff_id]]
            if raw_cc is not None and int(raw_cc) > 0:
                const = round(int(raw_cc) / 10.0, 1)
        entries.append(
            {
                "song_id": str(sr["song_id"]),
                "title": str(sr["title"] or sr["song_id"]),
                "difficulty": diff_id,
                "score": int(sr["score"] or 0),
                "clear_type": int(sr["ct"] or 0),
                "rating": float(sr["rating"] or 0.0),
                "pure": int(sr["perfect_count"] or 0),
                "shiny": int(sr["shiny_perfect_count"] or 0),
                "near": int(sr["near_count"] or 0),
                "miss": int(sr["miss_count"] or 0),
                "time_played": int(sr["time_played"] or 0),
                "constant": const,
            }
        )

    top30 = entries[:30]
    b30_avg = sum(e["rating"] for e in top30) / 30.0
    theory_max = (sum(e["rating"] for e in top30) + sum(e["rating"] for e in top30[:10])) / 40.0
    return {
        "username": str(row["name"]),
        "user_code": str(row["user_code"]),
        "raw_ptt": raw_ptt,
        "server_rank": server_rank,
        "character_id": int(row["character_id"]) if row["character_id"] is not None else 0,
        "is_uncapped": bool(row["is_char_uncapped_override"]) or bool(row["is_char_uncapped"]),
        "b30_avg": b30_avg,
        "r10_avg": r10_avg,
        "theory_max": theory_max,
        "entries": entries,
    }


def _render_b30n_sync(game_db_path: Path, user_id: int) -> bytes:
    data = _query_b30n_data(game_db_path, user_id)

    bg_path = THEME_DIR / "b30" / "B30.png"
    base = _open_rgba(bg_path)
    if base is None:
        base = Image.new("RGBA", (2000, 4700), (26, 28, 52, 255))

    w, _ = base.size

    # Partner icon (250x250 at 75, 130)
    icon_path = find_partner_icon_path(data["character_id"], data["is_uncapped"]) or find_partner_icon_path(0, False)
    if icon_path is not None:
        icon_img = _open_rgba(icon_path)
        if icon_img is not None:
            base.alpha_composite(icon_img.resize((250, 250), Image.Resampling.LANCZOS), (75, 130))

    # PTT diamond badge (150x150 at 200, 280)
    ptt_img = _open_rgba(IMG_DIR / _ptt_badge_filename(data["raw_ptt"]))
    if ptt_img is not None:
        base.alpha_composite(ptt_img.resize((150, 150), Image.Resampling.LANCZOS), (200, 280))

    draw = ImageDraw.Draw(base)
    f_ptt_hi = _get_font("Exo-Medium.ttf", 50)
    f_ptt_lo = _get_font("Exo-Medium.ttf", 40)
    if data["raw_ptt"] >= 0:
        hi, lo = f"{data['raw_ptt'] / 100:.2f}".split(".")
        draw.text((272, 370), hi, fill=(255, 255, 255, 255), font=f_ptt_hi, anchor="rs", stroke_width=3, stroke_fill=(10, 10, 18, 255))
        draw.text((272, 370), "." + lo, fill=(255, 255, 255, 255), font=f_ptt_lo, anchor="ls", stroke_width=3, stroke_fill=(10, 10, 18, 255))
    else:
        draw.text((275, 375), "--", fill=(255, 255, 255, 255), font=f_ptt_hi, anchor="mb", stroke_width=3, stroke_fill=(10, 10, 18, 255))

    # Header user text
    f_name = _get_font("Exo-Medium.ttf", 92)
    f_id = _get_font("Exo-Medium.ttf", 52)
    f_stat = _get_font("Exo-Medium.ttf", 64)
    f_right_sm = _get_font("Exo-Medium.ttf", 40)

    uname = _text_fit(draw, data["username"], 830, f_name)
    draw.text((365, 275), uname, fill=(255, 255, 255, 255), font=f_name, anchor="lb")
    draw.text((370, 355), f"ID: {data['user_code']}", fill=(215, 224, 248, 240), font=f_id, anchor="lb")

    # Right sub-banner & Akaine rank/max (cleanly below baked "Player Info" box)
    rank_line = f"Rank: #{data['server_rank']}" if data["server_rank"] else "Rank: Hidden"
    draw.text((100, 540), f"Best 30: {data['b30_avg']:.4f}", fill=(255, 255, 255, 255), font=f_stat, anchor="lb")
    draw.text((760, 540), f"Recent 10: {data['r10_avg']:.4f}", fill=(255, 255, 255, 255), font=f_stat, anchor="lb")
    draw.text((1900, 540), f"{rank_line}  ·  Max: {data['theory_max']:.3f}", fill=(205, 222, 255, 245), font=f_right_sm, anchor="rb")

    # Load tile mask & overlay once
    mask_path = THEME_DIR / "b30" / "mask.png"
    if mask_path.is_file():
        mask = Image.open(mask_path).convert("L")
    else:
        mask = Image.new("L", (560, 270), 255)
    table_img = _open_rgba(THEME_DIR / "b30" / "table.png")
    divider_img = _open_rgba(THEME_DIR / "b30" / "Divider.png")

    entries = data["entries"]
    y = 640
    x = 100
    last_bottom = y
    for idx, entry in enumerate(entries):
        if idx >= 39:
            break
        if idx > 0 and idx % 3 == 0:
            y += 300
            x = 100
        elif idx > 0:
            x += 620

        if idx == 30:
            y += 100
            if divider_img is not None:
                div_x = (w - divider_img.width) // 2
                base.alpha_composite(divider_img, (div_x, y - 68))

        tile = _draw_tile(entry, idx + 1, mask, table_img)
        base.alpha_composite(tile, (x, y))
        last_bottom = y + 270

    # Trim excess blank height if player has fewer than 39 scores, keeping neat footer margin
    final_h = min(base.height, max(1200, last_bottom + 90))
    if final_h < base.height:
        base = base.crop((0, 0, w, final_h))

    draw = ImageDraw.Draw(base)
    f_footer = _get_font("Exo-Regular.ttf", 26)
    ts_str = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    draw.text((w - 60, final_h - 38), f"Demiurge · Akaine // {ts_str}", fill=(210, 218, 242, 185), font=f_footer, anchor="rb")

    out = io.BytesIO()
    base.convert("RGB").save(out, format="JPEG", quality=92, optimize=True)
    return out.getvalue()


def render_b30n(game_db_path: Path, user_id: int) -> bytes:
    with _B30N_SLOT:
        return _render_b30n_sync(game_db_path, user_id)


def _get_fade_alpha_mask_landscape() -> Image.Image:
    global _FADE_MASK_LANDSCAPE_CACHE
    if _FADE_MASK_LANDSCAPE_CACHE is not None:
        return _FADE_MASK_LANDSCAPE_CACHE
    ramp = Image.new("L", (175, 1), 0)
    px = ramp.load()
    for x in range(175):
        px[x, 0] = max(0, 255 - int(x * 255 / 162))
    _FADE_MASK_LANDSCAPE_CACHE = ramp.resize((175, 208), Image.Resampling.NEAREST)
    return _FADE_MASK_LANDSCAPE_CACHE


def _get_tile_mask_landscape() -> Image.Image:
    global _TILE_MASK_LANDSCAPE_CACHE
    if _TILE_MASK_LANDSCAPE_CACHE is not None:
        return _TILE_MASK_LANDSCAPE_CACHE
    mask = Image.new("L", (476, 208), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 475, 207), radius=15, fill=255)
    _TILE_MASK_LANDSCAPE_CACHE = mask
    return _TILE_MASK_LANDSCAPE_CACHE


def _find_partner_full_path(character_id: int, is_uncapped: bool) -> Optional[Path]:
    if not CHAR_DIR.is_dir():
        return None
    cid = str(character_id)
    names = (
        [f"1080/{cid}u.png", f"1080/{cid}.png", f"{cid}u.png", f"{cid}.png"]
        if is_uncapped
        else [f"1080/{cid}.png", f"1080/{cid}u.png", f"{cid}.png", f"{cid}u.png"]
    )
    for n in names:
        p = CHAR_DIR / n
        if p.is_file():
            return p
    return None


def _draw_landscape_tile(entry: dict, rank: int, mask: Image.Image) -> Image.Image:
    w, h = 476, 208
    jpath = find_jacket_path(entry["song_id"])
    jacket = _open_rgba(jpath) if jpath is not None else None

    if jacket is not None:
        avg_rgb = _left_strip_avg_color(jacket)
        jk_sq = jacket.resize((208, 208), Image.Resampling.LANCZOS)
    else:
        avg_rgb = (42, 48, 76)
        jk_sq = Image.new("RGBA", (208, 208), (54, 60, 92, 255))

    fg_main, fg_sub, _ = _contrast_palette(avg_rgb)

    tile = Image.new("RGBA", (w, h), (*avg_rgb, 255))
    tile.alpha_composite(jk_sq, (268, 0))
    fade_overlay = Image.new("RGBA", (175, 208), (*avg_rgb, 255))
    fade_overlay.putalpha(_get_fade_alpha_mask_landscape())
    tile.alpha_composite(fade_overlay, (268, 0))

    scrim = Image.new("RGBA", (276, h), (0, 0, 0, 30) if _is_dark_rgb(avg_rgb) else (255, 255, 255, 34))
    tile.alpha_composite(scrim, (0, 0))

    invisible = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    tile = Image.composite(tile, invisible, mask)

    # Difficulty bar (10x38 at 18, 17)
    diff_id = int(entry["difficulty"])
    diff_file = DIFF_FILES.get(diff_id)
    diff_bar = _open_rgba(THEME_DIR / "diff" / diff_file) if diff_file else None
    if diff_bar is not None:
        tile.alpha_composite(diff_bar.resize((10, 38), Image.Resampling.LANCZOS), (18, 17))
    else:
        bdraw = ImageDraw.Draw(tile)
        bar_col = (242, 198, 56, 255) if diff_id == 4 else (160, 120, 255, 255)
        bdraw.rounded_rectangle((18, 17, 28, 55), radius=3, fill=bar_col)

    draw = ImageDraw.Draw(tile)
    f_title = _get_font("NotoSansCJK-Regular.otf", 25)
    f_score = _get_font("Exo-Medium.ttf", 29)
    f_rank = _get_font("Exo-Medium.ttf", 21)
    f_pfl_lbl = _get_font("Andrea.otf", 19)
    f_pfl_val = _get_font("Kazesawa-Regular.ttf", 19)
    f_pfl_sh = _get_font("Kazesawa-Regular.ttf", 14)
    f_meta_lbl = _get_font("Exo-Medium.ttf", 15)
    f_meta_val = _get_font("Kazesawa-Regular.ttf", 17)
    f_arrow = _get_font("Andrea.otf", 20)
    f_pill = _get_font("Exo-SemiBold.ttf", 13)

    # Rank top-right over jacket
    draw.text((462, 12), f"#{rank}", fill=(255, 255, 255, 255), font=f_rank, anchor="rt", stroke_width=2, stroke_fill=(15, 16, 26, 240))

    # Title + Score + DIFF & CLEAR pills
    title_str = _text_fit(draw, entry["title"], 332, f_title)
    draw.text((34, 15), title_str, fill=fg_main, font=f_title)

    score_str = format_score_arcaea(entry["score"])
    is_max_pm = entry["score"] >= 10_000_000 and entry["near"] == 0 and entry["miss"] == 0
    if is_max_pm:
        draw.text((36, 54), score_str, fill=(0, 180, 210, 185), font=f_score)
    draw.text((34, 52), score_str, fill=fg_main, font=f_score)
    score_w = int(draw.textlength(score_str, font=f_score))

    pill_x = 34 + score_w + 10
    pill_y1, pill_y2 = 57, 78
    diff_lbl = difficulty_name(diff_id)
    diff_pill_colors = {
        0: (52, 168, 226, 235),
        1: (76, 174, 84, 235),
        2: (146, 68, 194, 235),
        3: (192, 42, 72, 235),
        4: (212, 158, 36, 235),
    }
    diff_fill = diff_pill_colors.get(diff_id, (120, 120, 140, 235))
    dw = int(draw.textlength(diff_lbl, font=f_pill)) + 12
    draw.rounded_rectangle((pill_x, pill_y1, pill_x + dw, pill_y2), radius=5, fill=diff_fill)
    draw.text((pill_x + dw / 2, (pill_y1 + pill_y2) / 2), diff_lbl, fill=(255, 255, 255, 255), font=f_pill, anchor="mm")

    ct_short = clear_type_short(entry["clear_type"])
    ct_colors = {
        "PM": (42, 185, 224, 235),
        "FR": (162, 82, 224, 235),
        "HC": (205, 55, 76, 235),
        "EC": (68, 178, 108, 235),
        "NC": (56, 118, 212, 235),
        "TL": (110, 114, 128, 230),
    }
    ct_fill = ct_colors.get(ct_short, (68, 74, 96, 230))
    cx = pill_x + dw + 5
    cw = int(draw.textlength(ct_short, font=f_pill)) + 12
    draw.rounded_rectangle((cx, pill_y1, cx + cw, pill_y2), radius=5, fill=ct_fill)
    draw.text((cx + cw / 2, (pill_y1 + pill_y2) / 2), ct_short, fill=(255, 255, 255, 255), font=f_pill, anchor="mm")

    # P / F / L with 2px underlines cleanly below numbers
    draw.text((36, 94), "P", fill=fg_main, font=f_pfl_lbl)
    p_str = str(entry["pure"])
    draw.text((58, 94), p_str, fill=fg_main, font=f_pfl_val)
    pw = int(draw.textlength(p_str, font=f_pfl_val))
    draw.text((62 + pw, 98), f"(+{entry['shiny']})", fill=fg_sub, font=f_pfl_sh)
    draw.rounded_rectangle((36, 119, 178, 121), radius=1, fill=(52, 196, 255, 225))

    draw.text((36, 128), "F", fill=fg_main, font=f_pfl_lbl)
    draw.text((58, 128), str(entry["near"]), fill=fg_main, font=f_pfl_val)
    draw.rounded_rectangle((36, 153, 178, 155), radius=1, fill=(235, 186, 86, 225))

    draw.text((36, 162), "L", fill=fg_main, font=f_pfl_lbl)
    draw.text((58, 162), str(entry["miss"]), fill=fg_main, font=f_pfl_val)
    draw.rounded_rectangle((36, 187, 178, 189), radius=1, fill=(216, 86, 118, 225))

    # PTT & Date on right-center
    draw.text((196, 95), "PTT", fill=fg_sub, font=f_meta_lbl)
    cc_lbl = f"{entry['constant']:.1f}" if entry["constant"] > 0 else "?"
    draw.text((196, 127), cc_lbl, fill=fg_main, font=f_meta_val, anchor="lm")
    cc_w = int(draw.textlength(cc_lbl, font=f_meta_val))
    draw.text((202 + cc_w, 126), ">", fill=fg_sub, font=f_arrow, anchor="lm")
    draw.text((218 + cc_w, 127), f"{entry['rating']:.3f}", fill=fg_main, font=f_meta_val, anchor="lm")

    draw.text((196, 148), "DATE", fill=fg_sub, font=f_meta_lbl)
    draw.text((196, 170), _format_tile_date(entry["time_played"]), fill=fg_main, font=f_meta_val)

    return tile


def _make_landscape_backdrop(w: int, h: int, entries: list[dict]) -> Image.Image:
    col = Image.new("RGBA", (1, h), (11, 15, 40, 255))
    cpx = col.load()
    top, mid, bot = (12, 15, 44), (34, 46, 92), (9, 13, 34)
    for y in range(h):
        t = y / max(1, h - 1)
        if t < 0.4:
            k = t / 0.4
            c1, c2 = top, mid
        else:
            k = (t - 0.4) / 0.6
            c1, c2 = mid, bot
        cpx[0, y] = (
            int(c1[0] * (1 - k) + c2[0] * k),
            int(c1[1] * (1 - k) + c2[1] * k),
            int(c1[2] * (1 - k) + c2[2] * k),
            255,
        )
    bg = col.resize((w, h), Image.Resampling.BILINEAR)

    jackets = []
    for e in entries[:10]:
        jp = find_jacket_path(e["song_id"])
        if jp is not None:
            jk = _open_rgba(jp)
            if jk is not None:
                jackets.append(jk)
        if len(jackets) >= 8:
            break

    if jackets:
        # Render mosaic at 1/4 scale for speed then upscale + blur cleanly
        sw, sh = w // 4, h // 4
        mosaic = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        cell = 135
        idx = 0
        for yy in range(-20, sh, cell):
            for xx in range(-20, sw, cell):
                jk = jackets[idx % len(jackets)].resize((cell + 12, cell + 12), Image.Resampling.BILINEAR)
                jk = ImageEnhance.Brightness(jk).enhance(0.55)
                jk.putalpha(42)
                mosaic.paste(jk, (xx, yy), jk)
                idx += 1
        mosaic = mosaic.filter(ImageFilter.GaussianBlur(10)).resize((w, h), Image.Resampling.BILINEAR)
        bg = Image.alpha_composite(bg, mosaic)

    glow = Image.new("RGBA", (w // 4, h // 4), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-40, -20, 260, 260), fill=(140, 75, 255, 78))
    gd.ellipse((360, -40, 680, 240), fill=(90, 155, 255, 72))
    gd.ellipse((140, 200, 520, 460), fill=(65, 130, 240, 48))
    glow = glow.filter(ImageFilter.GaussianBlur(28)).resize((w, h), Image.Resampling.BILINEAR)
    return Image.alpha_composite(bg, glow)


def _render_b30n2_sync(game_db_path: Path, user_id: int) -> bytes:
    data = _query_b30n_data(game_db_path, user_id)
    entries = data["entries"][:30]

    w, h = 2560, 1600
    base = _make_landscape_backdrop(w, h, entries)

    # Top Glass Header (x=50..2510, y=24..204)
    hx1, hy1, hx2, hy2 = 50, 24, 2510, 204
    hw, hh = hx2 - hx1, hy2 - hy1
    hdr_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(hdr_layer).rounded_rectangle(
        (hx1, hy1, hx2, hy2),
        radius=20,
        fill=(18, 22, 48, 188),
        outline=(210, 224, 255, 76),
        width=2,
    )

    # Subtle partner illustration inside right edge of header
    full_path = _find_partner_full_path(data["character_id"], data["is_uncapped"])
    if full_path is not None:
        full_img = _open_rgba(full_path)
        if full_img is not None:
            th = 340
            tw = max(1, int(full_img.width * (th / full_img.height)))
            fi = full_img.resize((tw, th), Image.Resampling.LANCZOS)
            hdr_crop = Image.new("RGBA", (hw, hh), (0, 0, 0, 0))
            hdr_crop.alpha_composite(fi, (hw - tw - 12, -26))
            hdr_mask = Image.new("L", (hw, hh), 0)
            ImageDraw.Draw(hdr_mask).rounded_rectangle((0, 0, hw - 1, hh - 1), radius=20, fill=145)
            masked_art = Image.composite(hdr_crop, Image.new("RGBA", (hw, hh), (0, 0, 0, 0)), hdr_mask)
            hdr_layer.alpha_composite(masked_art, (hx1, hy1))

    base = Image.alpha_composite(base, hdr_layer)

    # Diamond partner icon + PTT diamond badge
    av_x, av_y, av_s = 82, 46, 136
    icon_path = find_partner_icon_path(data["character_id"], data["is_uncapped"]) or find_partner_icon_path(0, False)
    if icon_path is not None:
        ci = _open_rgba(icon_path)
        if ci is not None:
            ci = ci.resize((av_s, av_s), Image.Resampling.LANCZOS)
            dmask = Image.new("L", (av_s, av_s), 0)
            ImageDraw.Draw(dmask).polygon(
                [(av_s // 2, 0), (av_s, av_s // 2), (av_s // 2, av_s), (0, av_s // 2)],
                fill=255,
            )
            base.paste(ci, (av_x, av_y), dmask)
            ImageDraw.Draw(base).polygon(
                [(av_x + av_s // 2, av_y), (av_x + av_s, av_y + av_s // 2), (av_x + av_s // 2, av_y + av_s), (av_x, av_y + av_s // 2)],
                outline=(225, 232, 255, 210),
                width=2,
            )

    ptt_img = _open_rgba(IMG_DIR / _ptt_badge_filename(data["raw_ptt"]))
    if ptt_img is not None:
        base.alpha_composite(ptt_img.resize((86, 86), Image.Resampling.LANCZOS), (154, 108))

    draw = ImageDraw.Draw(base)
    f_ptt_hi = _get_font("Exo-SemiBold.ttf", 28)
    f_ptt_lo = _get_font("Exo-SemiBold.ttf", 22)
    if data["raw_ptt"] >= 0:
        hi, lo = f"{data['raw_ptt'] / 100:.2f}".split(".")
        draw.text((196, 159), hi, fill=(255, 255, 255, 255), font=f_ptt_hi, anchor="rs", stroke_width=2, stroke_fill=(10, 10, 18, 255))
        draw.text((196, 159), "." + lo, fill=(255, 255, 255, 255), font=f_ptt_lo, anchor="ls", stroke_width=2, stroke_fill=(10, 10, 18, 255))
    else:
        draw.text((197, 161), "--", fill=(255, 255, 255, 255), font=f_ptt_hi, anchor="mb", stroke_width=2, stroke_fill=(10, 10, 18, 255))

    # User info left-center
    f_tag = _get_font("Exo-SemiBold.ttf", 17)
    f_name = _get_font("Exo-Medium.ttf", 52)
    f_id = _get_font("Exo-Regular.ttf", 25)
    draw.text((262, 52), "AKAINE // BEST 30 · 16:10", fill=(204, 172, 255, 235), font=f_tag)
    uname = _text_fit(draw, data["username"], 740, f_name)
    draw.text((262, 76), uname, fill=(255, 255, 255, 255), font=f_name)
    draw.text((264, 142), f"ID: {data['user_code']}", fill=(208, 218, 245, 230), font=f_id)

    # Header 4 stat columns
    f_st_lbl = _get_font("Exo-SemiBold.ttf", 18)
    f_st_val = _get_font("Exo-Medium.ttf", 44)
    rank_val = f"#{data['server_rank']}" if data["server_rank"] else "Hidden"
    stats = [
        ("BEST 30", f"{data['b30_avg']:.4f}"),
        ("RECENT 10", f"{data['r10_avg']:.4f}"),
        ("MAX THEORY", f"{data['theory_max']:.4f}"),
        ("SERVER RANK", rank_val),
    ]
    sx1, sx2 = 1090, 2290
    col_w = (sx2 - sx1) / len(stats)
    for i, (lbl, val) in enumerate(stats):
        cx = int(sx1 + i * col_w + col_w / 2)
        if i > 0:
            lx = int(sx1 + i * col_w)
            draw.line((lx, 56, lx, 172), fill=(210, 222, 255, 68), width=1)
        draw.text((cx, 74), lbl, fill=(190, 206, 244, 225), font=f_st_lbl, anchor="mm")
        draw.text((cx, 128), val, fill=(255, 255, 255, 255), font=f_st_val, anchor="mm")

    # 5x6 Best 30 Grid
    mask = _get_tile_mask_landscape()
    start_x, start_y = 50, 224
    tile_w, tile_h = 476, 208
    gap_x, gap_y = 20, 16
    for idx, entry in enumerate(entries):
        col = idx % 5
        row = idx // 5
        tx = start_x + col * (tile_w + gap_x)
        ty = start_y + row * (tile_h + gap_y)
        tile = _draw_landscape_tile(entry, idx + 1, mask)
        base.alpha_composite(tile, (tx, ty))

    # Footer legend + timestamp
    draw = ImageDraw.Draw(base)
    f_leg = _get_font("Exo-SemiBold.ttf", 17)
    legend_items = [
        ("PST", (52, 168, 226, 235)),
        ("PRS", (76, 174, 84, 235)),
        ("FTR", (146, 68, 194, 235)),
        ("BYD", (192, 42, 72, 235)),
        ("ETR", (212, 158, 36, 235)),
    ]
    lx = 54
    for lbl, col_rgba in legend_items:
        draw.rounded_rectangle((lx, 1564, lx + 44, 1586), radius=5, fill=col_rgba)
        draw.text((lx + 22, 1575), lbl, fill=(255, 255, 255, 255), font=f_leg, anchor="mm")
        lx += 54

    f_footer = _get_font("Exo-Regular.ttf", 20)
    ts_str = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    draw.text((2506, 1575), f"Demiurge · Akaine // 16:10 B30 // {ts_str}", fill=(205, 215, 240, 195), font=f_footer, anchor="rm")

    out = io.BytesIO()
    base.convert("RGB").save(out, format="JPEG", quality=92, optimize=True)
    return out.getvalue()


def render_b30n2(game_db_path: Path, user_id: int) -> bytes:
    with _B30N_SLOT:
        return _render_b30n2_sync(game_db_path, user_id)
