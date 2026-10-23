"""Regenerate every FORGE brand icon from backend/static/icons/favicon.svg.

The SVG is the single source of truth for the mark (an anvil and a hammer
spark on obsidian glass). This script rasterises it to the PWA icons, the
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
        '<rect x="3" y="3" width="58" height="58" rx="15" fill="url(#tile)"/>',
        '<rect x="0" y="0" width="64" height="64" fill="url(#tile)"/>',
    )
    svg = re.sub(r'<rect x="3\.6".*?/>\n', "", svg)  # the frame would be clipped by masks
    return svg.replace(
        '<path d="M45 6.5', '<g transform="translate(6.4 6.4) scale(.8)"><path d="M45 6.5'
    ).replace("</svg>", "</g></svg>")


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

    # Feature graphic (1024x500): obsidian field, ember glow, mark + wordmark.
    W, H = 1024, 500
    graphic = Image.new("RGB", (W, H), (11, 9, 8))
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-220, -260, 520, 300), fill=(70, 32, 4))
    gd.ellipse((620, 180, 1180, 640), fill=(46, 12, 18))
    from PIL import ImageFilter

    graphic = Image.blend(graphic, Image.blend(graphic, glow, .9).filter(ImageFilter.GaussianBlur(60)), .85)
    mark = render(svg, 300)
    graphic.paste(mark, (72, 100), mark)
    draw = ImageDraw.Draw(graphic)
    try:
        bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 118)
        sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
    except OSError:
        bold = sub = ImageFont.load_default()
    draw.text((420, 150), "FORGE", font=bold, fill=(255, 247, 237))
    draw.text((426, 300), "Where engineers are made.", font=sub, fill=(251, 191, 36))
    save(graphic, LISTING / "feature-graphic.png")

    print("Regenerated:\n  " + "\n  ".join(written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
