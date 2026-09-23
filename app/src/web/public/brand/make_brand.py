"""Derive the app's brand assets from the official BMO Capital Markets lockup.

The source (`_source-bmo.png`) is the official mark supplied by the demo owner and
is used **for demo presentation only** — see BRAND.md. This script does not
redraw or restyle it; it crops, removes the white background and rescales, so the
mark that ships is the mark that was supplied.

    cm-logo.png        square, transparent, full colour  -> sign-in card
    cm-logo-white.png  square, transparent, mono white   -> the blue top bar
    cm-lockup.png      the full lockup, trimmed          -> sign-in card header
    favicon.png        64px roundel                      -> browser tab

The square mark is the **red roundel**, not the whole lockup: at 26px in the top
bar the wordmark is unreadable, and the bar already spells out the name. The
roundel is located automatically from the red pixels rather than a hardcoded
crop box, so re-supplying a differently-proportioned source still works.

    pip install pillow
    python make_brand.py [source.png]
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent
DEFAULT_SRC = OUT / "_source-bmo.png"

# Sampled from the supplied artwork.
BMO_BLUE = (0, 121, 194)
BMO_RED = (237, 28, 36)

WHITE_TOL = 18


def drop_white(im: Image.Image, tol: int = WHITE_TOL) -> Image.Image:
    """Make near-white pixels transparent. Returns a new RGBA image."""
    im = im.convert("RGBA")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if r > 255 - tol and g > 255 - tol and b > 255 - tol:
                px[x, y] = (r, g, b, 0)
    return im


def trim(im: Image.Image) -> Image.Image:
    bbox = im.getbbox()
    return im.crop(bbox) if bbox else im


def red_bbox(im: Image.Image, tol: int = 70) -> tuple[int, int, int, int] | None:
    """Bounding box of the red roundel, found by colour rather than coordinates."""
    rgb = im.convert("RGB")
    px = rgb.load()
    tr, tg, tb = BMO_RED
    xs: list[int] = []
    ys: list[int] = []
    for y in range(rgb.height):
        for x in range(rgb.width):
            r, g, b = px[x, y]
            if abs(r - tr) < tol and abs(g - tg) < tol and abs(b - tb) < tol:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs) + 1, max(ys) + 1)


def circle_mask(im: Image.Image, feather: float = 0.995, ss: int = 4) -> Image.Image:
    """Keep pixels inside the inscribed circle, drop the corners.

    Used instead of `drop_white` for the roundel. The mountain device inside the
    circle is *white*, so removing white pixels would punch a hole straight
    through the mark - it looks right on a white page and wrong the moment it
    sits on the blue top bar. Masking to the circle removes only the corner
    background and leaves the glyph intact.

    The mask is built at `ss`x and downsampled, which anti-aliases the rim. Doing
    it the other way round - mask small, then upscale - upscales the jaggies.
    """
    im = im.convert("RGBA")
    w, h = im.size
    mask = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(mask).ellipse(
        [0, 0, w * ss - 1, h * ss - 1], fill=255,
    )
    if feather < 1.0:
        inset = int(min(w, h) * ss * (1 - feather) / 2)
        if inset > 0:
            mask = Image.new("L", (w * ss, h * ss), 0)
            ImageDraw.Draw(mask).ellipse(
                [inset, inset, w * ss - 1 - inset, h * ss - 1 - inset], fill=255,
            )
    mask = mask.resize((w, h), Image.LANCZOS)

    out = im.copy()
    alpha = out.getchannel("A").point(lambda a: a)
    out.putalpha(Image.composite(alpha, Image.new("L", (w, h), 0), mask))
    return out


def square(im: Image.Image, size: int, pad: float = 0.0) -> Image.Image:
    """Fit onto a transparent square canvas, scaling UP or down as needed.

    `Image.thumbnail` only ever shrinks, so a 124px roundel would sit marooned in
    the middle of a 512px canvas. This scales to the target either way.
    """
    inner = max(1, int(size * (1 - pad)))
    scale = min(inner / im.width, inner / im.height)
    w = max(1, round(im.width * scale))
    h = max(1, round(im.height * scale))
    resized = im.convert("RGBA").resize((w, h), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(resized, ((size - w) // 2, (size - h) // 2), resized)
    return canvas


def to_white(im: Image.Image) -> Image.Image:
    """Force RGB to white, keep alpha - so the mark keeps its internal shape
    against the blue top bar rather than flattening into a solid blob."""
    im = im.convert("RGBA")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            _, _, _, a = px[x, y]
            px[x, y] = (255, 255, 255, a)
    return im


def main() -> int:
    src_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    if not src_path.exists():
        sys.exit(f"source not found: {src_path}\n"
                 f"place the official lockup at {DEFAULT_SRC.name} or pass a path")

    src = Image.open(src_path).convert("RGBA")
    print(f"source: {src.size[0]}x{src.size[1]}  ({src_path.name})")

    box = red_bbox(src)
    if box is None:
        sys.exit("could not locate the red roundel - is this the BMO lockup?")
    print(f"roundel located at {box}")

    # Upscale FIRST, then mask - so the rim is anti-aliased at final resolution
    # rather than being a 124px staircase blown up to 512.
    crop = src.crop(box)
    roundel_512 = circle_mask(square(crop, 512, pad=0.04))
    roundel_64 = circle_mask(square(crop, 64, pad=0.02))

    roundel_512.save(OUT / "cm-logo.png")
    print("+ cm-logo.png        512px roundel, transparent corners")

    to_white(roundel_512).save(OUT / "cm-logo-white.png")
    print("+ cm-logo-white.png  512px mono white, for the blue top bar")

    roundel_64.save(OUT / "favicon.png")
    print("+ favicon.png        64px roundel")

    lockup = trim(drop_white(src.copy()))
    lockup.thumbnail((900, 320), Image.LANCZOS)
    lockup.save(OUT / "cm-lockup.png")
    print(f"+ cm-lockup.png      {lockup.size[0]}x{lockup.size[1]} full lockup")

    print(f"\npalette: brand #{BMO_BLUE[0]:02x}{BMO_BLUE[1]:02x}{BMO_BLUE[2]:02x}"
          f"  accent #{BMO_RED[0]:02x}{BMO_RED[1]:02x}{BMO_RED[2]:02x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
