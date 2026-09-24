import os
import math
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter

CATEGORY_THEMES = {
    "restaurant": {
        "bg_start": (24, 8, 4),
        "bg_end": (120, 53, 15),
        "accent": (245, 158, 11),
        "accent_light": (254, 243, 199),
        "badge_bg": (180, 83, 9),
        "badge_text": (255, 255, 255),
        "icon": "🍽️",
    },
    "cafe": {
        "bg_start": (30, 15, 10),
        "bg_end": (140, 70, 30),
        "accent": (217, 119, 6),
        "accent_light": (254, 243, 199),
        "badge_bg": (180, 83, 9),
        "badge_text": (255, 255, 255),
        "icon": "☕",
    },
    "auto": {
        "bg_start": (3, 7, 18),
        "bg_end": (30, 58, 138),
        "accent": (14, 165, 233),
        "accent_light": (224, 242, 254),
        "badge_bg": (2, 132, 199),
        "badge_text": (255, 255, 255),
        "icon": "🚗",
    },
    "salon": {
        "bg_start": (28, 10, 24),
        "bg_end": (112, 26, 117),
        "accent": (236, 72, 153),
        "accent_light": (253, 242, 248),
        "badge_bg": (190, 24, 93),
        "badge_text": (255, 255, 255),
        "icon": "✂️",
    },
    "default": {
        "bg_start": (15, 23, 42),
        "bg_end": (55, 48, 163),
        "accent": (99, 102, 241),
        "accent_light": (238, 242, 255),
        "badge_bg": (79, 70, 229),
        "badge_text": (255, 255, 255),
        "icon": "🏪",
    },
}


def get_theme_for_category(category: str) -> dict:
    cat_lower = (category or "").lower()
    for key, theme in CATEGORY_THEMES.items():
        if key in cat_lower:
            return theme
    return CATEGORY_THEMES["default"]


def sample_logo_color(logo_path: Path) -> Optional[Tuple[int, int, int]]:
    """Extract dominant non-transparent, non-white/black color from logo."""
    try:
        with Image.open(logo_path) as img:
            img = img.convert("RGBA").resize((64, 64))
            colors = img.getcolors(64 * 64)
            if not colors:
                return None
            # Sort by frequency
            colors.sort(reverse=True, key=lambda c: c[0])
            for count, (r, g, b, a) in colors:
                if a < 128:
                    continue
                # Skip pure black/white
                brightness = (r + g + b) / 3
                if 40 < brightness < 220:
                    return (r, g, b)
    except Exception:
        pass
    return None


