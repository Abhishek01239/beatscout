"""Demo data seeding — first-run experience without any API keys.

Creates the demo user + a full mock catalog: discovered tracks, a couple
of APPROVED tracks with synthesized legal demo audio, one rendered preview
video and a connected mock YouTube account, so every screen of the UI is
explorable immediately.
"""

from __future__ import annotations

import logging
import math
import wave
from pathlib import Path

import numpy as np

from ..config import get_settings
from ..database import SessionLocal, init_db
from ..models import (
    Artist, AudioSource, Automation, Job, License, Permission, Track, User,
    Video, VideoTemplate, YouTubeAccount, YouTubeUpload,
)
from ..security import hash_password

log = logging.getLogger("beatscout.seed")

DEMO_EMAIL = "demo@beatscout.app"
DEMO_PASSWORD = "demo1234"


def seed_demo(force: bool = False) -> bool:
    """Seed demo data if the database is empty. Returns True when seeded."""
    init_db()
    db = SessionLocal()
    try:
        if not force and db.query(Track).count() > 0:
            return False
        log.info("seeding demo data…")
        user = db.query(User).filter(User.email == DEMO_EMAIL).first()
        if user is None:
            user = User(email=DEMO_EMAIL, name="Demo Operator",
                        password_hash=hash_password(DEMO_PASSWORD))
            db.add(user)
            db.flush()
        elif force:
            _wipe(db)

        _seed_templates(db)
        _seed_catalog(db, user)
        _seed_youtube(db, user)
        _seed_automation(db, user)
        db.commit()
        log.info("demo data seeded")
        return True
    finally:
        db.close()


def _wipe(db) -> None:
    for model in (Job, YouTubeUpload, Video, Permission, License, AudioSource,
                  Track, Artist, Automation, VideoTemplate, YouTubeAccount):
        db.query(model).delete()


def _seed_templates(db) -> None:
    from ..services.video.engine import STYLE_DEFAULTS
    for name, meta in STYLE_DEFAULTS.items():
        if db.query(VideoTemplate).filter(VideoTemplate.name == name).first():
            continue
        db.add(VideoTemplate(name=name, label=name.capitalize(),
                             description=meta["description"], defaults=meta["defaults"]))


def _seed_catalog(db, user: User) -> None:
    """Discover via the mock provider and wire up a rich demo state."""
    from ..services.discovery import DiscoveryConfig, discover_and_persist
    from ..services.spotify.mock import MockSpotifyProvider

    provider = MockSpotifyProvider()
    # create tracks through the discovery path (scoring + persistence)
    discover_and_persist(db, user.id, DiscoveryConfig(release_window_days=1200,
                                                      genres=[], max_tracks=24))

    tracks = db.query(Track).filter(Track.user_id == user.id).order_by(
        Track.discovery_score.desc()).all()

    for i, track in enumerate(tracks):
        # artwork: ensure local covers exist (mock provider art spec)
        from ..services.artwork import ensure_artwork
        ensure_artwork(track)
        if i < 2:
            _make_approved(db, user, track, i)
        elif i < 5:
            track.status = "PERMISSION_REQUIRED"
            track.rights_status = "REQUESTED"
            db.add(Permission(track_id=track.id, user_id=user.id,
                              status="REQUESTED", artist=track.artist_name,
                              email=f"mgmt@{track.artist_name.lower().replace(' ', '')}.demo"))
    db.flush()

    # render one small preview video for the first APPROVED track
    approved = [t for t in tracks if t.rights_status == "APPROVED"]
    if approved:
        _render_demo_video(db, user, approved[0])


