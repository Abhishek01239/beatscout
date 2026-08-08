"""FFmpeg/FFprobe helpers.

Resolution order for the ffmpeg binary:
  1. ``FFMPEG_BIN`` env var
  2. bundled binary from the ``imageio-ffmpeg`` wheel (modern, libx264+aac)
  3. ``ffmpeg`` on PATH

The bundled binary makes `pip install -e .` sufficient to render videos
on a clean machine (Windows/Linux/macOS).
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

from ...config import get_settings

log = logging.getLogger("beatscout.ffmpeg")


def resolve_ffmpeg() -> str:
    settings = get_settings()
    if settings.FFMPEG_BIN:
        return settings.FFMPEG_BIN
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    path = shutil.which("ffmpeg")
    if path:
        return path
    raise RuntimeError("ffmpeg not found — set FFMPEG_BIN or `pip install imageio-ffmpeg`.")


def _run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    log.debug("ffmpeg %s", " ".join(cmd[:10]) + (" …" if len(cmd) > 10 else ""))
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout, text=True)
    return proc


def probe_duration_ms(path: str) -> int | None:
    """Duration in ms parsed from `ffmpeg -i` stderr (no ffprobe required)."""
    ff = resolve_ffmpeg()
    proc = _run([ff, "-hide_banner", "-i", str(path)])
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr or "")
    if not match:
        return None
    h, m, s = match.groups()
    return int((int(h) * 3600 + int(m) * 60 + float(s)) * 1000)


def decode_to_pcm_wav(path: str, out_wav: str, sample_rate: int = 44100) -> str:
    """Decode any supported audio to a mono float32-ish WAV for analysis.

    ffmpeg normalizes to PCM 16-bit mono; the analysis layer widens to float.
    """
    ff = resolve_ffmpeg()
    proc = _run([
        ff, "-y", "-hide_banner", "-loglevel", "error",
        "-i", path, "-ac", "1", "-ar", str(sample_rate),
        "-c:a", "pcm_s16le",
        out_wav,
    ])
    if proc.returncode != 0 or not Path(out_wav).exists():
        raise RuntimeError(f"ffmpeg decode failed: {proc.stderr[-300:]}")
    return out_wav


def validate_media_file(path: str) -> dict:
    """Return {streams, codec, duration_ms} or raise ValueError."""
    ff = resolve_ffmpeg()
    proc = _run([ff, "-hide_banner", "-i", path])
    if "Stream #" not in (proc.stderr or ""):
        raise ValueError("Not a playable media file")
    stderr = proc.stderr or ""
    audio = re.search(r"Stream #0:\d+.*?Audio:\s*(\w+)", stderr)
    duration = probe_duration_ms(path)
    return {"codec": audio.group(1) if audio else None, "duration_ms": duration}


def render_video_frames(frames_iter, out_path: str, *, fps: int, width: int, height: int,
                        audio: str | None = None, crf: int = 21) -> None:
    """Pipe raw RGB24 frames into ffmpeg and mux with optional audio.

    `frames_iter` yields (height, width, 3) uint8 numpy arrays.
    """
    import numpy as np

    ff = resolve_ffmpeg()
    cmd = [
        ff, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
        "-r", str(fps), "-i", "-",
    ]
    if audio:
        cmd += ["-i", audio]
        cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            out_path]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for frame in frames_iter:
            arr = np.asarray(frame, dtype=np.uint8)
            if arr.ndim != 3 or arr.shape[2] != 3:
                raise ValueError(f"frame must be HxWx3, got {arr.shape}")
            proc.stdin.write(arr.tobytes())
        proc.stdin.close()
        proc.wait(timeout=900)
    except BrokenPipeError as exc:
        stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        raise RuntimeError(f"ffmpeg pipe closed early:\n{stderr[-500:]}") from exc

    if proc.returncode != 0 or not Path(out_path).exists():
        stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        raise RuntimeError(f"video render failed (rc={proc.returncode}):\n{stderr[-500:]}")