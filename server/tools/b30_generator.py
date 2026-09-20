import sqlite3
import os
import time
import math
import glob
import urllib.request
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

SERVER_ROOT = Path(os.environ.get("LYGUS_SERVER_ROOT", Path(__file__).resolve().parents[1]))
DB_PATH = os.environ.get("LYGUS_GAME_DB", str(SERVER_ROOT / "database" / "arcaea_database.db"))
JACKETS_PATH = os.environ.get("LYGUS_JACKET_ROOT", str(SERVER_ROOT / "assets" / "jackets"))
CHAR_PATH = os.environ.get("LYGUS_CHARACTER_ROOT", str(SERVER_ROOT / "assets" / "char"))
IMG_PATH = os.environ.get("LYGUS_IMAGE_ROOT", str(SERVER_ROOT / "assets" / "img"))

PARTNER_OVERRIDE_PATH = None
ICON_OVERRIDE_PATH = None

OUT_DIR = "/tmp"

FONT_DIR = "/tmp/b30_fonts"
os.makedirs(FONT_DIR, exist_ok=True)

FONT_REG = os.path.join(FONT_DIR, "NotoSans-Regular.ttf")
FONT_BOLD = os.path.join(FONT_DIR, "NotoSans-Bold.ttf")
FONT_TITLE = os.path.join(FONT_DIR, "Ndot57-Regular.otf")

SYSTEM_FONT_REG = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

SYSTEM_FONT_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

def download_fonts():
    urls = {
        FONT_REG: "https://github.com/notofonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf",
        FONT_BOLD: "https://github.com/notofonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf",
        FONT_TITLE: "https://raw.githubusercontent.com/xeji01/nothingfont/main/fonts/Ndot57-Regular.otf",
    }

    for path, url in urls.items():
        if os.path.exists(path) and os.path.getsize(path) > 10000:
            continue

        try:
            urllib.request.urlretrieve(url, path)
        except Exception:
            pass

def pick_font_path(bold=False):
    primary = FONT_BOLD if bold else FONT_REG
    if os.path.exists(primary) and os.path.getsize(primary) > 10000:
        return primary
    for p in SYSTEM_FONT_BOLD if bold else SYSTEM_FONT_REG:
        if os.path.exists(p):
            return p
    return None

def F(size, bold=False):
    path = pick_font_path(bold)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()

def get_clear_type(ct):
    return {0: "TL", 1: "NC", 2: "FR", 3: "PM", 4: "EC", 5: "HC"}.get(ct, "NC")

def get_diff_name(diff):
    return {0: "PST", 1: "PRS", 2: "FTR", 3: "BYD", 4: "ETR"}.get(diff, "?")

def get_diff_color(diff):
    return {
        0: (78, 185, 255),
        1: (55, 210, 105),
        2: (185, 80, 255),
        3: (255, 75, 95),
        4: (255, 216, 68),
    }.get(diff, (190, 190, 210))

def score_format(score):
    sc = str(int(score)).zfill(8)
    return f"{sc[:2]}'{sc[2:5]}'{sc[5:]}"

def text_fit(draw, text, max_width, font_obj, suffix="..."):
    text = str(text)
    if draw.textlength(text, font=font_obj) <= max_width:
        return text
    while text and draw.textlength(text + suffix, font=font_obj) > max_width:
        text = text[:-1]
    return text + suffix if text else ""

def rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask

def paste_rounded(base, img, x, y, w, h, radius=10):
    img = img.resize((w, h), Image.Resampling.LANCZOS).convert("RGBA")
    mask = rounded_mask((w, h), radius)
    base.paste(img, (x, y), mask)

def alpha_blur_rect(size, box, radius, fill, blur=0):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius=radius, fill=fill)
    if blur > 0:
        layer = layer.filter(ImageFilter.GaussianBlur(blur))
    return layer