def _make_approved(db, user: User, track: Track, idx: int) -> None:
    """Attach synthetic legal demo audio + license to a track."""
    audio_path = _synthesize_demo_audio(track, idx)
    audio = AudioSource(
        track_id=track.id,
        original_filename=f"demo_{track.track_name.replace(' ', '_')}.wav",
        file_path=str(audio_path),
        format="wav",
        size_bytes=audio_path.stat().st_size,
        duration_ms=None,
        checksum_sha512="demo" + "0" * 60,
        status="ready",
    )
    db.add(audio)
    db.flush()
    from ..services.audio.ffmpeg_utils import probe_duration_ms
    audio.duration_ms = probe_duration_ms(str(audio_path))

    lic = License(
        track_id=track.id,
        audio_source="artist_upload",
        license_name="Artist permission (demo)",
        commercial_use=True,
        youtube_use=True,
        modification_allowed=True,
        attribution_required=True,
        attribution_text=f"{track.artist_name} — {track.track_name}",
        verified_by="demo@beatscout.app",
        verified_at=__import__("datetime").datetime.utcnow(),
    )
    db.add(lic)
    track.rights_status = "APPROVED"
    track.status = "LICENSED"
    db.add(Permission(track_id=track.id, user_id=user.id, status="APPROVED",
                      artist=track.artist_name, email=f"artist@{idx}.demo",
                      permission_text="Demo artist granted permission to use this track.",
                      license_type="artist_upload", commercial_use=True, youtube_use=True,
                      modification_allowed=True, attribution_required=True,
                      attribution_text=f"{track.artist_name} — {track.track_name}",
                      approved_at=__import__("datetime").datetime.utcnow()))


def _render_demo_video(db, user: User, track: Track) -> None:
    """Render a short preview video so the dashboard has a real MP4."""
    from ..services.video.service import render_for_track
    try:
        render_for_track(db, track, style="minimal", as_preview=True)
    except Exception as exc:
        log.warning("demo video render skipped: %s", exc)


def _synthesize_demo_audio(track: Track, idx: int) -> Path:
    """Generate a short legal demo track (original composition, 24s)."""
    settings = get_settings()
    out = settings.storage_dir / "media" / "demo" / f"demo_{track.id}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        return out

    sr = 44100
    dur = 24.0
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    bpm = 92 + idx * 6
    beat = 60.0 / bpm
    # chord progression: Am - F - C - G
    chords = [
        [220.0, 261.63, 329.63],
        [174.61, 220.0, 261.63],
        [130.81, 164.81, 196.0],
        [196.0, 246.94, 293.66],
    ]
    audio = np.zeros_like(t)
    for bar in range(int(dur / (beat * 4))):
        chord = chords[bar % 4]
        bar_t = bar * beat * 4
        for f0 in chord:
            seg = np.sin(2 * np.pi * f0 * t) * (t > bar_t) * (t < bar_t + beat * 4)
            seg *= np.exp(-3 * ((t - bar_t) % (beat * 4)) / (beat * 4))
            audio += seg * 0.16
        # kick on every beat
        for b in range(4):
            bt = bar_t + b * beat
            env = np.exp(-14 * np.maximum(t - bt, 0.0))
            kick = np.sin(2 * np.pi * 55 * t) * env * (t >= bt)
            audio += kick * 0.5
        # hat on off-beats
        for b in range(4):
            bt = bar_t + b * beat + beat / 2
            env = np.exp(-80 * np.maximum(t - bt, 0.0))
            hat = np.random.default_rng(bar * 10 + b).uniform(-1, 1, len(t)) * env * (t >= bt)
            audio += hat * 0.08
    audio = np.clip(audio * 0.5, -1, 1)

    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((audio * 32767).astype(np.int16).tobytes())
    return out


def _seed_youtube(db, user: User) -> None:
    existing = db.query(YouTubeAccount).filter(YouTubeAccount.user_id == user.id).first()
    if existing:
        return
    db.add(YouTubeAccount(
        user_id=user.id,
        channel_id="UC-mock-channel-0001",
        channel_name="BeatScout Demo Channel",
        subscriber_count=1240,
        video_count=12,
        access_token="mock-token",
        refresh_token="mock-refresh",
        status="connected",
    ))


def _seed_automation(db, user: User) -> None:
    if db.query(Automation).filter(Automation.user_id == user.id).first():
        return
    db.add(Automation(
        user_id=user.id,
        name="Daily emerging-artist scan",
        enabled=True,
        discovery_frequency_hours=24,
        max_tracks_per_run=10,
        max_videos_per_day=2,
        auto_permission_request=True,
        auto_video_generation=False,
        auto_youtube_upload=False,
        genres=["lo-fi", "ambient", "indie"],
        release_window_days=90,
        min_freshness=0.4,
        max_artist_exposure=30,
    ))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("seeding:", seed_demo(force=True))