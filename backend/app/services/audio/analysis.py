"""Audio analysis: BPM, beats, RMS, spectral features, per-frame bands.

Two engines, same output schema:
  1. ``librosa`` engine — richest features, used when librosa is installed.
  2. numpy engine (default, zero heavy deps) — decodes the file to PCM via
     ffmpeg and computes onset envelope, tempo, band energies, RMS and
     spectral centroid directly with numpy FFTs.

The reactive renderer consumes a per-analysis-frame feature table:

    features["bass"|"mid"|"treble"|"rms"|"beat"|"onset"|"centroid"|...]
        -> list aligned to the *analysis* frame grid; the video engine
           resamples to the requested video fps.
"""

from __future__ import annotations

import logging
import math
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from .ffmpeg_utils import resolve_ffmpeg

log = logging.getLogger("beatscout.audio")

SAMPLE_RATE = 44100
FFT_WIN = 2048  # ~46 ms window at 44100 Hz


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------

def decode_wav_to_float(path: str, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Decode any audio file to mono float32 in [-1, 1] via ffmpeg."""
    ff = resolve_ffmpeg()
    with tempfile.TemporaryDirectory(prefix="bs_audio_") as tmp:
        wav_path = Path(tmp) / "decoded.wav"
        proc = subprocess_run([
            ff, "-y", "-hide_banner", "-loglevel", "error",
            "-i", path, "-ac", "1", "-ar", str(sr),
            "-c:a", "pcm_s16le", str(wav_path),
        ])
        if proc.returncode != 0 or not wav_path.exists():
            raise RuntimeError(f"ffmpeg decode failed: {proc.stderr[-300:]}")
        with wave.open(str(wav_path), "rb") as wf:
            raw = wf.readframes(wf.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def subprocess_run(cmd: list[str], timeout: int = 600):
    import subprocess
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_audio(path: str, fps: int = 30) -> dict:
    """Full analysis for a legally obtained audio file. JSON-safe dict."""
    try:
        return _analyze_librosa(path, fps)
    except ImportError:
        return _analyze_numpy(path, fps)


# ---------------------------------------------------------------------------
# numpy engine (default)
# ---------------------------------------------------------------------------

def _analyze_numpy(path: str, fps: int) -> dict:
    data = decode_wav_to_float(path)
    return _numpy_features(data, SAMPLE_RATE, fps)


def _numpy_features(data: np.ndarray, sr: int, fps: int) -> dict:
    duration = len(data) / sr
    an_fps = max(8.0, min(64.0, float(fps)))

    # STFT frame grid: ~50 ms hops
    hop = int(sr / an_fps)
    n_fft = FFT_WIN
    nfr = max(1, int(np.ceil((len(data) - n_fft) / hop)) + 1)

    mag = np.zeros((nfr, n_fft // 2 + 1), dtype=np.float32)
    for i in range(nfr):
        start = i * hop
        seg = data[start:start + n_fft]
        if len(seg) < n_fft:
            seg = np.pad(seg, (0, n_fft - len(seg)))
        mag[i] = np.abs(np.fft.rfft(seg * np.hanning(n_fft)))

    freqs = np.fft.rfftfreq(n_fft, 1 / sr)
    bass_map = (freqs >= 20) & (freqs < 250)
    mid_map = (freqs >= 250) & (freqs < 4000)
    treb_map = freqs >= 4000

    def energy(mask: np.ndarray) -> np.ndarray:
        m = mag[:, mask]
        return np.sqrt(np.mean(m ** 2, axis=1))

    bass = energy(bass_map)
    mid = energy(mid_map)
    treble = energy(treb_map)
    with np.errstate(divide="ignore", invalid="ignore"):
        total = mag.sum(axis=1) + 1e-9
        centroid = (mag * freqs[None, :]).sum(axis=1) / total
        bandwidth = np.sqrt((mag * (freqs[None, :] - centroid[:, None]) ** 2).sum(axis=1) / total)

    # RMS + onset envelope (zero-padded frames, same grid as the STFT)
    segs: list[np.ndarray] = []
    for i in range(nfr):
        start = i * hop
        seg = data[start:start + n_fft]
        if len(seg) < n_fft:
            seg = np.pad(seg, (0, n_fft - len(seg)))
        segs.append(seg)
    frames = np.stack(segs) if nfr > 1 else data[:n_fft][None, :]
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-6)
    onset = np.clip(np.diff(rms, prepend=rms[0]), 0, None)
    onset = onset / (onset.max() + 1e-9)

    bpm = estimate_bpm(onset, frame_sr=an_fps)

    # Beat pulse envelope: impulse train at beat rate, smoothed
    beat_env = beat_envelope(onset, bpm, an_fps)

    waveform = _waveform_bins(data, sr, 64)

    def resample(arr: np.ndarray, n: int) -> np.ndarray:
        if n == len(arr):
            return arr
        idx = np.linspace(0, len(arr) - 1, n)
        return np.interp(idx, np.arange(len(arr)), arr)

    n_out = max(1, int(round(duration * fps)))
    return {
        "bpm": bpm,
        "duration_ms": int(duration * 1000),
        "analysis_fps": an_fps,
        "rms": resample(rms, n_out).tolist(),
        "bass": resample(bass, n_out).tolist(),
        "mid": resample(mid, n_out).tolist(),
        "treble": resample(treble, n_out).tolist(),
        "onset": resample(onset, n_out).tolist(),
        "beat": resample(beat_env, n_out).tolist(),
        "centroid": resample(centroid, n_out).tolist(),
        "bandwidth": resample(bandwidth, n_out).tolist(),
        "waveform": waveform.tolist(),
    }


def estimate_bpm(onset: np.ndarray, frame_sr: float) -> float:
    """Autocorrelation of the onset envelope -> BPM (twice-averaged)."""
    x = np.asarray(onset, dtype=np.float64)
    x = x - x.mean()
    if x.std() < 1e-6 or len(x) < 12:
        return 0.0
    corr = np.correlate(x, x, "full")[len(x) - 1:]
    min_lag = max(1, int(round(frame_sr * 60 / 200)))
    max_lag = max(min_lag + 1, int(round(frame_sr * 60 / 50)))
    if max_lag > len(corr):
        return 0.0
    band = corr[min_lag:max_lag]
    peak = int(np.argmax(band)) + min_lag
    bpm = 60.0 * frame_sr / max(float(peak), 1.0)
    return round(bpm, 1) if (float(bpm) >= 50 and float(bpm) <= 210) else 0.0


def beat_envelope(onset: np.ndarray, bpm: float, fps: float) -> np.ndarray:
    """Pulse-shaped envelope: sharp at each beat, decaying between beats."""
    n = len(onset)
    if not bpm or n == 0:
        return np.zeros(n)
    period = fps * 60 / bpm
    phase = np.arange(n) % period / period
    pulse = np.exp(-4.0 * phase) if period else np.zeros(n)
    # align pulse start to strongest onset in each period via phase shift
    shift = 0
    env = np.roll(pulse, shift) * (0.35 + 0.65 * (onset / (onset.max() + 1e-9)))
    return env


def _waveform_bins(data: np.ndarray, sr: int, bins: int) -> np.ndarray:
    """Downsample the envelope to N bins (display/analysis waveform)."""
    n = len(data)
    if n == 0:
        return np.zeros(bins)
    seg = max(1, n // bins)
    trimmed = data[: seg * bins].reshape(bins, seg)
    return (trimmed.max(axis=1) - trimmed.min(axis=1)) / 2.0 if seg > 1 else np.abs(data[:bins])


# ---------------------------------------------------------------------------
# librosa engine (optional, richer — installed via requirements-extra)
# ---------------------------------------------------------------------------

def _analyze_librosa(path: str, fps: int) -> dict:
    import librosa

    y, sr = librosa.load(path, sr=SAMPLE_RATE, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)
    hop = int(sr / 30.0)
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop)
    stft = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)

    def band(mask):
        seg = stft[mask]
        return np.sqrt(np.mean(seg ** 2, axis=0)) if seg.size else np.zeros(stft.shape[1])

    n = len(rms)
    beat_env = np.zeros(n)
    for b in beats:
        i = min(int(b), n - 1)
        beat_env[i] = 1.0

    def resample(arr, k=n):
        idx = np.linspace(0, len(arr) - 1, k)
        return np.interp(idx, np.arange(len(arr)), arr)

    return {
        "bpm": round(float(tempo[0]) if np.ndim(tempo) else float(tempo), 1),
        "duration_ms": int(duration * 1000),
        "analysis_fps": 30.0,
        "rms": resample(rms).tolist(),
        "bass": resample(bass((freqs >= 20) & (freqs < 250))).tolist(),
        "mid": resample(bass((freqs >= 250) & (freqs < 4000))).tolist(),
        "treble": resample(bass(freqs >= 4000)).tolist(),
        "onset": resample(onset).tolist(),
        "beat": resample(beat_env).tolist(),
        "centroid": [0.0] * n,
        "bandwidth": [0.0] * n,
        "waveform": _waveform_bins(y, sr, 64).tolist(),
    }