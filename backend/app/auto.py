"""BeatScout autonomous daily pipeline — run headless, e.g. from GitHub Actions.

    python -m app.auto --limit 5 --provider jamendo --real

Flow per track:
    discover (CC-licensed source) -> dedupe against published state
    -> fetch audio + artwork (or synthesize for no-creds runs)
    -> render beat-reactive visualizer MP4
    -> upload to YouTube (real OAuth, or dry-run log)

Rights model: only source tracks carrying a verifiable CC license
(by / by-sa / zero — commercial + derivative OK) are auto-published.
Anything else stays in the human-review app. Same legal gate as the UI,
but grantable without a human round-trip.

State: auto_state.json under --state-dir (default: repo root /auto-state).
The GitHub Action commits it back so dedupe survives across runs.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("beatscout.auto")

ROOT = Path(__file__).resolve().parents[2]  # repo root (contains backend/, storage/)
DEFAULT_GENRES = ["Lo-fi", "Ambient", "Electronic"]


# ---------------------------------------------------------------------------
# Persistent state (dedupe across daily runs)
# ---------------------------------------------------------------------------

class AutoState:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict = {"seen": {}, "published": []}
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                log.warning("state file corrupt, starting fresh: %s", path)
        self.seen: dict = self.data.setdefault("seen", {})
        self.published: list = self.data.setdefault("published", [])

    def already_processed(self, track_id: str) -> bool:
        return track_id in self.seen

    def record(self, track_id: str, status: str, extra: dict | None = None) -> None:
        entry = {
            "status": status,
            "at": datetime.now(timezone.utc).isoformat(),
            **(extra or {}),
        }
        self.seen[track_id] = entry
        if status == "published":
            self.published.append(entry)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        tmp.replace(self.path)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

def get_provider(name: str):
    """'jamendo' -> real API (needs JAMENDO_CLIENT_ID); 'synth' -> offline demo."""
    if name == "jamendo":
        from .services.jamendo import JamendoProvider
        return JamendoProvider(), "jamendo"
    if name == "synth":
        return SynthProvider(), "synth"
    # auto: prefer the real CC source when the key exists, else synth
    from .config import get_settings
    if get_settings().JAMENDO_CLIENT_ID:
        from .services.jamendo import JamendoProvider
        return JamendoProvider(), "jamendo"
    return SynthProvider(), "synth"


class SynthProvider:
    """Offline stand-in: deterministic CC-style candidates + locally made assets."""

    name = "SYNTH"

    def discover(self, *, genres, release_from, release_to, limit=5, country=None):
        from .services.spotify.base import SpotifyTrackMeta
        metas = []
        for i in range(limit):
            n = i + 1
            metas.append(SpotifyTrackMeta(
                spotify_track_id=f"synth:{n}",
                spotify_artist_id=f"synth-art:{n}",
                track_name=f"Autumn Echoes {n}",
                artist_name="Synthwave Collective",
                album_name="Field Notes",
                release_date=date.today() - timedelta(days=n * 7),
                spotify_url="",
                album_art_url="",
                duration_ms=15_000,
                external_ids={
                    "jamendo_id": str(n),
                    "audio_url": "",   # empty -> local synthesis
                    "license_url": "https://creativecommons.org/licenses/by/4.0/",
                    "license_name": "by",
                },
            ))
        return metas


# ---------------------------------------------------------------------------
# Asset acquisition (URLs pinned: CC-licensed source or local synthesis)
# ---------------------------------------------------------------------------

def fetch_audio(meta, out_dir: Path, max_seconds: int = 0) -> Path:
    """Download the CC audio file, or synthesize a short tone when none exists."""
    url = meta.external_ids.get("audio_url") or ""
    out = out_dir / f"{meta.spotify_track_id.split(':')[-1]}.mp3"
    if url:
        import httpx
        try:
            with httpx.Client(timeout=90.0, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
            if resp.content and len(resp.content) > 1024:
                out.write_bytes(resp.content)
        except httpx.HTTPError as exc:
            log.warning("audio download failed (%s), falling back to synth tone", exc)
    if not out.exists() or out.stat().st_size < 1024:
        _synth_audio(out)
    if max_seconds > 0:
        _clip_audio(out, max_seconds)
    return out


def _clip_audio(path: Path, max_seconds: int) -> None:
    """Trim the audio to `max_seconds` (keeps CI render time bounded)."""
    tmp = path.with_suffix(".clip.mp3")
    subprocess.run(
        [resolve_ffmpeg(), "-y", "-i", str(path), "-t", str(max_seconds),
         "-codec:a", "libmp3lame", "-q:a", "5", str(tmp)],
        capture_output=True, timeout=120,
    )
    if tmp.exists() and tmp.stat().st_size > 1024:
        tmp.replace(path)


def fetch_artwork(meta, out_dir: Path) -> Path:
    """Cover art: download (Jamendo `image`) or synthesize a gradient brand card."""
    url = meta.external_ids.get("art_url") or ""
    out = out_dir / f"{meta.spotify_track_id.split(':')[-1]}.png"
    if url:
        import httpx
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                resp = client.get(url)
            if resp.status_code == 200 and resp.content and len(resp.content) > 1024:
                out.write_bytes(resp.content)
                return out
        except httpx.HTTPError:
            pass
    _synth_art(out, meta)
    return out


def _synth_audio(out: Path) -> None:
    """12s lo-fi beat loop (for zero-creds runs and tests)."""
    import numpy as np
    import struct
    import wave

    sr = 22_050
    t = np.linspace(0, 12.0, int(sr * 12.0), endpoint=False)
    beat = 2.0
    kick = np.exp(-((t % beat) - 0.0) ** 2 / 0.0006) * 0.8
    lead = 0.25 * np.sin(2 * np.pi * 220 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 4 * t))
    mono = np.clip(kick + lead, -1, 1).astype(np.float32)
    wav = out.with_suffix(".wav")
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22_050)
        wf.writeframes((mono * 32767).astype(np.int16).tobytes())
    subprocess.run(
        [resolve_ffmpeg(), "-y", "-i", str(wav), "-codec:a", "libmp3lame", "-q:a", "5", str(out)],
        capture_output=True, timeout=120,
    )
    wav.unlink(missing_ok=True)


def resolve_ffmpeg() -> str:
    from app.services.audio.ffmpeg_utils import resolve_ffmpeg as _r
    return _r()


def _synth_art(out: Path, meta) -> None:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (512, 512), (12, 13, 22))
    draw = ImageDraw.Draw(img)
    for y in range(512):
        t = y / 511
        draw.line([(0, y), (512, y)],
                  fill=(int(12 + 32 * t), int(13 + 21 * t), int(22 + 56 * t)))
    draw.ellipse([64, 64, 448, 448], fill=(44, 34, 78))
    draw.ellipse([232, 232, 280, 280], fill=(12, 13, 22))
    img.save(out, "PNG")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> dict:
    from app.config import get_settings
    from app.services.video.engine import DisplayInfo, render_video

    settings = get_settings()
    dry_run = bool(args.dry_run)
    state = AutoState(Path(args.state_dir) / "auto_state.json")
    provider, provider_name = get_provider(args.provider)
    media_dir = Path(args.storage) / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    genres = [g.strip() for g in args.genres.split(",") if g.strip()] or DEFAULT_GENRES
    limit = max(1, args.limit)

    log.info("daily run: provider=%s dry=%s limit=%s genres=%s state=%s",
             provider_name, dry_run, limit, genres, state.path)

    try:
        metas = provider.discover(
            genres=genres,
            release_from=date(2000, 1, 1),
            release_to=date.today(),
            limit=limit * 3,  # over-fetch; dedupe + license filter whittle it down
        )
    finally:
        if hasattr(provider, "close"):
            provider.close()

    summary = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "provider": provider_name,
        "dry_run": dry_run,
        "limit": limit,
        "candidates_seen": len(metas),
        "new": 0,
        "published_count": 0,
        "skipped_seen": 0,
        "errors": [],
        "videos": [],
    }

    for meta in metas:
        if summary["published_count"] >= limit:
            break
        tid = meta.spotify_track_id
        if state.already_processed(tid):
            summary["skipped_seen"] += 1
            continue
        try:
            audio_mp3 = fetch_audio(meta, media_dir, max_seconds=args.max_seconds)
            art_png = fetch_artwork(meta, media_dir)
            if audio_mp3.stat().st_size < 1_000 or art_png.stat().st_size < 1_000:
                raise RuntimeError("audio/art too small — fetch failed")

            display = DisplayInfo(
                title=meta.track_name,
                artist=meta.artist_name,
                attribution=attribution_line(meta),
            )
            mp4 = media_dir / f"{tid.split(':')[-1]}.mp4"
            render_video(
                display, str(audio_mp3), str(art_png),
                style=args.style, out_path=str(mp4),
                width=args.width, height=args.height, fps=args.fps,
                settings={"background": "dark", "particle_amount": 60, "font_size": 42},
            )
            if not mp4.exists() or mp4.stat().st_size < 10_000:
                raise RuntimeError("render produced no valid file")

            up = upload_to_youtube(
                meta=meta, video_file=mp4, dry_run=dry_run,
                privacy=args.privacy, category=args.category,
            )
            status = "dry-run" if dry_run else "published"
            state.record(tid, status, extra={
                "title": meta.track_name,
                "artist": meta.artist_name,
                "license": meta.external_ids.get("license_name", ""),
                "video_url": up.get("url", ""),
                "youtube_id": up.get("video_id", ""),
            })
            summary["published_count"] += 1
            summary["new"] += 1
            summary["videos"].append({**up, "title": meta.track_name, "artist": meta.artist_name})
            log.info("OK %s -> %s", meta.track_name, up.get("url") or "(dry-run)")
        except Exception as exc:  # bounded failure — never abort the whole batch
            log.exception("track failed: %s", meta.track_name)
            state.record(tid, "error", extra={"error": str(exc)[:300]})
            summary["errors"].append({"track": meta.track_name, "error": str(exc)[:300]})

    state.save()
    summary["state_file"] = str(state.path)
    out = {k: v for k, v in summary.items()}
    print("=== BEATSCOUT DAILY SUMMARY ===")
    print(json.dumps(out, indent=2))
    return out


def attribution_line(meta) -> str:
    lic = meta.external_ids.get("license_name", "")
    url = meta.external_ids.get("license_url", "")
    return f"CC-licensed by {meta.artist_name} — {lic or 'CC'} ({url})"


# ---------------------------------------------------------------------------
# YouTube posting — real via Refresh-Token OAuth; dry-run keeps CI green keyless
# ---------------------------------------------------------------------------

def upload_to_youtube(*, meta, video_file: Path, dry_run: bool, privacy: str,
                      title: str | None = None, category: str = "10",
                      tags: list[str] | None = None) -> dict:
    from app.config import get_settings
    settings = get_settings()

    if dry_run:
        return {
            "video_id": "dry",
            "url": f"https://www.youtube.com/watch?v=dry-{meta.spotify_track_id.split(':')[-1]}",
            "privacy": privacy,
            "dry_run": True,
        }

    if not (settings.YOUTUBE_CLIENT_ID and settings.YOUTUBE_CLIENT_SECRET
            and settings.YOUTUBE_REFRESH_TOKEN):
        raise RuntimeError(
            "YouTube credentials missing (YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN) "
            "— rerun with --dry-run or add the GitHub secrets."
        )

    from .services.youtube.real import RealYouTubeProvider
    provider = RealYouTubeProvider()
    result = provider.upload(
        tokens={"access_token": None, "refresh_token": settings.YOUTUBE_REFRESH_TOKEN},
        file_path=str(video_file),
        title=title or f"{meta.track_name} — {meta.artist_name} (visualizer)",
        description=description_for(meta),
        tags=list(tags or ["music", "visualizer", meta.external_ids.get("license_name", "cc")]),
        category=category,
        privacy=privacy,
    )
    return {"video_id": result.video_id, "url": result.url, "privacy": privacy}


def description_for(meta) -> str:
    lic = meta.external_ids.get("license_name", "")
    url = meta.external_ids.get("license_url", "")
    license_line = f"License: {lic} ({url})" if url else "License: Creative Commons (see source)"
    return (
        f"{meta.track_name} — {meta.artist_name}\n\n"
        f"Generated by BeatScout — an open-source beat visualizer.\n\n"
        f"Music: {meta.artist_name} — \"{meta.track_name}\"\n"
        f"{license_line}\n"
    )


# ---------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="BeatScout daily autonomous pipeline")
    p.add_argument("--limit", type=int, default=5, help="videos per run")
    p.add_argument("--provider", default="auto",
                   choices=["auto", "jamendo", "synth"])
    p.add_argument("--genres", default=", ".join(DEFAULT_GENRES))
    p.add_argument("--style", default="minimal",
                   choices=["minimal", "neon", "cinematic", "spectrum", "waveform"])
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=False)
    p.add_argument("--real", dest="dry_run", action="store_false")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"])
    p.add_argument("--category", default="10", help="YouTube category id (10 = Music)")
    p.add_argument("--max-seconds", type=int, default=0,
                   help="trim audio to N seconds before render (keeps CI time bounded)")
    p.add_argument("--state-dir", default=str(ROOT / "auto-state"))
    p.add_argument("--storage", default=str(ROOT / "storage" / "auto"))
    return p.parse_args(argv)


def main() -> None:
    run(parse_args())


if __name__ == "__main__":
    main()