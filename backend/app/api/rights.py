"""Rights endpoints: permission workflow + license verification + audio upload."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Permission, Track, User
from ..schemas.rights import (
    LicenseOut, LicenseVerifyRequest, PermissionApprove, PermissionOut,
    PermissionReject, PermissionRequestCreate,
)
from ..schemas.spotify import TrackOut
from ..services import rights as rights_svc
from ..services.audio.ingest import AudioValidationError, store_audio
from .deps import get_current_user, own_track

log = logging.getLogger("beatscout.api.rights")
router = APIRouter(tags=["rights"])


# -- permission workflow ---------------------------------------------------

@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(status: str | None = None, db: Session = Depends(get_db),
                     current: User = Depends(get_current_user)):
    q = db.query(Permission).filter(Permission.user_id == current.id)
    if status:
        q = q.filter(Permission.status == status)
    return q.order_by(Permission.created_at.desc()).limit(200).all()


@router.post("/tracks/{track_id}/permission", response_model=PermissionOut, status_code=201)
def request_permission(track_id: int, body: PermissionRequestCreate,
                       db: Session = Depends(get_db),
                       current: User = Depends(get_current_user)):
    """Create a permission request sent to the artist/license owner."""
    track = own_track(db, track_id, current)
    perm = rights_svc.request_permission(db, track, current.id,
                                         artist=body.artist, email=body.email,
                                         message=body.message)
    return perm


@router.post("/permissions/{permission_id}/approve", response_model=PermissionOut)
def approve_permission(permission_id: int, body: PermissionApprove,
                       db: Session = Depends(get_db),
                       current: User = Depends(get_current_user)):
    perm = db.get(Permission, permission_id)
    if perm is None or perm.user_id != current.id:
        raise HTTPException(404, "Permission not found")
    return rights_svc.approve_permission(
        db, perm,
        permission_text=body.permission_text, license_type=body.license_type,
        commercial_use=body.commercial_use, youtube_use=body.youtube_use,
        modification_allowed=body.modification_allowed,
        attribution_required=body.attribution_required,
        attribution_text=body.attribution_text, proof_url=body.proof_url,
        expires_at=body.expires_at,
    )


@router.post("/permissions/{permission_id}/reject", response_model=PermissionOut)
def reject_permission(permission_id: int, body: PermissionReject,
                      db: Session = Depends(get_db),
                      current: User = Depends(get_current_user)):
    perm = db.get(Permission, permission_id)
    if perm is None or perm.user_id != current.id:
        raise HTTPException(404, "Permission not found")
    return rights_svc.reject_permission(db, perm, body.reason)


# -- license ---------------------------------------------------------------

@router.post("/tracks/{track_id}/license/verify", response_model=LicenseOut)
def verify_license(track_id: int, body: LicenseVerifyRequest,
                   db: Session = Depends(get_db),
                   current: User = Depends(get_current_user)):
    """Operator marks a compatible license as verified (CC / public domain / …)."""
    track = own_track(db, track_id, current)
    try:
        license_row = rights_svc.verify_license(
            db, track,
            audio_source=body.audio_source, license_name=body.license_name,
            license_url=body.license_url, commercial_use=body.commercial_use,
            youtube_use=body.youtube_use, modification_allowed=body.modification_allowed,
            attribution_required=body.attribution_required,
            attribution_text=body.attribution_text, proof_url=body.proof_url,
            expires_at=body.expires_at, verified_by=body.verified_by or current.email,
        )
    except PermissionError as exc:
        raise HTTPException(422, str(exc))
    return license_row


# -- audio upload ----------------------------------------------------------

@router.post("/tracks/{track_id}/audio", response_model=TrackOut)
async def upload_audio(track_id: int, file: UploadFile = File(...),
                       db: Session = Depends(get_db),
                       current: User = Depends(get_current_user)):
    """Upload a *legally obtained* audio file for the track (mp3/wav/flac/m4a)."""
    track = own_track(db, track_id, current)
    data = await file.read()
    try:
        store_audio(db, track.id, file.filename or "upload.bin", data)
    except AudioValidationError as exc:
        raise HTTPException(422, str(exc))
    db.refresh(track)
    return track