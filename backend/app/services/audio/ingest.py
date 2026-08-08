"""Audio ingestion: multipart upload validation + secure local storage.

Stores original files under ``storage/audio/``.  Validates:
  - extension within allowlist (mp3, wav, flac, m4a)
  - size cap (MAX_UPLOAD_MB)
  - decodability + duration via ffmpeg
  - content hash (SHA-512) to prevent duplicates & tampering
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from ...config import get_settings
from ...models import AudioSource, Track

log = logging.getLogger("beatscout.ingest")

_ALLOWED = {"mp3", "wav", "flac", "m4a"}
_EXT_RE = re.compile(r"\.([a-zA-Z0-9]+)$")


class AudioValidationError(ValueError):
    pass


def validate_audio_upload(filename: str, size: int) -> None:
    """Raise AudioValidationError on any violation."""
    settings = get_settings()
    m = _EXT_RE.search(filename)
    if not m or m.group(1).lower() not in _ALLOWED:
        raise AudioValidationError(
            f"Unsupported file type {m.group(1) if m else '(none)'}. Allowed: mp3, wav, flac, m4a."
        )
    if size <= 0:
        raise AudioValidationError("Empty file.")
    if size > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise AudioValidationError(
            f"File too large (limit {settings.MAX_UPLOAD_MB} MB)."
        )


def store_audio(db: Session, track_id: int, filename: str, filedata: bytes) -> AudioSource:
    """Validate + persist an uploaded audio file, returning the AudioSource row."""
    validate_audio_upload(filename, len(filedata))
    settings = get_settings()
    ext = _EXT_RE.search(filename).group(1).lower()

    media_dir = settings.storage_dir / "media" / "audio"
    media_dir.mkdir(parents=True, exist_ok=True)
    dest = media_dir / f"{uuid.uuid4().hex[:12]}.{ext}"

    # decode validation BEFORE writing permanently
    tmp = media_dir / f".tmp_{uuid.uuid4().hex[:8]}.{ext}"
    tmp.write_bytes(filedata)
    from .ffmpeg_utils import probe_duration_ms
    duration = None
    try:
        duration = probe_duration_ms(str(tmp))
        if duration is None or duration < 8000:
            tmp.unlink(missing_ok=True)
            raise AudioValidationError("Audio too short or not decodable (min 8s).")
        if duration > 60 * 60 * 1000:
            tmp.unlink(missing_ok=True)
            raise AudioValidationError("Audio longer than 60 minutes is not supported.")
    except AudioValidationError:
        raise
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise AudioValidationError(f"Could not decode audio: {exc}") from exc

    tmp.rename(dest)
    checksum = hashlib.sha512(filedata).hexdigest()
    existing = db.query(AudioSource).filter(
        AudioSource.track_id == track_id, AudioSource.checksum_sha512 == checksum
    ).first()
    if existing:
        dest.unlink(missing_ok=True)
        log.info("duplicate audio upload (hash match) for track %s", track_id)
        return existing

    row = AudioSource(
        track_id=track_id,
        original_filename=filename[:200],
        file_path=str(dest),
        format=ext,
        size_bytes=len(filedata),
        duration_ms=duration,
        checksum_sha512=checksum,
        status="ready",
    )
    db.add(row)
    track = db.get(Track, track_id)
    if track:
        track.status = "LICENSED" if track.rights_status == "APPROVED" else "PERMISSION_REQUIRED"
    db.commit()
    db.refresh(row)
    log.info("audio stored for track %s: %s (%.1f MB)", track_id, filename, len(filedata) / 1e6)
    return row


def analyze_audio_source(db: Session, audio: AudioSource) -> dict:
    """Run analysis, persist nothing (caller stores), return JSON-safe dict."""
    from .analysis import analyze_audio
    result = analyze_audio(audio.file_path)
    audio.status = "analysed"
    db.commit()
    return result