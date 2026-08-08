"""Video generation schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .common import ORMModel


class VideoOut(ORMModel):
    id: int
    track_id: int
    template: str
    status: str
    progress: float
    file_path: str | None = None
    thumbnail_path: str | None = None
    width: int
    height: int
    fps: int
    duration_ms: int | None = None
    settings: dict
    error: str | None = None
    preview: bool
    created_at: datetime
    completed_at: datetime | None = None


class VideoRenderRequest(BaseModel):
    track_id: int
    template: str = Field(default="minimal", description="minimal|neon|cinematic|spectrum|pulse")
    preview: bool = Field(default=False, description="render a short low-res preview")
    settings: dict = Field(default_factory=dict)
    fps: int = Field(default=30, ge=12, le=60)


class VideoSettings(BaseModel):
    background: str = "dark"              # dark | midnight | ocean | ember | forest
    artwork_position: str = "center"      # center | left | right | bottom
    text_position: str = "bottom"         # bottom | top | center
    font_size: int = Field(default=42, ge=16, le=120)
    waveform_type: str = "bars"           # bars | mirror | line
    particle_amount: int = Field(default=60, ge=0, le=400)
    animation_intensity: float = Field(default=1.0, ge=0.0, le=3.0)


class VideoPreviewRequest(BaseModel):
    track_id: int
    template: str = "minimal"
    settings: dict = Field(default_factory=dict)


class TemplateList(ORMModel):
    id: int
    name: str
    label: str
    description: str | None = None
    defaults: dict