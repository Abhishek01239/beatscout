"""Video engine: beat-reactive visualizer renderer.

Renders 1920x1080@30 (configurable) H.264+AAC MP4s that react to the real
audio: bass/mid/treble/RMS/onset/beat drive scale, opacity, particles,
waveform amplitude, spectrum height, camera drift and glow intensity.

Styles: minimal | neon | cinematic | spectrum | pulse.

Legal gate: this module must only be called for tracks whose rights are
APPROVED — enforced upstream by :mod:`app.services.rights`.

Pipeline:
    analyze_audio(audio) -> ReactiveFeatures -> per-frame features ->
    style renderer -> raw RGB frames piped to ffmpeg (H.264) + audio (AAC).
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field

import numpy as np

from ..audio.analysis import analyze_audio
from ..audio.ffmpeg_utils import probe_duration_ms, render_video_frames
from .prep import (
    STYLE_ACCENTS,
    STYLE_BACKGROUNDS,
    artwork_sprite,
    blend_artwork,
    blend_overlay,
    box_blur,
    draw_border_glow,
    draw_particles,
    draw_radial_spectrum,
    draw_ring,
    draw_waveform,
    make_background,
    make_particles,
    text_overlay,
)

log = logging.getLogger("beatscout.video.engine")

TEMPLATES = ("minimal", "neon", "cinematic", "spectrum", "pulse")

# Human-readable metadata for each template (used for seeding + UI).
STYLE_DEFAULTS: dict[str, dict] = {
    "minimal": {
        "description": "Album artwork centered, animated waveform, title + artist, subtle background movement.",
        "defaults": {"background": "dark", "artwork_position": "center", "waveform_type": "mirror"},
    },
    "neon": {
        "description": "Dynamic spectrum bars, glow effects, beat-reactive particles, animated artwork.",
        "defaults": {"background": "midnight", "artwork_position": "center_left", "waveform_type": "bars", "particle_amount": 70},
    },
    "cinematic": {
        "description": "Blurred artwork background, slow camera movement, minimal typography, audio-reactive particles.",
        "defaults": {"background": "film", "artwork_position": "center", "waveform_type": "line"},
    },
    "spectrum": {
        "description": "Large circular spectrum with album artwork in the center, beat-reactive bars.",
        "defaults": {"background": "ocean", "artwork_position": "center", "waveform_type": "radial"},
    },
    "pulse": {
        "description": "Background gradient, pulsing artwork synchronized to the beat.",
        "defaults": {"background": "ember", "artwork_position": "center", "waveform_type": "bars"},
    },
}


@dataclass
class DisplayInfo:
    """Text shown in the visualizer."""
    title: str
    artist: str = ""
    attribution: str | None = None


# ---------------------------------------------------------------------------
# Feature table
# ---------------------------------------------------------------------------

class ReactiveFeatures:
    """Per-video-frame audio features, normalized to 0..1."""

    def __init__(self, analysis: dict, fps: int):
        self.fps = max(1, fps)
        self.duration_ms = int(analysis.get("duration_ms", 0))
        src_n = len(analysis.get("rms", []))
        raw = {
            "bass": analysis.get("bass") or [0.0] * src_n,
            "mid": analysis.get("mid") or [0.0] * src_n,
            "treble": analysis.get("treble") or [0.0] * src_n,
            "rms": analysis.get("rms") or [0.0] * src_n,
            "onset": analysis.get("onset") or [0.0] * src_n,
            "beat": analysis.get("beat") or [0.0] * src_n,
            "centroid": analysis.get("centroid") or [0.0] * src_n,
        }
        norm: dict[str, np.ndarray] = {}
        for key, arr in raw.items():
            a = np.asarray(arr, dtype=np.float64)
            if a.size >= 3:
                a = np.convolve(a, [0.25, 0.5, 0.25], mode="same")
            lo, hi = float(np.percentile(a, 3)), float(np.percentile(a, 97))
            rng = max(hi - lo, 1e-9)
            norm[key] = np.clip((a - lo) / rng, 0.0, 1.0)
        self.n_out = max(1, int(round(self.duration_ms / 1000 * self.fps)))
        self.arrays = {k: _resample(v, self.n_out) for k, v in norm.items()}
        self.bpm = float(analysis.get("bpm") or 0.0)
        self.wave = self.arrays["rms"] if self.n_out else np.zeros(8)

    def get(self, i: int) -> dict[str, float]:
        i = min(max(i, 0), self.n_out - 1)
        return {k: float(v[i]) for k, v in self.arrays.items()}


def _resample(arr: np.ndarray, n: int) -> np.ndarray:
    if n == len(arr):
        return arr
    idx = np.linspace(0, len(arr) - 1, n)
    return np.interp(idx, np.arange(len(arr)), arr)


# ---------------------------------------------------------------------------
# Helpers used by several styles
# ---------------------------------------------------------------------------

def _glow_overlay(height: int, width: int, strength: float,
                  accent: np.ndarray) -> np.ndarray:
    """RGBA full-frame overlay of a soft radial glow (for breathing)."""
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    d2 = (xx - width * 0.5) ** 2 + (yy - height * 0.42) ** 2
    radial = np.exp(-d2 / float(2 * (width * 0.3) ** 2)) * strength
    img = np.zeros((height, width, 3), np.float32)
    img += radial[:, :, None] * accent[None, None, :]
    alpha = (np.clip(radial, 0, 1) * 200).astype(np.uint8)
    return np.dstack([np.clip(img, 0, 255).astype(np.uint8), alpha])


def _vignette(height: int, width: int, strength: float = 0.55) -> np.ndarray:
    """HxWx1 multiplier darkening the edges (0..1)."""
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    d = np.sqrt(((xx - width / 2) / (width / 2)) ** 2 + ((yy - height / 2) / (height / 2)) ** 2)
    return np.clip(1.0 - strength * np.clip(d - 0.55, 0, 1) / 0.45, 0.05, 1.0)[:, :, None]


# ---------------------------------------------------------------------------
# Base renderer
# ---------------------------------------------------------------------------

class StyleRenderer:
    """Base class; `.frame(i)` returns an HxWx3 uint8 array."""

    def __init__(self, feats: ReactiveFeatures, info: DisplayInfo, art: np.ndarray,
                 *, width: int, height: int, bg: str = "dark",
                 particle_amount: int = 0, font_size: int = 44,
                 intensity: float = 1.0, waveform_type: str = "bars"):
        self.feats = feats
        self.info = info
        self.w, self.h = width, height
        self.bg_name = bg if bg in STYLE_BACKGROUNDS else "dark"
        self.intensity = max(0.0, min(3.0, intensity))
        self.waveform_type = waveform_type if waveform_type in ("bars", "mirror", "line") else "bars"
        self.art = art
        self.sprite = artwork_sprite(art, 640)
        self.accent = STYLE_ACCENTS[self.bg_name].copy()
        self.count = max(0, particle_amount)
        self.particles = make_particles(self.count, height, width) if self.count else {}
        self.base_bg = make_background(self.h, self.w, self.bg_name, 0.0)

        from ..artwork import _font
        self.title_ov = text_overlay(info.title.title(), _font(font_size),
                                     color=(255, 255, 255), alpha=248)
        self.artist_ov = text_overlay(info.artist.upper(), _font(max(13, font_size // 2)),
                                      color=(212, 214, 224), alpha=198)
        self.meta_ov = (text_overlay(info.attribution or "", _font(15),
                                     color=(172, 174, 192), alpha=150)
                        if info.attribution else np.zeros((0, 0, 4), np.uint8))

    # -- shared pieces ------------------------------------------------------

    def fade(self, i: int, dur: int = 30) -> float:
        return min(1.0, i / max(1, dur))

    def add_texts(self, frame: np.ndarray, i: int, *, cx: float = 0.5,
                  title_cy: float = 0.14, artist_cy: float | None = None) -> np.ndarray:
        f = self.fade(i)
        frame = blend_overlay(frame, self.title_ov, cx=cx, cy=title_cy, fade_in=f)
        ay = artist_cy if artist_cy is not None else title_cy + 0.055
        frame = blend_overlay(frame, self.artist_ov, cx=cx, cy=ay, alpha=0.92, fade_in=f)
        if self.meta_ov.shape[0]:
            frame = blend_overlay(frame, self.meta_ov, cx=0.5, cy=0.94, alpha=0.55, fade_in=f)
        return frame

    def add_particles(self, frame: np.ndarray, i: int, f: dict[str, float],
                      factor: float = 1.0) -> np.ndarray:
        if self.particles:
            frame = draw_particles(frame, self.particles, bass=f["bass"] * factor,
                                   treble=f["treble"] * factor, drawn=0.6 * self.fade(i))
        return frame

    def base_frame(self) -> np.ndarray:
        return self.base_bg.copy()

    def artifact(self, frame: np.ndarray) -> np.ndarray:
        return frame

    # -- API ---------------------------------------------------------------

    def render(self, i: int) -> np.ndarray:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Style 1 — Minimal
# ---------------------------------------------------------------------------

class MinimalRenderer(StyleRenderer):
    def render(self, i: int) -> np.ndarray:
        f = self.feats.get(i)
        frame = self.base_frame()
        # breathing radial glow, independent of the beat
        pulse = (math.sin(i / 70.0) * 0.5 + 0.5) * 0.35 * self.intensity
        frame = blend_overlay(frame, _glow_overlay(self.h, self.w, pulse, self.accent),
                              cx=0.5, cy=0.4, alpha=0.3)
        # artwork centered; scales subtly with the beat envelope
        scale = 0.40 + 0.035 * f["beat"] * self.intensity
        frame = blend_artwork(frame, self.sprite, cx=0.5, cy=0.5, scale=scale)
        # mirror waveform at the bottom
        frame = draw_waveform(frame, self.feats.wave, cx=0.5, cy=0.84,
                              amp=0.5 * self.intensity, rms=f["rms"],
                              accent=self.accent, kind=self.waveform_type, glow=True)
        return self.add_texts(frame, i, title_cy=0.10, artist_cy=0.045)


# ---------------------------------------------------------------------------
# Style 2 — Neon
# ---------------------------------------------------------------------------

class NeonRenderer(StyleRenderer):
    def render(self, i: int) -> np.ndarray:
        f = self.feats.get(i)
        frame = self.base_frame()
        # spectrum bars rising from the lower third
        frame = draw_waveform(frame, self.feats.arrays["mid"], cx=0.5, cy=0.70,
                              amp=1.3 * self.intensity, rms=f["bass"],
                              accent=self.accent, kind="bars", glow=True)
        # border glow pulses with the beat
        frame = draw_border_glow(frame, self.accent, f["beat"] * 0.85 * self.intensity)
        frame = self.add_particles(frame, i, f, factor=1.0)
        # artwork: small, right-of-center, pulsing
        scale = 0.28 + 0.045 * f["beat"] * self.intensity
        frame = blend_artwork(frame, self.sprite, cx=0.80, cy=0.32, scale=scale,
                              pulse=f["beat"])
        return self.add_texts(frame, i, title_cy=0.88, artist_cy=0.955)


# ---------------------------------------------------------------------------
# Style 3 — Dark Cinematic
# ---------------------------------------------------------------------------

class CinematicRenderer(StyleRenderer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from PIL import Image
        # oversized blurred backdrop for the slow camera drift
        art = Image.fromarray(self.art).convert("RGB")
        art = art.resize((int(self.w * 1.35), int(self.h * 1.35)), Image.LANCZOS)
        self.backdrop = box_blur(np.asarray(art), radius=12)
        self.vig = _vignette(self.h, self.w, strength=0.6)

    def render(self, i: int) -> np.ndarray:
        f = self.feats.get(i)
        bw, bh = self.backdrop.shape[1], self.backdrop.shape[0]
        # slow camera movement
        dx = int((math.sin(i / 90.0) * 0.5 + 0.5) * (bw - self.w))
        dy = int((math.cos(i / 130.0) * 0.5 + 0.5) * (bh - self.h))
        frame = self.backdrop[dy:dy + self.h, dx:dx + self.w].copy()
        frame = np.clip(frame.astype(np.float32) * self.vig, 0, 255).astype(np.uint8)
        frame = self.add_particles(frame, i, f, factor=0.5)
        return self.add_texts(frame, i, title_cy=0.86, artist_cy=0.93)


# ---------------------------------------------------------------------------
# Style 4 — Spectrum
# ---------------------------------------------------------------------------

class SpectrumRenderer(StyleRenderer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rays = 48
        self.phases = np.random.default_rng(11).uniform(0, 2 * np.pi, self.rays)

    def render(self, i: int) -> np.ndarray:
        f = self.feats.get(i)
        frame = self.base_frame()
        bands = np.zeros(self.rays)
        for r in range(self.rays):
            p = (self.phases[r] + i * 0.01) % 1.0
            mix = (f["mid"] * 0.5 + f["bass"] * 0.30 * (1 - p) + f["treble"] * 0.2 * p)
            bands[r] = np.clip(mix * (0.55 + 0.5 * f["beat"]) + 0.02 * math.sin(p * 6.28 + r), 0, 1)
        frame = draw_radial_spectrum(frame, bands, cx=0.5, cy=0.5, inner=230,
                                     accent=self.accent, thickness=5)
        # artwork in the middle, rotating slowly via pulse ring
        frame = blend_artwork(frame, self.sprite, cx=0.5, cy=0.5, scale=0.30,
                              pulse=f["beat"])
        if f["beat"] > 0.5:
            frame = draw_ring(frame, 0.5, 0.5, int(self.w * 0.20),
                              alpha=0.5 * f["beat"], accent=self.accent)
        return self.add_texts(frame, i, title_cy=0.88, artist_cy=0.955)


# ---------------------------------------------------------------------------
# Style 5 — Pulse
# ---------------------------------------------------------------------------

class PulseRenderer(StyleRenderer):
    def render(self, i: int) -> np.ndarray:
        f = self.feats.get(i)
        # gradient background pulses with the beat
        frame = make_background(self.h, self.w, self.bg_name, pulse=f["beat"] * self.intensity)
        # expanding rings
        base_r = int(min(self.w, self.h) * 0.30)
        for rr in range(3):
            r = base_r + rr * 110 + int(f["beat"] * 130 * self.intensity)
            frame = draw_ring(frame, 0.5, 0.5, r, alpha=0.22, accent=self.accent)
        # artwork breathes with the beat
        scale = 0.36 + 0.06 * f["beat"] * self.intensity
        frame = blend_artwork(frame, self.sprite, cx=0.5, cy=0.5, scale=scale,
                              pulse=f["beat"])
        # bass-driven bar at the very bottom
        frame = draw_waveform(frame, self.feats.wave, cx=0.5, cy=0.94,
                              amp=0.30 * self.intensity, rms=f["bass"],
                              accent=self.accent, kind="bars", glow=False)
        return self.add_texts(frame, i, title_cy=0.10, artist_cy=0.045)


# ---------------------------------------------------------------------------
# Registry + entrypoint
# ---------------------------------------------------------------------------

RENDERERS = {
    "minimal": MinimalRenderer,
    "neon": NeonRenderer,
    "cinematic": CinematicRenderer,
    "spectrum": SpectrumRenderer,
    "pulse": PulseRenderer,
}


def render_video(
    info: DisplayInfo,
    audio_file: str,
    art_file: str,
    style: str = "minimal",
    *,
    out_path: str | None = None,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    settings: dict | None = None,
    preview_seconds: float | None = None,
    progress=None,
) -> dict:
    """Render a beat-reactive visualizer MP4 from a rights-cleared audio file.

    Returns: {path, width, height, fps, duration_ms, bpm, style}.
    """
    from PIL import Image

    style = style if style in RENDERERS else "minimal"
    settings = settings or {}

    log.info("render start: style=%s %dx%d@%d audio=%s", style, width, height, fps,
             str(audio_file).rsplit("/", 1)[-1])
    features = analyze_audio(audio_file, fps)
    feats = ReactiveFeatures(features, fps)

    art_arr = np.asarray(Image.open(art_file).convert("RGB"))
    renderer = RENDERERS[style](
        feats, info, art_arr,
        width=width, height=height,
        bg=settings.get("background", "dark"),
        particle_amount=int(settings.get("particle_amount", 60)),
        font_size=int(settings.get("font_size", 42)),
        intensity=float(settings.get("animation_intensity", 1.0)),
        waveform_type=settings.get("waveform_type", "bars"),
    )

    total_frames = feats.n_out
    if preview_seconds:
        total_frames = min(total_frames, max(1, int(preview_seconds * fps)))

    def frames():
        for i in range(total_frames):
            yield renderer.render(i)
            if progress and i % 4 == 0:
                progress(min(i / max(total_frames, 1), 1.0))

    out = out_path or f"beatscout_{style}_{int(time.time())}.mp4"
    render_video_frames(frames(), out, fps=fps, width=width, height=height, audio=audio_file)
    duration = probe_duration_ms(out)
    log.info("render complete: %s (%.1fs)", out, (duration or 0) / 1000)
    if progress:
        progress(1.0)
    return {
        "path": out,
        "width": width,
        "height": height,
        "fps": fps,
        "duration_ms": duration or feats.duration_ms,
        "bpm": feats.bpm,
        "style": style,
    }