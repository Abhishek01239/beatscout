"""Rights / licensing tests — includes the legal business rule gate."""

from __future__ import annotations

from datetime import date

import uuid

import pytest

from app.services.rights import require_approved_rights


def _mk_track(db, user, rights_status="PENDING"):
    from app.models import Artist, Track

    artist = Artist(name="Test Artist", spotify_artist_id="art-1-%s" % uuid.uuid4().hex[:6])
    db.add(artist)
    db.flush()
    t = Track(
        user_id=user.id,
        spotify_track_id="trk-test-1-%s" % uuid.uuid4().hex[:6],
        track_name="Permission Test",
        artist_name="Test Artist",
        release_date=date(2024, 5, 1),
        status="CANDIDATE",
        rights_status=rights_status,
        discovery_score=70.0,
        artist_id=artist.id,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def test_video_requires_approved_rights(db, demo_user):
    track = _mk_track(db, demo_user, rights_status="PENDING")
    with pytest.raises(PermissionError):
        require_approved_rights(track)


def test_request_then_approve_permission(db, demo_user):
    from app.models import License
    from app.services.rights import approve_permission, request_permission

    track = _mk_track(db, demo_user, rights_status="PENDING")
    perm = request_permission(
        db, track, demo_user.id,
        artist="Test Artist", email="artist@example.com",
        message="Can we make a visualizer for your track?",
    )
    assert perm.status == "REQUESTED"
    assert track.rights_status == "REQUESTED"

    approve_permission(
        db, perm,
        permission_text="Artist replied: yes go ahead.",
        license_type="explicit_permission",
        commercial_use=True,
        youtube_use=True,
        modification_allowed=True,
        attribution_required=True,
        attribution_text="Track — Artist",
        proof_url="https://example.com/thread",
        expires_at=None,
    )
    db.refresh(track)
    assert track.rights_status == "APPROVED"
    lic = db.query(License).filter(License.track_id == track.id).first()
    assert lic is not None
    assert lic.youtube_use is True

    # gate is now open
    require_approved_rights(track)  # must not raise


def test_reject_permission_blocks_video(db, demo_user):
    from app.services.rights import reject_permission, request_permission

    track = _mk_track(db, demo_user, rights_status="PENDING")
    perm = request_permission(db, track, demo_user.id, artist="A", email="a@b.co",
                              message="granted for visualizer use")
    reject_permission(db, perm, reason="artist declined")
    db.refresh(track)
    assert track.rights_status == "REJECTED"
    with pytest.raises(PermissionError):
        require_approved_rights(track)


def test_verified_license_approves_track(db, demo_user):
    """License-based path: verify_license() must flip rights to APPROVED."""
    from app.models import License
    from app.services.rights import verify_license

    track = _mk_track(db, demo_user, rights_status="UNKNOWN")
    verify_license(
        db, track,
        audio_source="artist_direct",
        license_name="CC BY 4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        commercial_use=True,
        youtube_use=True,
        modification_allowed=True,
        attribution_required=True,
        attribution_text="Author (CC BY 4.0)",
        proof_url=None,
        expires_at=None,
        verified_by="demo@beatscout.dev",
    )
    db.refresh(track)
    assert track.rights_status == "APPROVED"
    assert db.query(License).filter(License.track_id == track.id).count() == 1


def test_approved_track_without_audio_reaches_render_stage(db, demo_user):
    """Gate open for APPROVED; missing audio must surface as ValueError,
    NOT PermissionError — proving the legal gate is not the blocker."""
    from app.services.video.service import render_for_track

    track = _mk_track(db, demo_user, rights_status="APPROVED")
    with pytest.raises(ValueError):
        render_for_track(db, track, as_preview=True)