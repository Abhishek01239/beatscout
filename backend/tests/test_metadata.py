"""Metadata generator tests: no false 'official' claims, disclosure line, attribution."""

from __future__ import annotations

from datetime import date, datetime

import uuid

import pytest


def _mk_track(db, user, license_name, commercial_use=True, youtube_use=True,
              attribution_required=False, attribution_text=None):
    from app.models import Artist, License, Track

    artist = Artist(name="Nova Wave", spotify_artist_id="art-nova-%s" % uuid.uuid4().hex[:6])
    db.add(artist)
    db.flush()
    t = Track(
        user_id=user.id,
        spotify_track_id="trk-meta-%s" % uuid.uuid4().hex[:6],
        track_name="Midnight Signal",
        artist_name="Nova Wave",
        release_date=date(2024, 6, 1),
        status="LICENSED",
        rights_status="APPROVED",
        artist_id=artist.id,
    )
    db.add(t)
    db.flush()
    lic = License(
        track_id=t.id,
        audio_source="artist_direct",
        license_name=license_name,
        commercial_use=commercial_use,
        youtube_use=youtube_use,
        attribution_required=attribution_required,
        attribution_text=attribution_text,
        verified_by=user.email,
        verified_at=datetime.utcnow(),
    )
    db.add(lic)
    db.commit()
    db.refresh(t)
    return t


def test_never_claims_official_for_standard_license(db, demo_user):
    from app.services.metadata import build_youtube_metadata

    track = _mk_track(db, demo_user, license_name="explicit_permission")
    meta = build_youtube_metadata(track, track.license)
    assert "official" not in meta["title"].lower()
    assert "Not an official release" in meta["description"]


def test_disclosure_present_when_license_row_is_none(db, demo_user):
    from app.services.metadata import build_youtube_metadata

    track = _mk_track(db, demo_user, license_name="explicit_permission")
    meta = build_youtube_metadata(track, None)
    # falls back to track.license when license_row is None
    assert "permission" in meta["description"].lower()


def test_attribution_required_is_honored(db, demo_user):
    from app.services.metadata import build_youtube_metadata

    track = _mk_track(
        db, demo_user, license_name="CC BY 4.0",
        attribution_required=True, attribution_text="Nova Wave (designated)",
    )
    meta = build_youtube_metadata(track, track.license)
    assert "Nova Wave" in meta["description"]
    assert meta["tags"], "expected non-empty tags"


def test_metadata_shape(db, demo_user):
    from app.services.metadata import build_youtube_metadata

    track = _mk_track(db, demo_user, license_name="CC BY 4.0")
    meta = build_youtube_metadata(track, track.license)
    assert {"title", "description", "tags", "category_id"} <= set(meta)
    assert isinstance(meta["tags"], list)
    assert len(meta["title"]) > 3