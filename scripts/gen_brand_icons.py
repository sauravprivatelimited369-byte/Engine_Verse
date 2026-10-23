"""Regenerate every MERIDIAN brand icon from backend/static/icons/favicon.svg.

The SVG is the single source of truth for the mark (an M inside a meridian
ring, with the orbit's signal dot). This script rasterises it to the PWA icons, the
legacy Android launcher mipmaps and the store-listing icon, and composes the
1024x500 feature graphic. It is a maintainer tool, not a runtime dependency:

    pip install resvg-py pillow
    python scripts/gen_brand_icons.py

The adaptive-icon foreground (android/.../ic_launcher_foreground.xml) is a
hand-maintained vector twin of the same paths; keep the two in step.
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAVICON = ROOT / "backend/static/icons/favicon.svg"
ICONS = ROOT / "backend/static/icons"
RES = ROOT / "android/app/src/main/res"
LISTING = ROOT / "android/listing"

MIPMAPS = {  # density bucket -> legacy launcher px
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}


def _maskable_svg(svg: str) -> str:
    """Full-bleed tile, glyph inside the maskable safe zone (centre 80%)."""
    svg = svg.replace(
        '<rect x="3" y="3" width="58" height="58" rx="14" fill="url(#tile)"/>',
        '<rect x="0" y="0" width="64" height="64" fill="url(#tile)"/>',
    )
    svg = re.sub(r'<rect x="3\.6".*?/>\n', "", svg)  # the frame would be clipped by masks
    return svg.replace(
        '<g id="mark">', '<g id="mark" transform="translate(6.4 6.4) scale(.8)">'
    )


def main() -> int:
    try:
        from PIL import Image, ImageDraw, ImageFont
        from resvg_py import svg_to_bytes
    except ImportError:
        print("Missing tools: pip install resvg-py pillow", file=sys.stderr)
        return 2

    def render(svg: str, size: int) -> Image.Image:
        return Image.open(io.BytesIO(svg_to_bytes(svg_string=svg, width=size, height=size))).convert("RGBA")

    svg = FAVICON.read_text(encoding="utf-8")
    written: list[str] = []

    def save(img: Image.Image, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path)
        written.append(str(path.relative_to(ROOT)))

    save(render(svg, 192), ICONS / "icon-192.png")
    save(render(svg, 512), ICONS / "icon-512.png")
    save(render(_maskable_svg(svg), 512), ICONS / "maskable-512.png")
    save(render(svg, 512), LISTING / "icon-512.png")

    for bucket, px in MIPMAPS.items():
        tile = render(svg, px)
        save(tile, RES / bucket / "ic_launcher.png")
        mask = Image.new("L", (px, px), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, px, px), fill=255)
        round_icon = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        round_icon.paste(tile, (0, 0), mask)
        save(round_icon, RES / bucket / "ic_launcher_round.png")

    # Feature graphic (1024x500): warm paper field, navy wordmark, blue signal.
    W, H = 1024, 500
    graphic = Image.new("RGB", (W, H), (245, 242, 235))
    from PIL import ImageFilter

    wash = Image.new("RGB", (W, H), (245, 242, 235))
    wd = ImageDraw.Draw(wash)
    wd.ellipse((520, -260, 1280, 420), fill=(225, 234, 250))
    graphic = Image.blend(graphic, wash.filter(ImageFilter.GaussianBlur(90)), .8)
    mark = render(svg, 250)
    graphic.paste(mark, (64, 125), mark)
    draw = ImageDraw.Draw(graphic)
    try:
        bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 92)
        sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 33)
    except OSError:
        bold = sub = ImageFont.load_default()
    draw.text((362, 168), "MERIDIAN", font=bold, fill=(14, 31, 54))
    draw.text((366, 285), "Engineering, studied properly.", font=sub, fill=(29, 91, 214))
    # Keep the graphic inside the 1024x500 canvas whatever font was available.
    draw.text((366, 392), "Notes  ·  Practice  ·  Progress", font=sub, fill=(59, 74, 94))
    save(graphic, LISTING / "feature-graphic.png")

    print("Regenerated:\n  " + "\n  ".join(written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