def draw_glow(base, box, radius=18, color=(140, 120, 255, 120), blur=24):
    x1, y1, x2, y2 = box
    pad = blur * 3
    layer = Image.new("RGBA", (x2 - x1 + pad * 2, y2 - y1 + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(
        (pad, pad, pad + x2 - x1, pad + y2 - y1),
        radius=radius,
        fill=color,
    )
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    base.alpha_composite(layer, (x1 - pad, y1 - pad))

def glass_panel(base, box, radius=14, fill=(190, 210, 255, 78), outline=(235, 240, 255, 145), glow=False):
    if glow:
        draw_glow(base, box, radius=radius, color=(125, 145, 255, 80), blur=18)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=1)
    x1, y1, x2, y2 = box
    d.rounded_rectangle(
        (x1 + 1, y1 + 1, x2 - 1, y1 + 26),
        radius=radius,
        fill=(255, 255, 255, 26),
    )
    d.line((x1 + 8, y1 + 1, x2 - 8, y1 + 1), fill=(255, 255, 255, 80), width=1)
    base.alpha_composite(layer)

def draw_badge(draw, x, y, text, fill, font_obj):
    text_color = (28, 25, 35) if text in ("PRS", "ETR", "PST") else (255, 255, 255)
    w = int(draw.textlength(text, font=font_obj)) + 16
    h = 24
    draw.rounded_rectangle((x, y, x + w, y + h), radius=6, fill=fill)
    draw.text((x + 8, y + 2), text, fill=text_color, font=font_obj)
    return w

def load_jacket(song_id):
    names = [f"{song_id}.jpg", f"{song_id}.png", f"dl_{song_id}.jpg", f"dl_{song_id}.png"]
    for n in names:
        p = os.path.join(JACKETS_PATH, n)
        if os.path.exists(p):
            try: return Image.open(p).convert("RGBA")
            except: pass
    return None

def image_area(path):
    try:
        im = Image.open(path)
        return im.width * im.height
    except:
        return 0

def find_character_asset(character_id, want_icon=False, is_uncapped=False):
    if character_id is None:
        return None
    char_id = str(character_id)
    if want_icon:
        if is_uncapped:
            names_to_try = [f"{char_id}u_icon.png", f"{char_id}_icon.png"]
        else:
            names_to_try = [f"{char_id}_icon.png"]
    else:
        if is_uncapped:
            names_to_try = [f"1080/{char_id}u.png", f"1080/{char_id}.png", f"{char_id}u.png", f"{char_id}.png", f"{char_id}u_mp.png", f"{char_id}_mp.png"]
        else:
            names_to_try = [f"1080/{char_id}.png", f"{char_id}.png", f"{char_id}_mp.png", f"{char_id}a_mp.png"]

    for n in names_to_try:
        p = os.path.join(CHAR_PATH, n)
        if os.path.exists(p): return p

    candidates = []
    for ext in ("png", "jpg", "jpeg", "webp"):
        candidates += glob.glob(os.path.join(CHAR_PATH, "**", f"*{char_id}*.{ext}"), recursive=True)
    if not candidates: return None

    if want_icon:
        icon_candidates = [p for p in candidates if "icon" in os.path.basename(p).lower()]
        if icon_candidates: return sorted(icon_candidates, key=image_area)[0]
        return sorted(candidates, key=image_area)[0]

    full_candidates = [p for p in candidates if "icon" not in os.path.basename(p).lower()]
    if full_candidates: return sorted(full_candidates, key=image_area, reverse=True)[0]
    return sorted(candidates, key=image_area, reverse=True)[0]

def load_character(character_id, is_uncapped):
    icon, full = None, None
    icon_path = ICON_OVERRIDE_PATH or find_character_asset(character_id, want_icon=True, is_uncapped=is_uncapped)
    full_path = PARTNER_OVERRIDE_PATH or find_character_asset(character_id, want_icon=False, is_uncapped=is_uncapped)
    
    # Smart Fallback if the database character is missing from the server assets
    if not icon_path or not full_path:
        fallback_id = "16" # Lethe
        icon_path = icon_path or find_character_asset(fallback_id, want_icon=True, is_uncapped=True)
        full_path = full_path or find_character_asset(fallback_id, want_icon=False, is_uncapped=True)

    if icon_path:
        try: icon = Image.open(icon_path).convert("RGBA")
        except: icon = None
    if full_path:
        try: full = Image.open(full_path).convert("RGBA")
        except: full = None
    return icon, full, icon_path, full_path

def make_background(w, h, char_full=None, jackets=None):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    px = img.load()
    top, mid, bottom = (12, 14, 48), (42, 56, 102), (8, 13, 34)
    for y in range(h):
        t = y / h
        if t < 0.38:
            k = t / 0.38
            c1, c2 = top, mid
        else:
            k = (t - 0.38) / 0.62
            c1, c2 = mid, bottom
        r = int(c1[0] * (1 - k) + c2[0] * k)
        g = int(c1[1] * (1 - k) + c2[1] * k)
        b = int(c1[2] * (1 - k) + c2[2] * k)
        for x in range(w):
            px[x, y] = (r, g, b, 255)

    if jackets:
        collage = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        idx = 0
        for yy in range(-120, h, 230):
            for xx in range(-120, w, 230):
                jk = jackets[idx % len(jackets)]
                idx += 1
                if jk:
                    tmp = jk.resize((270, 270), Image.Resampling.LANCZOS)
                    tmp = ImageEnhance.Brightness(tmp).enhance(0.48)
                    tmp = ImageEnhance.Contrast(tmp).enhance(1.2)
                    tmp.putalpha(38)
                    collage.paste(tmp, (xx, yy), tmp)
        collage = collage.filter(ImageFilter.GaussianBlur(26))
        img.alpha_composite(collage)

    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-180, 40, 360, 610), fill=(145, 70, 255, 88))
    gd.ellipse((420, -170, 1220, 560), fill=(130, 165, 255, 90))
    gd.ellipse((680, 160, 1260, 780), fill=(160, 90, 255, 60))
    gd.ellipse((170, 980, 760, 1660), fill=(55, 145, 255, 44))
    glow = glow.filter(ImageFilter.GaussianBlur(95))
    img.alpha_composite(glow)

    if char_full:
        cg = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        cgd = ImageDraw.Draw(cg)
        cgd.ellipse((410, -80, 1180, 560), fill=(160, 150, 255, 105))
        cgd.ellipse((600, 20, 1190, 520), fill=(235, 235, 255, 40))
        cg = cg.filter(ImageFilter.GaussianBlur(70))
        img.alpha_composite(cg)

        target_h = 455
        ratio = target_h / char_full.height
        cw = int(char_full.width * ratio)
        ch = int(char_full.height * ratio)

        cf = char_full.resize((cw, ch), Image.Resampling.LANCZOS)
        cf = ImageEnhance.Brightness(cf).enhance(1.08)
        cf = ImageEnhance.Contrast(cf).enhance(1.07)
        cf = ImageEnhance.Sharpness(cf).enhance(1.08)

        alpha = cf.getchannel("A")
        fade = Image.new("L", (cw, ch), 255)
        fd = ImageDraw.Draw(fade)

        for x in range(cw):
            if x < 170:
                a = int(255 * (x / 170))
                fd.line((x, 0, x, ch), fill=a)

        for y in range(ch):
            if y > ch - 130:
                a = int(255 * max(0, (ch - y) / 130))
                for x in range(cw):
                    old = fade.getpixel((x, y))
                    fade.putpixel((x, y), min(old, a))

        alpha = Image.composite(alpha, Image.new("L", (cw, ch), 0), fade)
        cf.putalpha(alpha)
        cx = w - cw - 10
        img.alpha_composite(cf, (cx, 10))

    d = ImageDraw.Draw(img)
    for i in range(80):
        x = int((math.sin(i * 12.9898) * 0.5 + 0.5) * w)
        y = int((math.sin(i * 78.233 + 2.5) * 0.5 + 0.5) * h)
        r = 1 + i % 3
        a = 45 + (i % 5) * 16
        d.ellipse((x - r, y - r, x + r, y + r), fill=(225, 232, 255, a))
    for i in range(20):
        x = int((i * 193 + 30) % w)
        y = int((i * 127 + 40) % h)
        d.line((x, y, x + 165, y - 80), fill=(205, 190, 255, 42), width=1)
    return img

