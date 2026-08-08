"""Audio ingestion + analysis tests (extension allowlist, analysis output shape)."""

from __future__ import annotations

import io
import math
import os
import struct
import tempfile
import wave
import uuid
from datetime import date


def _wav_bytes(seconds: float = 9.0) -> bytes:
    """A tiny valid WAV (440 Hz sine, 16-bit mono, 8000 Hz)."""
    buf = io.BytesIO()
    n = int(8000 * seconds)
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"".join(
            struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / 8000)))
            for i in range(n)
        ))
    return buf.getvalue()


def _mk_track(db, user):
    from app.models import Artist, Track

    art = Artist(name="Solo Test", spotify_artist_id=f"art-1-{uuid.uuid4().hex[:6]}")
    db.add(art)
    db.flush()
    t = Track(
        user_id=user.id, spotify_track_id=f"trk-a1-{uuid.uuid4().hex[:6]}", track_name="Tone Test",
        artist_name="Solo Test", release_date=date(2024, 4, 1), status="CANDIDATE",
        rights_status="UNKNOWN", artist_id=art.id,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def test_ingest_rejects_disallowed_extension(client, auth_headers, demo_user, db):
    track = _mk_track(db, demo_user)
    r = client.post(
        f"/api/tracks/{track.id}/audio",
        files={"file": ("evil.exe", b"MZ...", "application/octet-stream")},
        headers=auth_headers,
    )
    assert r.status_code == 422
    assert "unsupported file type" in r.json()["detail"].lower()


def test_ingest_accepts_wav_and_marks_source(client, auth_headers, demo_user, db):
    track = _mk_track(db, demo_user)
    r = client.post(
        f"/api/tracks/{track.id}/audio",
        files={"file": ("loop.wav", _wav_bytes(), "audio/wav")},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["rights_status"] in ("UNKNOWN", "PENDING")
    # audio source row created
    from app.models import AudioSource

    src = db.query(AudioSource).filter(AudioSource.track_id == track.id).first()
    assert src is not None
    assert src.file_path.endswith(".wav")


def test_analysis_output_shape_and_values():
    from app.services.audio.analysis import analyze_audio

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(_wav_bytes())
        path = f.name
    try:
        a = analyze_audio(path)
        assert a["duration_ms"] == 9000
        assert len(a["rms"]) > 0
        assert len(a["bass"]) == len(a["rms"]) == len(a["mid"]) == len(a["treble"])
        assert len(a["waveform"]) == 64
        assert 0.0 <= a["bpm"] <= 240.0
    finally:
        os.unlink(path)