"""BeatScout — FastAPI application entrypoint.

Run locally:
    cd backend && uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import auth, automation, dashboard, jobs, rights, spotify, tracks, videos, youtube
from .config import get_settings
from .database import init_db, SessionLocal
from .services.jobs import LocalWorker

log = logging.getLogger("beatscout")

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL or "INFO"),
    format="[%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    worker: LocalWorker | None = None
    if settings.REDIS_URL:
        log.info("REDIS_URL set — celery worker expected; local worker disabled")
    else:
        # Local fallback worker: processes the QUEUED job table in-process
        if settings.AUTO_RUN_WORKER:
            worker = LocalWorker(poll_seconds=settings.WORKER_POLL_SECONDS)
            worker.start()
    if settings.SEED_DEMO:
        from .services.seed import seed_demo
        try:
            seed_demo()
        except Exception:
            log.exception("demo seeding failed (continuing)")
    yield
    if worker:
        worker.stop()


app = FastAPI(
    title="BeatScout API",
    version="1.0.0",
    description=(
        "Discover low-exposure independent music (Spotify metadata), verify "
        "reusable rights, generate beat-reactive visualizer videos and publish "
        "them to YouTube. Rights-gated: no video without APPROVED rights."
    ),
    lifespan=lifespan,
)

# --- CORS ------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- static media ----------------------------------------------------------
from fastapi.staticfiles import StaticFiles  # noqa: E402

media_mount = settings.storage_dir
media_mount.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(media_mount)), name="media")

# --- routers ---------------------------------------------------------------
app.include_router(auth.router, prefix="/api")
app.include_router(spotify.router, prefix="/api")
app.include_router(tracks.router, prefix="/api")
app.include_router(rights.router, prefix="/api")
app.include_router(videos.router, prefix="/api")
app.include_router(youtube.router, prefix="/api")
app.include_router(automation.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")


@app.get("/")
def root():
    return {
        "name": "BeatScout",
        "docs": "/docs",
        "provider_mode": "MOCK" if not settings.has_spotify_credentials else "REAL",
    }


@app.get("/health")
def health():
    return {"status": "ok", "provider_mode": get_provider_mode()}


def get_provider_mode() -> str:
    if settings.has_spotify_credentials:
        return "REAL"
    return "MOCK"


# --- error handlers --------------------------------------------------------
@app.exception_handler(PermissionError)
async def permission_error_handler(request: Request, exc: PermissionError):
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})