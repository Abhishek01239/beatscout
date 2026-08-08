"""YouTube thumbnail generator (1280x720) with several layouts."""

from __future__ import annotations

import logging

import numpy as np
from PIL import Image, ImageDraw

from ..artwork import _font, load_track_artwork

log = logging.getLogger("beatscout.thumbnail")

THUMB_W, THUMB_H = 1280, 720
LAYOUTS = ("classic", "artwork_center", "band", "split")


def render_thumbnail(track, out_path: str, layout: str = "classic") -> str:
    """Render a 1280x720 thumbnail; returns the path written."""
    layout = layout if layout in LAYOUTS else "classic"
    img = _LAYOUT_FNS[layout](
        load_track_artwork(track, size=(THUMB_H, THUMB_H)),
        track.track_name,
        track.artist_name,
        track.genre,
    )
    img.convert("RGB").save(out_path, "JPEG", quality=92)
    log.info("thumbnail rendered: %s", out_path)
    return out_path


def _base(width: int, height: int) -> Image.Image:
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    c1, c2 = np.array([12, 13, 22], np.float32), np.array([44, 34, 78], np.float32)
    t = np.linspace(0, 1, height, dtype=np.float32)[:, None]   # (H, 1)
    base = c1[None, :] * (1 - t) + c2[None, :] * t             # (H, 3)
    base = np.broadcast_to(base[:, None, :], (height, width, 3)).copy()
    glow = np.exp(-((xx - width * 0.5) ** 2 + (yy - height * 0.45) ** 2) / float(2 * (width * 0.4) ** 2))
    base += glow[:, :, None] * 48
    return Image.fromarray(np.clip(base, 0, 255).astype("uint8"))


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if cur and draw.textlength(test, font=font) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines[:3]


def _classic(art: Image.Image, title: str, artist: str, genre: str | None) -> Image.Image:
    img = _base(THUMB_W, THUMB_H)
    art = art.resize((640, 640), Image.LANCZOS)
    img.paste(art, (40, (THUMB_H - 640) // 2))
    draw = ImageDraw.Draw(img)
    x = 760
    draw.text((x, 130), artist.upper(), font=_font(30), fill=(202, 206, 224))
    lines = _wrap(draw, title.title(), _font(72), THUMB_W - x - 60)
    for i, line in enumerate(lines):
        draw.text((x, 190 + i * 86), line, font=_font(72), fill=(255, 255, 255))
    if genre:
        draw.text((x, 560), genre.upper(), font=_font(24), fill=(120, 200, 255))
    draw.text((THUMB_W - 240, THUMB_H - 54), "BEAT SCOUT", font=_font(26), fill=(150, 155, 190))
    return img


def _artwork_center(art: Image.Image, title: str, artist: str, genre: str | None) -> Image.Image:
    img = _base(THUMB_W, THUMB_H)
    art = art.resize((640, 640), Image.LANCZOS)
    img.paste(art, ((THUMB_W - 640) // 2, 20))
    draw = ImageDraw.Draw(img)
    draw.text((THUMB_W // 2, 130), artist.upper(), font=_font(28), anchor="mm", fill=(210, 214, 230))
    draw.text((THUMB_W // 2, 690), title.title(), font=_font(56), anchor="mm", fill=(255, 255, 255))
    return img


def _banded(art: Image.Image, title: str, artist: str, genre: str | None) -> Image.Image:
    img = _base(THUMB_W, THUMB_H)
    strip = art.resize((THUMB_W, 300), Image.LANCZOS)
    img.paste(strip, (0, THUMB_H - 300))
    draw = ImageDraw.Draw(img, "RGBA")
    draw.rectangle([0, THUMB_H - 300, THUMB_W, THUMB_H], fill=(0, 0, 0, 150))
    draw.text((60, THUMB_H - 250), artist.upper(), font=_font(30), fill=(255, 255, 255))
    draw.text((60, THUMB_H - 180), title.title(), font=_font(64), fill=(255, 255, 255))
    return img


def _split(art: Image.Image, title: str, artist: str, genre: str | None) -> Image.Image:
    img = _base(THUMB_W, THUMB_H)
    art = art.resize((THUMB_H, THUMB_H), Image.LANCZOS)
    img.paste(art, (0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((THUMB_H + 80, 130), artist.upper(), font=_font(28), fill=(225, 228, 240))
    lines = _wrap(draw, title.title(), _font(54), THUMB_W - THUMB_H - 140)
    for i, line in enumerate(lines):
        draw.text((THUMB_H + 80, 200 + i * 66), line, font=_font(54), fill=(255, 255, 255))
    return img


_LAYOUT_FNS = {
    "classic": _classic,
    "artwork_center": _artwork_center,
    "band": _banded,
    "split": _split,
}