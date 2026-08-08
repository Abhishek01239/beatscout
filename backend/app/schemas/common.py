"""Pydantic ORM-compatible base + shared response envelope.

All response schemas use ``from_attributes=True`` so SQLAlchemy models
serialize directly.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    detail: str
    code: str | None = None


class ProviderStatus(BaseModel):
    spotify: str  # "REAL" | "MOCK"
    youtube: str  # "REAL" | "MOCK"
    mode: str
    database: str  # configured drivername
    version: str