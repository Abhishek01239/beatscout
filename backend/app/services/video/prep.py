"""Shared rendering helpers for the visualizer pipeline.

Pure numpy + Pillow: gradients, sprites, text overlays, waveform bars,
box blur, feature normalization.  Style renderers live in ``engine.py``.
"""

from __future__ import annotations

import logging
import math

import numpy as np

log = logging.getLogger("beatscout.video.prep")


# ---------------------------------------------------------------------------
# Style palettes
# ---------------------------------------------------------------------------

STYLE_BACKGROUNDS = {
    "dark":     ((8, 9, 14), (22, 24, 40)),
    "midnight": ((5, 6, 18), (42, 30, 100)),
    "ocean":    ((4, 16, 30), (12, 62, 94)),
    "ember":    ((30, 8, 12), (74, 40, 14)),
    "forest":   ((6, 26, 16), (26, 76, 52)),
}

STYLE_ACCENTS = {
    "dark":     np.array([124, 132, 255], dtype=np.float32),
    "midnight": np.array([226, 108, 255], dtype=np.float32),
    "ocean":    np.array([72, 208, 255], dtype=np.float32),
    "ember":    np.array([255, 150, 96], dtype=np.float32),
    "forest":   np.array([72, 255, 168], dtype=np.float32),
}


# ---------------------------------------------------------------------------
# Backgrounds
# ---------------------------------------------------------------------------