def draw_centered(draw, center, text, font_obj, fill):
    cx, cy = center
    bbox = draw.textbbox((0, 0), text, font=font_obj)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(
        (cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]),
        text,
        fill=fill,
        font=font_obj,
    )

def draw_header(img, username, user_code, b30_avg, max_ptt, r10_avg, char_icon, rank):
    draw = ImageDraw.Draw(img)
    
    try:
        f_logo = ImageFont.truetype(FONT_TITLE, 54)
    except Exception:
        f_logo = F(54, True)
        
    try:
        f_title = ImageFont.truetype(FONT_TITLE, 43)
    except Exception:
        f_title = F(43, False)
        
    try:
        f_b30 = ImageFont.truetype(FONT_TITLE, 20)
    except Exception:
        f_b30 = F(20, True)
    f_user = F(34, True)
    f_id = F(19, False)
    f_label = F(12, False)
    f_num = F(30, True)

    draw.text((50, 38), "AKAINE", fill=(255, 255, 255, 248), font=f_logo)
    
    logo_bbox = draw.textbbox((0, 0), "AKAINE", font=f_logo)
    logo_w = logo_bbox[2] - logo_bbox[0]
    draw.line((50, 101, 50 + logo_w, 101), fill=(210, 180, 255, 170), width=2)
    
    pb_text = "Player Bests"
    b30_text = "// B30"
    
    pb_bbox = draw.textbbox((0, 0), pb_text, font=f_title)
    pb_w = pb_bbox[2] - pb_bbox[0]
    
    b30_bbox = draw.textbbox((0, 0), b30_text, font=f_b30)
    b30_w = b30_bbox[2] - b30_bbox[0]
    
    # Restore original right_x
    right_x = 560
    
    draw.text((right_x - pb_w, 47), pb_text, fill=(242, 244, 255, 246), font=f_title)
    draw.text((right_x - b30_w, 96), b30_text, fill=(220, 135, 255, 230), font=f_b30)

    av_x, av_y, av_s = 48, 123, 102
    av_glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(av_glow)
    gd.polygon(
        [
            (av_x + av_s//2, av_y - 12),
            (av_x + av_s + 12, av_y + av_s//2),
            (av_x + av_s//2, av_y + av_s + 12),
            (av_x - 12, av_y + av_s//2)
        ],
        fill=(172, 110, 255, 105)
    )
    av_glow = av_glow.filter(ImageFilter.GaussianBlur(14))
    img.alpha_composite(av_glow)

    if char_icon:
        ci = char_icon.resize((av_s, av_s), Image.Resampling.LANCZOS)
        mask = Image.new("L", (av_s, av_s), 0)
        md = ImageDraw.Draw(mask)
        md.polygon([(av_s//2, 0), (av_s, av_s//2), (av_s//2, av_s), (0, av_s//2)], fill=255)
        img.paste(ci, (av_x, av_y), mask)
        
        # Draw border
        draw.polygon(
            [(av_x + av_s//2, av_y), (av_x + av_s, av_y + av_s//2), (av_x + av_s//2, av_y + av_s), (av_x, av_y + av_s//2)],
            outline=(200, 200, 215, 200), width=2
        )
    else:
        draw.ellipse((av_x, av_y, av_x + av_s, av_y + av_s), fill=(76, 88, 138, 255))
        initial = username[:1].upper() if username else "?"
        f_initial = F(52, True)
        bbox = draw.textbbox((0, 0), initial, font=f_initial)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((av_x + av_s / 2 - tw / 2, av_y + av_s / 2 - th / 2 - 4), initial, fill=(255, 255, 255), font=f_initial)

    # Draw PTT badge
    if max_ptt >= 13.0: r_idx = 7
    elif max_ptt >= 12.5: r_idx = 6
    elif max_ptt >= 12.0: r_idx = 5
    elif max_ptt >= 11.0: r_idx = 4
    elif max_ptt >= 10.0: r_idx = 3
    elif max_ptt >= 7.0: r_idx = 2
    elif max_ptt >= 3.5: r_idx = 1
    else: r_idx = 0

    badge_path = os.path.join(IMG_PATH, f"rating_{r_idx}.png")
    if os.path.exists(badge_path):
        try:
            badge_img = Image.open(badge_path).convert("RGBA")
            badge_s = 56
            badge_img = badge_img.resize((badge_s, badge_s), Image.Resampling.LANCZOS)
            
            # Center of the badge around the bottom right edge
            bx = av_x + av_s - badge_s // 2 - 18
            by = av_y + av_s - badge_s // 2 - 12
            
            img.alpha_composite(badge_img, (int(bx), int(by)))
            
            try:
                f_badge = ImageFont.truetype(FONT_BOLD, 18)
            except:
                f_badge = F(18, False)
                
            badge_text = f"{max_ptt:.2f}"
            bbox = draw.textbbox((0, 0), badge_text, font=f_badge)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            
            tx = bx + badge_s/2 - tw/2
            ty = by + badge_s/2 - th/2 - 12
            
            draw.text((tx, ty), badge_text, fill=(255, 255, 255, 255), font=f_badge, stroke_width=2, stroke_fill=(0, 0, 0, 255))
        except Exception:
            pass

    # Draw username and ID first
    draw.text((188, 145), username, fill=(255, 255, 255, 248), font=f_user)
    draw.text((190, 188), f"ID: {user_code}", fill=(210, 218, 245, 230), font=f_id)
    
    # Calculate username width to place rank to the right
    user_bbox = draw.textbbox((0, 0), username, font=f_user)
    user_w = user_bbox[2] - user_bbox[0]
    
    rank_text = f"#{rank}"
    
    # Draw rank using FONT_TITLE, large enough to span username and ID
    try:
        f_rank = ImageFont.truetype(FONT_TITLE, 80)
    except Exception:
        f_rank = F(80, True)
    
    rank_bbox = draw.textbbox((0, 0), rank_text, font=f_rank)
    rank_w = rank_bbox[2] - rank_bbox[0]
    
    # The right edge is aligned with Player Bests (right_x)
    right_x = 560
    rank_x = right_x - rank_w
    
    # Lower it further to vertically center it with username and ID
    draw.text((rank_x, 150), rank_text, fill=(255, 255, 255, 248), font=f_rank)

    # Stat panel fixed perfectly centered
    stat_x1, stat_y1 = 28, 268
    stat_w, stat_h = 520, 82
    stat_x2, stat_y2 = stat_x1 + stat_w, stat_y1 + stat_h

    glass_panel(
        img,
        (stat_x1, stat_y1, stat_x2, stat_y2),
        radius=12,
        fill=(18, 29, 70, 126),
        outline=(180, 205, 255, 125),
        glow=True,
    )

    stats = [
        ("BEST TOP30 AVG", f"{b30_avg:.4f}"),
        ("MAX POTENTIAL", f"{max_ptt:.4f}"),
        ("RECENT TOP10 AVG", f"~{r10_avg:.4f}"),
    ]

    col_w = stat_w / 3

    label_y = stat_y1 + 17
    value_y = stat_y1 + 56

    for i, (label, value) in enumerate(stats):
        cx = stat_x1 + col_w * i + col_w / 2

        draw_centered(draw, (cx, label_y), label, f_label, (210, 220, 255, 225))
        draw_centered(draw, (cx, value_y), value, f_num, (255, 238, 255, 255))

        if i < 2:
            lx = stat_x1 + col_w * (i + 1)
            draw.line(
                (lx, stat_y1 + 15, lx, stat_y2 - 15),
                fill=(205, 215, 255, 115),
                width=1,
            )

def draw_song_card(img, x, y, w, h, s, rank):
    draw = ImageDraw.Draw(img)
    f_rank = F(16, True)
    f_badge = F(12, True)
    f_song = F(13, True)
    f_score = F(20, False)
    f_small = F(10, False)
    f_small_b = F(10, True)

    glass_panel(img, (x, y, x + w, y + h), radius=9, fill=(201, 219, 255, 78), outline=(235, 240, 255, 150), glow=False)

    strip = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(strip)
    rank_strip_w = 47
    sd.rounded_rectangle((x, y, x + rank_strip_w, y + h), radius=9, fill=(12, 19, 47, 145))
    sd.rectangle((x + rank_strip_w - 14, y, x + rank_strip_w + 6, y + h), fill=(12, 19, 47, 95))
    img.alpha_composite(strip)

    draw.text((x + 10, y + 4), f"#{rank}", fill=(255, 255, 255, 238), font=f_rank)

    jk_s = h - 16
    jk_x = x + 48
    jk_y = y + 8

    title_bar_x1 = x + 48
    title_bar_y1 = y + 9
    title_bar_x2 = x + w - 8
    title_bar_y2 = y + 29
    title_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    td = ImageDraw.Draw(title_layer)
    td.rounded_rectangle((title_bar_x1, title_bar_y1, title_bar_x2, title_bar_y2), radius=8, fill=(31, 33, 72, 178))
    img.alpha_composite(title_layer)

    jk = load_jacket(s["song_id"])
    if jk:
        paste_rounded(img, jk, jk_x, jk_y, jk_s, jk_s, radius=7)
        draw.rounded_rectangle((jk_x, jk_y, jk_x + jk_s, jk_y + jk_s), radius=7, outline=(255, 255, 255, 165), width=2)
    else:
        draw.rounded_rectangle((jk_x, jk_y, jk_x + jk_s, jk_y + jk_s), radius=7, fill=(35, 38, 52, 255), outline=(255, 255, 255, 110), width=1)

    diff_name = get_diff_name(s["diff"])
    diff_col = get_diff_color(s["diff"])
    draw_badge(draw, jk_x, jk_y, diff_name, diff_col, f_badge)

    tx = jk_x + jk_s + 11
    max_w = x + w - tx - 9

    name = text_fit(draw, s["name"], max_w, f_song)
    title_bbox = draw.textbbox((0, 0), name, font=f_song)
    title_h = title_bbox[3] - title_bbox[1]
    title_y = title_bar_y1 + ((title_bar_y2 - title_bar_y1) - title_h) / 2 - 1
    draw.text((tx, title_y), name, fill=(255, 255, 255, 246), font=f_song)

    draw.text((tx, y + 31), score_format(s["score"]), fill=(255, 255, 255, 250), font=f_score)
    ptt = f"Potential {s['base']:.1f}  →  {s['ptt']:.4f}   {s['ct']}"
    draw.text((tx, y + 52), ptt, fill=(228, 235, 255, 225), font=f_small)

    pfl = f"P.{s['p']} (+{s['sp']})   F.{s['f']}   L.{s['l']}"
    draw.text((tx, y + 67), pfl, fill=(226, 190, 255, 235), font=f_small_b)

    if s.get("days", -1) >= 0:
        ds = f"{s['days']}d"
        tw = draw.textlength(ds, font=f_small)
        draw.text((x + w - tw - 9, y + h - 16), ds, fill=(210, 218, 245, 160), font=f_small)

def draw_legend(img, y):
    draw = ImageDraw.Draw(img)
    f = F(10, False)
    f_b = F(11, True)
    items = [
        ("PRS", "PRESENT", get_diff_color(1)),
        ("FTR", "FUTURE", get_diff_color(2)),
        ("ETR", "ETERNAL", get_diff_color(4)),
        ("EC", "EASY CLEAR", None),
        ("HC", "HARD CLEAR", None),
        ("NC", "NORMAL CLEAR", None),
        ("TL", "TRACK LOST", None),
    ]
    x = 47
    for code, desc, color in items:
        if color:
            text_col = (25, 25, 35) if code in ("PRS", "ETR") else (255, 255, 255)
            bw = int(draw.textlength(code, font=f_b)) + 14
            draw.rounded_rectangle((x, y, x + bw, y + 21), radius=5, fill=color)
            draw.text((x + 7, y + 3), code, fill=text_col, font=f_b)
            x += bw + 10
        else:
            draw.text((x, y + 4), code, fill=(255, 255, 255, 235), font=f_b)
            x += int(draw.textlength(code, font=f_b)) + 7
        draw.text((x, y + 4), desc, fill=(205, 214, 240, 215), font=f)
        x += int(draw.textlength(desc, font=f)) + 34

def fetch_scores(user_code):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, rating_ptt, character_id, is_char_uncapped_override FROM user WHERE user_code = ?", (user_code,))
    user = c.fetchone()
    if not user:
        conn.close()
        return None
    user_id, max_ptt, character_id, is_uncapped = user
    
    c.execute("SELECT COUNT(*) FROM user WHERE rating_ptt > ?", (max_ptt,))
    rank = c.fetchone()[0] + 1
    
    max_ptt = max_ptt / 100.0 if max_ptt else 0.0

    c.execute("""
        SELECT b.song_id, b.difficulty, b.score, b.clear_type, c.name,
               c.rating_pst, c.rating_prs, c.rating_ftr, c.rating_byn, c.rating_etr,
               b.rating, b.perfect_count, b.shiny_perfect_count,
               b.near_count, b.miss_count, b.time_played
        FROM best_score b
        LEFT JOIN chart c ON b.song_id = c.song_id
        WHERE b.user_id = ? AND b.rating > 0
        ORDER BY b.rating DESC
        LIMIT 33
    """, (user_id,))
    now = time.time() * 1000
    scores = []
    for row in c.fetchall():
        song_id, diff, score, ct, name, pst, prs, ftr, byn, etr, rating, p, sp, f, l, tp = row
        bases = [pst, prs, ftr, byn, etr]
        base = 0.0
        if diff < len(bases) and bases[diff] and bases[diff] > 0:
            base = bases[diff] / 10.0
        if tp and tp > 1500000000000:
            days = max(0, int((now - tp) / (1000 * 60 * 60 * 24)))
        else:
            days = -1
        scores.append({
            "song_id": song_id, "name": name or song_id, "diff": diff, "score": score,
            "ct": get_clear_type(ct), "base": base, "ptt": rating, "p": p or 0,
            "sp": sp or 0, "f": f or 0, "l": l or 0, "days": days,
        })

    c.execute("SELECT rating FROM recent30 WHERE user_id = ? ORDER BY rating DESC LIMIT 10", (user_id,))
    r10 = [x[0] for x in c.fetchall()]
    r10_avg = sum(r10) / len(r10) if r10 else 0.0
    conn.close()
    return {
        "user_id": user_id, "max_ptt": max_ptt, "character_id": character_id,
        "is_uncapped": bool(is_uncapped), "scores": scores, "r10_avg": r10_avg,
        "rank": rank,
    }

def generate_b30(user_code, username):
    download_fonts()
    data = fetch_scores(user_code)
    if not data: return None

    scores = data["scores"]
    top30 = scores[:30]
    b30_avg = sum(x["ptt"] for x in top30) / len(top30) if top30 else 0.0

    char_icon, char_full, icon_path, full_path = load_character(data["character_id"], data["is_uncapped"])

    W, H = 1024, 1536
    bg_jackets = []
    for s in scores[:15]:
        jk = load_jacket(s["song_id"])
        if jk: bg_jackets.append(jk)

    img = make_background(W, H, char_full=char_full, jackets=bg_jackets)

    draw_header(img, username=username, user_code=user_code, b30_avg=b30_avg, max_ptt=data["max_ptt"], r10_avg=data["r10_avg"], char_icon=char_icon, rank=data["rank"])

    # Layout 30 bài, không overflow
    card_w = 313
    card_h = 88
    gap_x = 12
    gap_y = 8
    start_x = 29
    start_y = 362

    main = top30[:30]
    for i, s in enumerate(main):
        col = i % 3
        row = i // 3
        x = start_x + col * (card_w + gap_x)
        y = start_y + row * (card_h + gap_y)
        draw_song_card(img, x, y, card_w, card_h, s, i + 1)

    draw = ImageDraw.Draw(img)
    footer_line_y = 1427
    draw.line((32, footer_line_y, W - 32, footer_line_y), fill=(190, 205, 255, 70), width=1)
    draw_legend(img, 1450)

    f_footer = F(10, False)
    ts = time.strftime("%Y-%m-%d %H:%M")
    footer = f"Generated by EC2 Server @ {ts}"
    tw = draw.textlength(footer, font=f_footer)
    draw.text((W - tw - 28, H - 24), footer, fill=(190, 198, 225, 150), font=f_footer)

    out_path = os.path.join(OUT_DIR, f"b30_{user_code}.jpg")
    img.convert("RGB").save(out_path, quality=96, optimize=True)
    return out_path

if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        path = generate_b30(sys.argv[1], sys.argv[2])
        if path:
            print(path)
        else:
            print("User not found.")
    else:
        print("Usage: python3 b30_generator.py <user_code> <username>")
