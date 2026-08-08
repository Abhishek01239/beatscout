"""Rights, permission, license schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from .common import ORMModel


class LicenseOut(ORMModel):
    id: int
    track_id: int
    audio_source: str
    license_name: str | None = None
    license_url: str | None = None
    commercial_use: bool
    youtube_use: bool
    modification_allowed: bool
    attribution_required: bool
    attribution_text: str | None = None
    proof_url: str | None = None
    verified_at: datetime | None = None
    expires_at: datetime | None = None


class LicenseVerifyRequest(BaseModel):
    audio_source: str = Field(default="artist_upload", description="artist_upload|permission|creative_commons|public_domain|commercial_provider|other")
    license_name: str | None = None
    license_url: str | None = None
    commercial_use: bool = True
    youtube_use: bool = True
    modification_allowed: bool = True
    attribution_required: bool = False
    attribution_text: str | None = None
    proof_url: str | None = None
    expires_at: datetime | None = None
    verified_by: str | None = None


class PermissionOut(ORMModel):
    id: int
    track_id: int
    status: str
    artist: str
    email: str
    permission_text: str | None = None
    license_type: str | None = None
    commercial_use: bool
    youtube_use: bool
    modification_allowed: bool
    attribution_required: bool
    attribution_text: str | None = None
    approved_at: datetime | None = None
    expires_at: datetime | None = None
    proof_url: str | None = None
    created_at: datetime


class PermissionRequestCreate(BaseModel):
    artist: str | None = None
    email: EmailStr
    message: str | None = Field(default=None, max_length=4000)


class PermissionApprove(BaseModel):
    permission_text: str = Field(min_length=10, max_length=4000)
    license_type: str | None = "commercial_use"
    commercial_use: bool = True
    youtube_use: bool = True
    modification_allowed: bool = True
    attribution_required: bool = True
    attribution_text: str | None = None
    proof_url: str | None = None
    expires_at: datetime | None = None


class PermissionReject(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)