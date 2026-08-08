"""Licensing & rights service — the legal gate for the whole pipeline.

BUSINESS RULE (non-negotiable):

    if track.rights_status != "APPROVED":
        raise PermissionError(
            "This track cannot be processed because usage rights "
            "have not been verified."
        )

A track reaches APPROVED only through one of:
  1. an explicit approval record (:class:`Permission` status APPROVED)
  2. a verified, clearly compatible license (:class:`License` that allows
     commercial/YouTube use) — Creative Commons, public domain,
     artist-provided audio with permission, or another provider that
     explicitly permits the use.

Discovering a song on Spotify with low streams NEVER authorizes use.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import License, Permission, Track

log = logging.getLogger("beatscout.rights")

APPROVED = "APPROVED"
PERMISSION_STATUSES = ("UNKNOWN", "REQUESTED", "PENDING", "APPROVED", "REJECTED", "EXPIRED")

BUSINESS_RULE_MESSAGE = (
    "This track cannot be processed because usage rights have not been verified. "
    "Add a licensed audio file and confirm permission first."
)


def require_approved_rights(track: Track) -> None:
    """Raise `PermissionError` unless usage rights are verified. Central rule."""
    if track.rights_status != APPROVED:
        raise PermissionError(BUSINESS_RULE_MESSAGE)


def request_permission(db: Session, track: Track, user_id: int, *, artist: str | None,
                       email: str, message: str | None) -> Permission:
    """Create a REQUESTED permission record for the artist/license owner."""
    perm = Permission(
        track_id=track.id,
        user_id=user_id,
        artist=artist or track.artist_name,
        email=email,
        permission_text=message or "",
        status="REQUESTED",
    )
    db.add(perm)
    track.rights_status = "REQUESTED"
    track.status = "PERMISSION_REQUIRED"
    db.commit()
    db.refresh(perm)
    log.info("permission requested for track %s via %s", track.id, email)
    return perm


def approve_permission(db: Session, perm: Permission, *, permission_text: str,
                       license_type: str | None, commercial_use: bool, youtube_use: bool,
                       modification_allowed: bool, attribution_required: bool,
                       attribution_text: str | None, proof_url: str | None,
                       expires_at: datetime | None) -> Permission:
    """Operator records the artist's approval (email/screenshot/URL as proof)."""
    perm.status = "APPROVED"
    perm.permission_text = permission_text
    perm.license_type = license_type
    perm.commercial_use = commercial_use
    perm.youtube_use = youtube_use
    perm.modification_allowed = modification_allowed
    perm.attribution_required = attribution_required
    perm.attribution_text = attribution_text or (
        f"{perm.artist} — {db.get(Track, perm.track_id).track_name}"
        if db.get(Track, perm.track_id) else perm.artist
    )
    perm.proof_url = proof_url
    perm.approved_at = datetime.utcnow()
    perm.expires_at = expires_at

    # Mirror onto the track-level license for the render gate
    track = db.get(Track, perm.track_id)
    _upsert_track_license(db, track, perm=perm)
    track.rights_status = APPROVED
    track.status = "LICENSED"
    db.commit()
    return perm


def reject_permission(db: Session, perm: Permission, reason: str | None) -> Permission:
    perm.status = "REJECTED"
    if reason:
        perm.permission_text = (perm.permission_text or "") + f"\nRejected: {reason}"
    track = db.get(Track, perm.track_id)
    track.rights_status = "REJECTED"
    track.status = "PERMISSION_REQUIRED"
    db.commit()
    return perm


def verify_license(db: Session, track: Track, *, audio_source: str, license_name: str | None,
                   license_url: str | None, commercial_use: bool, youtube_use: bool,
                   modification_allowed: bool, attribution_required: bool,
                   attribution_text: str | None, proof_url: str | None,
                   expires_at: datetime | None, verified_by: str | None) -> License:
    """Operator manually verifies a compatible license for the track."""
    license_row = License(
        track_id=track.id,
        audio_source=audio_source,
        license_name=license_name,
        license_url=license_url,
        commercial_use=commercial_use,
        youtube_use=youtube_use,
        modification_allowed=modification_allowed,
        attribution_required=attribution_required,
        attribution_text=attribution_text,
        proof_url=proof_url,
        expires_at=expires_at,
        verified_by=verified_by,
        verified_at=datetime.utcnow(),
    )
    db.add(license_row)

    if not compatible(license_row):
        track.rights_status = "REJECTED"
        track.status = "PERMISSION_REQUIRED"
        db.commit()
        raise PermissionError(
            "License does not permit YouTube/commercial use. "
            "Track cannot become APPROVED."
        )

    track.rights_status = APPROVED
    track.status = "LICENSED"
    db.commit()
    db.refresh(license_row)
    log.info("license verified for track %s: %s", track.id, license_name)
    return license_row


def compatible(license_row: License) -> bool:
    """A license is compatible when it allows YouTube use (+commercial)."""
    if license_row.expires_at and license_row.expires_at < datetime.utcnow():
        return False
    return bool(license_row.youtube_use)


def _upsert_track_license(db: Session, track: Track, perm: Permission | None = None) -> None:
    existing = track.license
    row = existing or License(track_id=track.id)
    if perm:
        row.audio_source = "permission"
        row.license_name = perm.license_type or "artist permission"
        row.commercial_use = perm.commercial_use
        row.youtube_use = perm.youtube_use
        row.modification_allowed = perm.modification_allowed
        row.attribution_required = perm.attribution_required
        row.attribution_text = perm.attribution_text
        row.proof_url = perm.proof_url
        row.verified_by = perm.email
        row.verified_at = perm.approved_at
        row.expires_at = perm.expires_at
    if row.track_id is None:
        row.track_id = track.id
    db.add(row)
    db.flush()