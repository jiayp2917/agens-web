"""Generate raster ink-wash assets for the prototype.

The prototype is static HTML, but the home screen needs an actual background
image asset rather than a CSS-only placeholder. This script creates a soft
xianxia ink backdrop with Pillow so the asset is deterministic and local.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


def lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def draw_mountain(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], fill, width: int) -> None:
    poly = [(0, 844), *points, (width, 844)]
    draw.polygon(poly, fill=fill)


def main() -> None:
    random.seed(2917)
    ASSETS.mkdir(parents=True, exist_ok=True)

    w, h = 390, 844
    img = Image.new("RGB", (w, h), "#f7f4ec")
    px = img.load()
    top = (231, 238, 235)
    bottom = (247, 244, 236)
    for y in range(h):
        t = y / (h - 1)
        for x in range(w):
            mist = int(5 * math.sin((x + y * 0.35) / 27))
            px[x, y] = (
                max(0, min(255, lerp(top[0], bottom[0], t) + mist)),
                max(0, min(255, lerp(top[1], bottom[1], t) + mist)),
                max(0, min(255, lerp(top[2], bottom[2], t) + mist)),
            )

    # Distant mountains.
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    far = [(0, 328), (54, 240), (98, 286), (151, 208), (215, 310), (287, 230), (390, 318)]
    mid = [(0, 398), (44, 330), (98, 352), (154, 284), (207, 370), (276, 306), (390, 388)]
    near = [(0, 475), (76, 405), (128, 436), (195, 375), (246, 448), (315, 390), (390, 456)]
    draw_mountain(d, far, (76, 95, 91, 38), w)
    draw_mountain(d, mid, (62, 82, 78, 52), w)
    draw_mountain(d, near, (48, 68, 64, 68), w)
    layer = layer.filter(ImageFilter.GaussianBlur(2.4))
    img = Image.alpha_composite(img.convert("RGBA"), layer)

    # Cloud bands.
    cloud = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    c = ImageDraw.Draw(cloud)
    for band_y, alpha, spread in [(225, 54, 95), (355, 46, 120), (520, 32, 160)]:
        for _ in range(42):
            cx = random.randint(-40, w + 40)
            cy = int(random.gauss(band_y, 28))
            rx = random.randint(44, spread)
            ry = random.randint(10, 24)
            c.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=(255, 255, 255, alpha))
    cloud = cloud.filter(ImageFilter.GaussianBlur(10))
    img = Image.alpha_composite(img, cloud)

    # Suggestive temple gate, intentionally faint.
    gate = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    g = ImageDraw.Draw(gate)
    ink = (34, 47, 45, 72)
    gold = (176, 139, 68, 64)
    g.line((145, 548, 245, 548), fill=ink, width=2)
    g.line((158, 548, 158, 642), fill=ink, width=3)
    g.line((232, 548, 232, 642), fill=ink, width=3)
    g.line((134, 570, 256, 570), fill=gold, width=2)
    g.arc((111, 498, 279, 582), start=202, end=338, fill=ink, width=2)
    for step in range(8):
        y = 658 + step * 17
        g.line((142 - step * 9, y, 248 + step * 9, y), fill=(34, 47, 45, 24), width=1)
    gate = gate.filter(ImageFilter.GaussianBlur(0.4))
    img = Image.alpha_composite(img, gate)

    # Paper texture.
    texture = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(texture)
    for _ in range(2800):
        x = random.randrange(w)
        y = random.randrange(h)
        v = random.choice([-1, 1])
        alpha = random.randint(5, 14)
        color = (70, 60, 42, alpha) if v < 0 else (255, 255, 255, alpha)
        tdraw.point((x, y), fill=color)
    texture = texture.filter(ImageFilter.GaussianBlur(0.25))
    img = Image.alpha_composite(img, texture)

    img.convert("RGB").save(ASSETS / "ink-home-bg.png", quality=95)


if __name__ == "__main__":
    main()
