"""Local keyframe renderer for V5 fallback and smoke tests."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _font(size: int) -> ImageFont.ImageFont:
    for name in ["msyh.ttc", "simhei.ttf", "arial.ttf"]:
        try:
            return ImageFont.truetype(name, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def create_keyframe(path: str, title: str, subtitle: str, palette: tuple[int, int, int]) -> str:
    """Create a simple cinematic keyframe PNG."""
    width, height = 768, 432
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)

    base = Image.new("RGB", (width, height), palette)
    draw = ImageDraw.Draw(base)

    for y in range(height):
        shade = int(60 * (y / height))
        color = tuple(max(0, min(255, channel - shade)) for channel in palette)
        draw.line([(0, y), (width, y)], fill=color)

    draw.rectangle((0, height - 118, width, height), fill=(12, 16, 22))
    draw.rectangle((56, 56, width - 56, height - 150), outline=(255, 255, 255), width=2)
    draw.ellipse((width // 2 - 42, 124, width // 2 + 42, 208), fill=(245, 226, 188))
    draw.rectangle((width // 2 - 65, 208, width // 2 + 65, 306), fill=(42, 62, 96))

    title_font = _font(30)
    body_font = _font(19)
    draw.text((42, height - 100), title[:22], fill=(255, 255, 255), font=title_font)
    draw.text((42, height - 58), subtitle[:48], fill=(190, 210, 235), font=body_font)

    base.save(output)
    return str(output)
