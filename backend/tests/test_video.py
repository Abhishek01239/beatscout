"""Video engine + service tests: template catalog, rights gate, tiny render."""

from __future__ import annotations

from datetime import date

import uuid

import pytest


def test_template_catalog_complete():
    from app.services.video.engine import RENDERERS, STYLE_DEFAULTS, TEMPLATES

    assert set(TEMPLATES) == {"minimal", "neon", "cinematic", "spectrum", "pulse"}
    assert set(RENDERERS) == set(TEMPLATES)
    assert set(STYLE_DEFAULTS) == set(TEMPLATES)


def test_render_preview_smoke(tmp_path, db, demo_user):
    """Render a real preview MP4 from a tiny synthesized WAV (slow but end-to-end)."""
    import numpy as np
    import wave

    from app.models import Artist, AudioSource, Track
    from app.services.video.service import render_for_track

    wav_path = tmp_path / "demo.wav"
    sr = 22050
    t = np.linspace(0, 4.0, int(sr * 4.0), endpoint=False)
    tone = 0.4 * np.sin(2 * np.pi * 220 * t) * (1 + 0.5 * np.sin(2 * np.pi * 2 * t))
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((tone * 32767).astype(np.int16).tobytes())

    art = Artist(name="Render Artist", spotify_artist_id="art-r-%s" % uuid.uuid4().hex[:6])
    db.add(art)
    db.flush()
    track = Track(
        user_id=demo_user.id, spotify_track_id="trk-render-%s" % uuid.uuid4().hex[:6], track_name="Render Test",
        artist_name="Render Artist", release_date=date(2024, 7, 1), status="LICENSED",
        rights_status="APPROVED", artist_id=art.id,
    )
    db.add(track)
    db.flush()
    db.add(AudioSource(
            track_id=track.id, original_filename="render-test.wav",
            file_path=str(wav_path), format="wav", size_bytes=wav_path.stat().st_size,
            checksum_sha512="x" * 128, duration_ms=4000,
        ))
    db.commit()
    db.refresh(track)

    video = render_for_track(db, track, style="minimal", as_preview=True)
    assert video.file_path.endswith(".mp4")
    assert video.template == "minimal"
    assert video.preview is True
    assert video.status == "completed"
    assert video.thumbnail_path and video.thumbnail_path.endswith(".jpg")


def test_render_requires_approved_rights(db, demo_user):
    from app.models import Artist, Track
    from app.services.video.service import render_for_track

    art = Artist(name="NoRights", spotify_artist_id="art-nr-%s" % uuid.uuid4().hex[:6])
    db.add(art)
    db.flush()
    track = Track(
        user_id=demo_user.id, spotify_track_id="trk-nr-%s" % uuid.uuid4().hex[:6], track_name="No Rights",
        artist_name="NoRights", release_date=date(2024, 7, 1), status="CANDIDATE",
        rights_status="PENDING", artist_id=art.id,
    )
    db.add(track)
    db.commit()
    db.refresh(track)
    with pytest.raises(PermissionError):
        render_for_track(db, track, as_preview=True)