"""All ORM models. Importing this package registers every table on
``Base.metadata`` so ``create_all`` / migrations see the full schema."""

from ..database import Base  # noqa: F401
from .user import User  # noqa: F401
from .audio import Artist, Track, AudioSource  # noqa: F401
from .licensing import License, Permission  # noqa: F401
from .video import Video, VideoTemplate  # noqa: F401
from .integration import (  # noqa: F401
    SpotifyAccount,
    YouTubeAccount,
    YouTubeUpload,
)
from .jobs import Job, Automation, Setting  # noqa: F401

__all__ = [
    "Base",
    "User",
    "Artist",
    "Track",
    "AudioSource",
    "License",
    "Permission",
    "Video",
    "VideoTemplate",
    "SpotifyAccount",
    "YouTubeAccount",
    "YouTubeUpload",
    "Job",
    "Automation",
    "Setting",
]