def generate_brand_monogram(business_name: str, category: str, output_path: Path) -> str:
    """Creates a circular monogram brand logo if user skips uploading one."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    size = 400
    theme = get_theme_for_category(category)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Gradient circular background
    for i in range(size // 2, 0, -1):
        ratio = i / (size // 2)
        r = int(theme["bg_end"][0] * ratio + theme["accent"][0] * (1 - ratio))
        g = int(theme["bg_end"][1] * ratio + theme["accent"][1] * (1 - ratio))
        b = int(theme["bg_end"][2] * ratio + theme["accent"][2] * (1 - ratio))
        draw.ellipse([size // 2 - i, size // 2 - i, size // 2 + i, size // 2 + i], fill=(r, g, b, 255))

    # Outer border ring
    draw.ellipse([10, 10, size - 10, size - 10], outline=(255, 255, 255, 180), width=6)

    # Initials
    words = [w for w in business_name.split() if w.isalnum()]
    initials = "".join(w[0].upper() for w in words[:2]) if words else "DM"

    try:
        font = ImageFont.truetype("arial.ttf", 130)
    except Exception:
        font = ImageFont.load_default()

    # Center text
    bbox = draw.textbbox((0, 0), initials, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text(((size - w) / 2, (size - h) / 2 - 10), initials, fill=(255, 255, 255, 255), font=font)

    img.save(output_path, "PNG")
    return str(output_path)


def generate_hero_banner(
    business_name: str,
    category: str,
    tagline: Optional[str],
    logo_path: Optional[str],
    output_path: Path,
) -> str:
    """
    Generates a panoramic 1200x500 hero section banner compositing:
    - Dynamic gradient & atmospheric glow matching the logo / category
    - Logo placement with rounded glassmorphism badge & border glow
    - Clean typography with business name, category badge, and tagline
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1200, 500
    theme = get_theme_for_category(category)

    # If logo has dominant color, adapt theme
    if logo_path and Path(logo_path).exists():
        dominant = sample_logo_color(Path(logo_path))
        if dominant:
            theme = theme.copy()
            theme["accent"] = dominant
            theme["bg_end"] = (
                max(10, int(dominant[0] * 0.6)),
                max(10, int(dominant[1] * 0.6)),
                max(10, int(dominant[2] * 0.6)),
            )

    # 1. Base gradient
    base = Image.new("RGB", (width, height), theme["bg_start"])
    draw = ImageDraw.Draw(base)

    # Multi-step angular/horizontal gradient
    for x in range(width):
        t = x / width
        r = int(theme["bg_start"][0] * (1 - t) + theme["bg_end"][0] * t)
        g = int(theme["bg_start"][1] * (1 - t) + theme["bg_end"][1] * t)
        b = int(theme["bg_start"][2] * (1 - t) + theme["bg_end"][2] * t)
        draw.line([(x, 0), (x, height)], fill=(r, g, b))

    # 2. Glowing Orb Accents
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)

    # Right glow behind logo
    center_x, center_y = 950, 250
    radius = 280
    for r_step in range(radius, 0, -10):
        alpha = int(45 * (1 - r_step / radius))
        glow_draw.ellipse(
            [center_x - r_step, center_y - r_step, center_x + r_step, center_y + r_step],
            fill=(theme["accent"][0], theme["accent"][1], theme["accent"][2], alpha),
        )

    # Left subtle ambiance
    glow_draw.ellipse(
        [50, -50, 450, 350],
        fill=(theme["accent_light"][0], theme["accent_light"][1], theme["accent_light"][2], 18),
    )

    base = Image.alpha_composite(base.convert("RGBA"), glow).convert("RGB")
    draw = ImageDraw.Draw(base)

    # 3. Decorative subtle line grid / patterns
    for y in range(0, height, 40):
        draw.line([(0, y), (width, y)], fill=(255, 255, 255, 8), width=1)

    # 4. Fonts
    try:
        font_badge = ImageFont.truetype("arialbd.ttf", 22)
        font_title = ImageFont.truetype("arialbd.ttf", 52)
        font_tagline = ImageFont.truetype("arial.ttf", 26)
        font_small = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font_badge = ImageFont.load_default()
        font_title = ImageFont.load_default()
        font_tagline = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # 5. Left Content Layout
    # Category Pill
    badge_text = f"✨  {(category or 'Storefront').upper()}"
    badge_bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
    bw = badge_bbox[2] - badge_bbox[0] + 32
    bh = 38
    badge_x, badge_y = 80, 80
    draw.rounded_rectangle(
        [badge_x, badge_y, badge_x + bw, badge_y + bh],
        radius=19,
        fill=theme["badge_bg"],
        outline=(255, 255, 255, 120),
        width=1,
    )
    draw.text((badge_x + 16, badge_y + 8), badge_text, fill=theme["badge_text"], font=font_badge)

    # Business Name
    title_text = business_name
    if len(title_text) > 28:
        title_text = title_text[:25] + "..."
    draw.text((80, 145), title_text, fill=(255, 255, 255), font=font_title)

    # Tagline
    if tagline:
        clean_tag = f"“{tagline}”"
        if len(clean_tag) > 55:
            clean_tag = clean_tag[:52] + "...”"
        draw.text((80, 225), clean_tag, fill=(229, 231, 235), font=font_tagline)
    else:
        draw.text((80, 225), "Premium Quality & Direct Customer Service", fill=(209, 213, 219), font=font_tagline)

    # Trust indicator
    draw.text((80, 390), "★ 100% Verified Digital Storefront • DukaanMitra AI", fill=theme["accent"], font=font_small)

    # 6. Logo Integration (Right Side Showcase Badge)
    logo_size = 200
    logo_pos_x = 850
    logo_pos_y = 150

    # Draw rounded white glassmorphism card for logo
    draw.rounded_rectangle(
        [logo_pos_x - 20, logo_pos_y - 20, logo_pos_x + logo_size + 20, logo_pos_y + logo_size + 20],
        radius=28,
        fill=(255, 255, 255, 240),
        outline=theme["accent"],
        width=3,
    )

    if logo_path and Path(logo_path).exists():
        try:
            with Image.open(logo_path) as logo_img:
                logo_img = logo_img.convert("RGBA")
                logo_img.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
                # Center logo inside card
                lw, lh = logo_img.size
                paste_x = logo_pos_x + (logo_size - lw) // 2
                paste_y = logo_pos_y + (logo_size - lh) // 2
                base.paste(logo_img, (paste_x, paste_y), logo_img)
        except Exception:
            # Fallback monogram
            draw.text((logo_pos_x + 50, logo_pos_y + 70), business_name[:2].upper(), fill=theme["accent"], font=font_title)
    else:
        # Monogram in the card
        draw.text((logo_pos_x + 60, logo_pos_y + 70), business_name[:2].upper(), fill=theme["accent"], font=font_title)

    base = base.convert("RGB")
    base.save(output_path, "JPEG", quality=92)
    return str(output_path)
