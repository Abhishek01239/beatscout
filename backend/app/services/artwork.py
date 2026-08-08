"""Artwork handling: download remote artwork or synthesize artwork locally.

For MOCK discovered tracks (album_art_url == "mock://art/<n>") we generate
a deterministic, branded gradient cover — so the UI and video pipeline work
fully offline. For REAL tracks we download the Spotify CDN artwork.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..config import get_settings

log = logging.getLogger("beatscout.artwork")

_PALETTES = [
    ((16, 20, 34), (99, 102, 241)),     # indigo night
    ((10, 24, 20), (52, 211, 153)),     # emerald
    ((36, 12, 24), (244, 63, 94)),      # rose
    ((13, 22, 40), (56, 189, 248)),     # cyan
    ((30, 16, 8), (251, 146, 60)),      # amber
    ((22, 10, 32), (168, 85, 247)),     # violet
    ((8, 30, 28), (45, 212, 191)),      # teal
]


def ensure_artwork(track) -> str | None:
    """Return a local artwork path for `track`, creating it if needed."""
    settings = get_settings()
    if track.artwork_path and Path(track.artwork_path).exists():
        return track.artwork_path

    art_dir = settings.storage_dir / "artwork"
    art_dir.mkdir(parents=True, exist_ok=True)
    url = track.album_art_url or ""

    if url.startswith("mock://"):
        seed = url
        path = art_dir / f"{seed.split('/')[-1]}.png"
        if not path.exists():
            _synthetic_cover(path, track.track_name, track.artist_name, seed)
        track.artwork_path = str(path)
        return str(path)

    if url.startswith("http"):
        try:
            path = art_dir / f"track_{track.id}_{hashlib.md5(url.encode()).hexdigest()[:8]}.png"
            if not path.exists():
                resp = httpx.get(url, timeout=15, follow_redirects=True)
                resp.raise_for_status()
                img = Image.open(__import__("io").BytesIO(resp.content)).convert("RGB")
                img.thumbnail((1024, 1024), Image.LANCZOS)
                img.save(path, "PNG")
            track.artwork_path = str(path)
        except Exception as exc:  # network hiccup -> fall back to synthetic
            log.warning("artwork download failed for track %s: %s — using synthetic", track.id, exc)
            path = art_dir / f"track_{track.id}.png"
            if not path.exists():
                _synthetic_cover(path, track.track_name, track.artist_name, f"mock://{track.id}")
            track.artwork_path = str(path)
        return track.artwork_path

    # No remote source at all -> synthesize a branded placeholder cover so the
    # render pipeline never stalls on a missing image.
    path = art_dir / f"track_{track.id}.png"
    if not path.exists():
        _synthetic_cover(path, track.track_name, track.artist_name, f"mock://{track.id}")
    track.artwork_path = str(path)
    log.info("no artwork URL for track %s — generated synthetic cover", track.id)
    return str(path)


def _synthetic_cover(path: Path, track_name: str, artist_name: str, seed: str) -> None:
    """Generate a branded placeholder cover (offline-safe)."""
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    palette = _PALETTES[h % len(_PALETTES)]
    c1, c2 = palette
    size = 1024
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        t = y / size
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        for x in range(size):
            px[x, y] = (r, g, b)

    draw = ImageDraw.Draw(img, "RGBA")
    cx, cy = size // 2, size // 2
    for i, radius in enumerate(range(140, 460, 36)):
        alpha = 26 - i
        if alpha <= 0:
            break
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                     outline=(255, 255, 255, alpha), width=6)
    # waveform-ish bars
    import math
    for i in range(-7, 8):
        h = int(150 * math.sin(i / 2.2) ** 2) + 30
        draw.rectangle([cx + i * 26 - 9, cy - h // 2, cx + i * 26 + 9, cy + h // 2],
                       fill=(255, 255, 255, 90))

    font_l = _font(size // 12)
    font_s = _font(size // 22)
    draw.text((48, size - 130), artist_name.upper(), font=font_s, fill=(255, 255, 255, 170))
    draw.text((48, size - 66), track_name.title(), font=font_l, fill=(255, 255, 255, 240))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    img.save(path, "PNG")


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default()


_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def load_track_artwork(track, size: tuple[int, int] = (1024, 1024)) -> Image.Image:
    """Return a square RGB artwork image for compositing, or a synthetic fallback."""
    path = ensure_artwork(track)
    img = Image.open(path).convert("RGB") if path else Image.new("RGB", size, (16, 18, 28))
    img.thumbnail(size, Image.LANCZOS)
    return img