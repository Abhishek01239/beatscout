"""BeatScout application configuration.

All settings come from environment variables / a root `.env` file
(pydantic-settings).  Secrets are never exposed through the API —
only provider *modes* (REAL/MOCK) and redacted status booleans are.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root = two levels above this file (backend/app/config.py)
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env", Path.cwd() / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Core
    APP_NAME: str = "BeatScout"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = "dev-insecure-secret-change-me-please-32-bytes-min"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720

    # Database (sqlite fallback for local dev)
    DATABASE_URL: str = "sqlite:///./beatscout.db"

    # Spotify Web API
    SPOTIFY_CLIENT_ID: str = ""
    SPOTIFY_CLIENT_SECRET: str = ""
    SPOTIFY_REDIRECT_URI: str = "http://localhost:5173/settings"

    # YouTube Data API v3
    YOUTUBE_CLIENT_ID: str = ""
    YOUTUBE_CLIENT_SECRET: str = ""
    YOUTUBE_REDIRECT_URI: str = "http://localhost:5173/settings/youtube"
    YOUTUBE_REFRESH_TOKEN: str = ""   # headless (CI) uploads: obtained once via scripts/yt_token.py

    # Redis / Celery (empty -> in-process fallback worker)
    REDIS_URL: str = ""

    # Object storage (empty -> local filesystem storage/)
    STORAGE_BUCKET: str = ""
    STORAGE_ENDPOINT: str = ""
    STORAGE_ACCESS_KEY: str = ""
    STORAGE_SECRET_KEY: str = ""
    STORAGE_REGION: str = ""

    # Video
    FFMPEG_BIN: str = ""
    VIDEO_WIDTH: int = 1920
    VIDEO_HEIGHT: int = 1080
    VIDEO_FPS: int = 30
    PREVIEW_WIDTH: int = 640
    PREVIEW_HEIGHT: int = 360

    # Uploads
    MAX_UPLOAD_MB: int = 200
    ALLOWED_AUDIO_TYPES: str = "mp3,wav,flac,m4a"

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Runtime
    SEED_DEMO: int = 1
    RATE_LIMIT_ENABLED: int = 1
    AUTO_RUN_WORKER: int = 1        # in-process job worker when REDIS_URL is empty
    WORKER_POLL_SECONDS: int = 2

    # Autonomous daily pipeline (app/auto.py, GitHub Actions)
    JAMENDO_CLIENT_ID: str = ""     # free Jamendo API client id (CC music source)
    AUTO_DRY_RUN: int = 1           # 1 = log uploads, 0 = actually post to YouTube

    # ---------- derived helpers ----------

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_audio_types(self) -> list[str]:
        return [t.strip().lower() for t in self.ALLOWED_AUDIO_TYPES.split(",") if t.strip()]

    @property
    def has_spotify_credentials(self) -> bool:
        return bool(self.SPOTIFY_CLIENT_ID and self.SPOTIFY_CLIENT_SECRET)

    @property
    def has_youtube_credentials(self) -> bool:
        return bool(self.YOUTUBE_CLIENT_ID and self.YOUTUBE_CLIENT_SECRET)

    @property
    def provider_mode(self) -> str:
        """'hybrid' when any real credentials exist, else 'mock'."""
        if self.has_spotify_credentials or self.has_youtube_credentials:
            return "hybrid"
        return "mock"

    @property
    def storage_dir(self) -> Path:
        d = BASE_DIR / "storage"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def database_path(self) -> str:
        return self.DATABASE_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()