def make_background(height: int, width: int, bg_name: str, pulse: float = 0.0) -> np.ndarray:
    """Vertical gradient + radial glow, HxWx3 uint8."""
    c1, c2 = STYLE_BACKGROUNDS.get(bg_name, STYLE_BACKGROUNDS["dark"])
    c1, c2 = np.array(c1, dtype=np.float32), np.array(c2, dtype=np.float32)
    t = np.linspace(0, 1, height, dtype=np.float32)[:, None]
    base = c1[None, :] * (1 - t) + c2[None, :] * t                      # H x 3
    base = np.broadcast_to(base[:, None, :], (height, width, 3)).copy()

    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    glow = np.exp(-((xx - width * 0.5) ** 2 + (yy - height * 0.40) ** 2)
                  / float(2 * (width * 0.26) ** 2))
    base += (130.0 + 120.0 * max(0.0, min(pulse, 1.0))) * glow[:, :, None]
    return np.clip(base, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# Blur (no scipy: separable box blur via cumulative sums)
# ---------------------------------------------------------------------------

def box_blur(arr: np.ndarray, radius: int = 4) -> np.ndarray:
    """Separable box blur via cumulative sums (no scipy). Same shape out."""
    if radius <= 0:
        return arr.copy()
    a = arr.astype(np.float32)
    if a.ndim == 2:
        a = a[:, :, None]
    k = radius * 2 + 1
    orig_shape = a.shape
    padded = np.pad(a, ((0, 0), (k, k), (0, 0)), mode="edge")
    cs = np.cumsum(padded, axis=1)
    hb = (cs[:, k:, :] - cs[:, :-k, :]) / k          # width w + k
    hb = hb[:, : orig_shape[1], :]
    padded = np.pad(hb, ((k, k), (0, 0), (0, 0)), mode="edge")
    cs = np.cumsum(padded, axis=0)
    vb = (cs[k:, :, :] - cs[:-k, :, :]) / k          # height h + k
    vb = vb[: orig_shape[0], :, :]
    return np.clip(vb, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# Text overlays (Pillow -> RGBA numpy)
# ---------------------------------------------------------------------------

def text_overlay(text: str, font, color=(255, 255, 255), alpha: int = 235) -> np.ndarray:
    """Pre-render a string to an RGBA numpy overlay (HxWx4)."""
    from PIL import Image, ImageDraw

    if not text:
        return np.zeros((0, 0, 4), dtype=np.uint8)
    tmp = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    bbox = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 40, 14
    img = Image.new("RGBA", (tw + pad_x * 2, th + pad_y * 2), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((pad_x, pad_y), text, font=font, fill=(*color, alpha))
    return np.asarray(img)


def blend_overlay(frame: np.ndarray, overlay: np.ndarray, *, cx: float, cy: float,
                  alpha: float = 1.0, fade_in: float = 1.0) -> np.ndarray:
    """Alpha-blend an RGBA overlay into frame at fractional center (cx, cy)."""
    if overlay.shape[0] == 0 or alpha <= 0.01 or fade_in <= 0.01:
        return frame
    oh, ow = overlay.shape[:2]
    h, w = frame.shape[:2]
    x0, y0 = int(w * cx - ow / 2), int(h * cy - oh / 2)
    x1, y1 = x0 + ow, y0 + oh
    dst_x0, dst_y0 = max(0, x0), max(0, y0)
    dst_x1, dst_y1 = min(w, x1), min(h, y1)
    if dst_x1 <= dst_x0 or dst_y1 <= dst_y0:
        return frame
    src_x0, src_y0 = dst_x0 - x0, dst_y0 - y0
    src_x1, src_y1 = src_x0 + (dst_x1 - dst_x0), src_y0 + (dst_y1 - dst_y0)
    a = overlay[src_y0:src_y1, src_x0:src_x1, 3:4].astype(np.float32) / 255.0
    a = np.clip(a * alpha * fade_in, 0, 1)
    rgb = overlay[src_y0:src_y1, src_x0:src_x1, :3].astype(np.float32)
    region = frame[dst_y0:dst_y1, dst_x0:dst_x1].astype(np.float32)
    frame[dst_y0:dst_y1, dst_x0:dst_x1] = (region * (1 - a) + rgb * a).astype(np.uint8)
    return frame


# ---------------------------------------------------------------------------
# Artwork sprites
# ---------------------------------------------------------------------------

def artwork_sprite(art: np.ndarray, size: int) -> np.ndarray:
    """Center-crop then resize artwork to a size x size RGBA sprite."""
    h, w = art.shape[:2]
    s = min(h, w)
    y0, x0 = (h - s) // 2, (w - s) // 2
    from PIL import Image
    img = Image.fromarray(art[y0:y0 + s, x0:x0 + s])
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    img = img.resize((size, size), Image.LANCZOS)
    return np.asarray(img)


def blend_artwork(frame: np.ndarray, sprite: np.ndarray, *, cx: float, cy: float,
                  scale: float = 1.0, shade: float = 0.0, pulse: float = 0.0) -> np.ndarray:
    """Composite artwork centered at (cx, cy) with scale + darkening + pulse ring."""
    h, w = frame.shape[:2]
    r = int(round(scale * sprite.shape[0]))
    if r <= 4:
        return frame
    if pulse > 0.01:
        draw_ring(frame, cx, cy, int(r * (1.0 + 0.12 * pulse)), width=max(2, int(r * 0.012)),
                  intensity=pulse)
    x0, y0 = int(w * cx - r / 2), int(h * cy - r / 2)
    x1, y1 = x0 + r, y0 + r
    dst_x0, dst_y0 = max(0, x0), max(0, y0)
    dst_x1, dst_y1 = min(w, x1), min(h, y1)
    if dst_x1 <= dst_x0 or dst_y1 <= dst_y0:
        return frame
    src_x0, src_y0 = dst_x0 - x0, dst_y0 - y0
    src_x1, src_y1 = src_x0 + (dst_x1 - dst_x0), src_y0 + (dst_y1 - dst_y0)
    sprite_win = sprite[src_y0:src_y1, src_x0:src_x1]
    a = sprite_win[:, :, 3:4].astype(np.float32) / 255.0
    rgb = sprite_win[:, :, :3].astype(np.float32) * (1.0 - shade)
    region = frame[dst_y0:dst_y1, dst_x0:dst_x1].astype(np.float32)
    frame[dst_y0:dst_y1, dst_x0:dst_x1] = (region * (1 - a) + rgb * a).astype(np.uint8)
    return frame


def draw_ring(frame: np.ndarray, cxF: float, cyF: float, radius: int,
              alpha: float = 1.0, accent: np.ndarray | None = None) -> np.ndarray:
    """Soft pulse ring (cheap distance-field on the neighborhood)."""
    h, w = frame.shape[:2]
    cx, cy = int(w * cxF), int(h * cyF)
    r = int(radius)
    if r <= 2:
        return frame
    # compute distance field only inside the ring bounding box
    y0, x0 = max(0, cy - r - 12), max(0, cx - r - 12)
    y1, x1 = min(h, cy + r + 12), min(w, cx + r + 12)
    if y1 <= y0 or x1 <= x0:
        return frame
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    band = np.clip(1.0 - np.abs(dist - r) / 8.0, 0, 1) * alpha
    col = accent if accent is not None else STYLE_ACCENTS["dark"]
    region = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = np.clip(region + band[:, :, None] * col[None, None, :] * 0.85, 0, 255).astype(np.uint8)
    return frame


# ---------------------------------------------------------------------------
# Waveforms & spectra
# ---------------------------------------------------------------------------

def draw_waveform(frame: np.ndarray, wave: np.ndarray, *, cx: float, cy: float,
                  amp: float = 1.0, rms: float = 0.5, accent: np.ndarray,
                  kind: str = "bars", glow: bool = True) -> np.ndarray:
    """Draw a reactive waveform across the frame at vertical position cy."""
    h, w = frame.shape[:2]
    n = 96
    if len(wave) < 2:
        return frame
    interpolated = np.interp(np.linspace(0, len(wave) - 1, n), np.arange(len(wave)), wave)
    bw = int(w * 0.86)
    x0 = (w - bw) // 2
    y0 = int(h * cy)
    seg_w = max(1, bw // n)
    layer = np.zeros_like(frame)
    col = np.clip(accent, 0, 255).astype(np.uint8)
    max_bar = int(h * 0.16 * amp)
    for i in range(n):
        v = float(interpolated[i]) * (0.3 + 2.2 * rms)
        bar_h = max(2, int(v * max_bar))
        x = x0 + i * seg_w
        if kind == "mirror":
            top = max(0, y0 - bar_h // 2)
            bottom = min(h, y0 + bar_h // 2)
            layer[top:bottom, x:x + seg_w] = col
        elif kind == "line":
            py = y0 - int(v * h * 0.12 * amp)
            if 0 <= py < h:
                layer[py:py + 3, x:x + seg_w] = col
        else:  # bars rising from bottom
            bottom = min(h, y0 + bar_h)
            layer[y0:bottom, x:x + seg_w] = col
    if glow:
        glow_img = box_blur(layer, 4)
        return np.clip(glow_img.astype(np.float32) * 0.35 + frame.astype(np.float32) + layer.astype(np.float32), 0, 255).astype(np.uint8)
    return np.clip(frame.astype(np.float32) + layer.astype(np.float32), 0, 255).astype(np.uint8)


def draw_border_glow(frame: np.ndarray, accent: np.ndarray, intensity: float) -> np.ndarray:
    """Add a subtle neon glow to top & bottom edges (intensity 0..1)."""
    h, w = frame.shape[:2]
    a = np.clip(intensity, 0.0, 1.0)
    if a < 0.02:
        return frame
    fade = np.exp(-np.linspace(0, 6, h // 2))
    edge = (fade[:, None, None] * accent[None, None, :] * a * 0.8).astype(np.float32)
    frame[: h // 2] = np.clip(frame[:h // 2].astype(np.float32) + edge, 0, 255).astype(np.uint8)
    frame[h // 2:] = np.clip(frame[h // 2:].astype(np.float32) + edge[::-1], 0, 255).astype(np.uint8)
    return frame


def draw_radial_spectrum(frame: np.ndarray, bands: np.ndarray, *, cx: float, cy: float,
                         inner: float, accent: np.ndarray, thickness: int = 6) -> np.ndarray:
    """Radial bars around a center point. `bands` is a 0..1 array (len>=4)."""
    h, w = frame.shape[:2]
    n = len(bands)
    cx_i, cy_i = int(w * cx), int(h * cy)
    col = np.clip(accent, 0, 255).astype(np.uint8)
    max_len = int(h * 0.24)
    for i in range(n):
        ang = 2.0 * math.pi * i / n - math.pi / 2
        cos_a, sin_a = math.cos(ang), math.sin(ang)
        length = inner + float(bands[i]) * max_len
        steps = max(2, int(length))
        ts = np.linspace(inner, length, steps).astype(np.int32)
        px = cx_i + (ts * cos_a).astype(np.int32)
        py = cy_i + (ts * sin_a).astype(np.int32)
        for dy in range(-thickness // 2, thickness // 2 + 1):
            for dx in range(-thickness // 2, thickness // 2 + 1):
                if dx * dx + dy * dy > (thickness // 2) ** 2:
                    continue
                ok = (px + dx >= 0) & (px + dx < w) & (py + dy >= 0) & (py + dy < h)
                frame[py[ok] + dy, px[ok] + dx] = col
    return frame


# ---------------------------------------------------------------------------
# Particles
# ---------------------------------------------------------------------------

def make_particles(count: int, height: int, width: int, seed: int = 7) -> dict:
    """Deterministic particle state: x, y, vx, vy, hue_index."""
    rng = np.random.default_rng(seed)
    return {
        "x": rng.uniform(0, width, count),
        "y": rng.uniform(0, height, count),
        "vx": rng.uniform(-0.6, 0.6, count),
        "vy": rng.uniform(-0.9, -0.2, count),
        "h": rng.integers(0, 3, count),
    }


def draw_particles(frame: np.ndarray, parts: dict, *, bass: float, treble: float,
                   drawn: float = 1.0) -> np.ndarray:
    """Advance + draw additive glow particles. mutates `frame`."""
    h, w = frame.shape[:2]
    n = len(parts["x"])
    speed = 1.0 + bass * 6.0
    parts["x"] = parts["x"] + parts["vx"] * speed
    parts["y"] = parts["y"] + parts["vy"] * speed
    # respawn at bottom
    respawn = parts["y"] < -4
    parts["y"][respawn] = h + 4
    parts["x"][respawn] = rng_integers(respawn, w)
    brightness = 0.25 + 0.75 * treble
    colors = np.array([[226, 108, 255], [72, 208, 255], [255, 150, 96]], np.uint8)
    for i in range(n):
        xi, yi = int(parts["x"][i]), int(parts["y"][i])
        if not (0 <= xi < w and 0 <= yi < h):
            continue
        c = colors[parts["h"][i]]
        radius = 2 + int(bass * 3)
        y0, y1 = yi - radius, yi + radius + 1
        x0, x1 = xi - radius, xi + radius + 1
        region = frame[y0:y1, x0:x1].astype(np.float32)
        frame[y0:y1, x0:x1] = np.clip(
            region + c[None, None, :] * (0.18 * drawn * brightness), 0, 255
        ).astype(np.uint8)
    return frame


def rng_integers(mask: np.ndarray, limited: float) -> np.ndarray:
    """Re-randomize x for respawned particles."""
    return np.random.default_rng().uniform(0, limited, mask.sum()) if mask.any() else np.array([])