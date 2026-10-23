#!/usr/bin/env python3
"""Generate the raster images the public pages reference.

Outputs (all under backend/static/img/):

* ``og-image.png``   1200x630 Open Graph / Twitter card image. PNG, because
  some social crawlers still ignore WebP for ``og:image``.
* ``og-image.webp``  The same card as WebP, for browsers that accept it.
* ``app-icon-192.webp`` / ``app-icon-512.webp``  WebP copies of the PWA icons,
  served through ``<picture>`` with the PNG as the fallback.

The SVG mark in backend/static/icons/favicon.svg is the source of truth, as in
``gen_brand_icons.py``. This is a maintainer tool, not a runtime dependency:

    pip install resvg-py pillow
    python scripts/gen_social_images.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "backend" / "static" / "icons"
IMG = ROOT / "backend" / "static" / "img"


def main() -> int:
    try:
        from PIL import Image, ImageDraw, ImageFont
        from resvg_py import svg_to_bytes
    except ImportError:
        print("Missing tools: pip install resvg-py pillow", file=sys.stderr)
        return 2

    svg = (ICONS / "favicon.svg").read_text(encoding="utf-8")

    def render(size: int) -> Image.Image:
        data = svg_to_bytes(svg_string=svg, width=size, height=size)
        return Image.open(io.BytesIO(data)).convert("RGBA")

    IMG.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    # --- Open Graph card -------------------------------------------------
    width, height = 1200, 630
    card = Image.new("RGB", (width, height), (245, 242, 235))
    mark = render(260)
    card.paste(mark, (96, (height - 260) // 2), mark)
    draw = ImageDraw.Draw(card)
    try:
        bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 96)
        sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 38)
    except OSError:
        bold = sub = ImageFont.load_default()
    draw.text((410, 205), "MERIDIAN", font=bold, fill=(14, 31, 54))
    draw.text((414, 330), "Engineering, studied properly.", font=sub, fill=(29, 91, 214))
    draw.text((414, 392), "Notes  ·  Practice  ·  Progress", font=sub, fill=(59, 74, 94))

    png = IMG / "og-image.png"
    card.save(png, optimize=True)
    written.append(str(png.relative_to(ROOT)))
    webp = IMG / "og-image.webp"
    card.save(webp, quality=86, method=6)
    written.append(str(webp.relative_to(ROOT)))

    # --- WebP copies of the app icons -----------------------------------
    for size in (192, 512):
        source = ICONS / f"icon-{size}.png"
        icon = Image.open(source).convert("RGBA") if source.exists() else render(size)
        target = IMG / f"app-icon-{size}.webp"
        icon.save(target, quality=90, method=6)
        written.append(str(target.relative_to(ROOT)))

    print("Regenerated:\n  " + "\n  ".join(written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
