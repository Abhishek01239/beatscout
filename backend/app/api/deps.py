"""Shared FastAPI dependencies: DB session, current user, ownership."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Track, User
from ..security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)

# --------------------------------------------------------------------------
# Rate limiting (in-memory sliding window, per IP, per route)
# --------------------------------------------------------------------------

_rate_buckets: dict[str, list[float]] = {}


def rate_limit(request: Request, limit: int = 20, window_seconds: int = 60) -> None:
    """Simple in-memory rate limiter: `limit` requests per window per IP."""
    if not get_settings().RATE_LIMIT_ENABLED:
        return
    client_ip = request.client.host if request.client else "unknown"
    key = f"{request.url.path}:{client_ip}"
    now = _now()
    hits = [t for t in _rate_buckets.get(key, []) if now - t < window_seconds]
    if len(hits) >= limit:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Too many requests. Slow down.")
    hits.append(now)
    _rate_buckets[key] = hits


def _now() -> float:
    from time import time
    return time()


# ---------------------------------------------------------------------------
# Auth dependencies
# ---------------------------------------------------------------------------

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_access_token(credentials.credentials)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from None
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
    except PermissionError:
        return None
    return db.get(User, int(payload["sub"]))


def own_track(db: Session, track_id: int, user: User) -> Track:
    """Fetch a track and enforce that it belongs to `user`."""
    track = db.get(Track, track_id)
    if track is None or track.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Track not found")
    return track