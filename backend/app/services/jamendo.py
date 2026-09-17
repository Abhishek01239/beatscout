"""Jamendo discovery provider — free CC-licensed music for *real* publication.

Jamendo exposes its catalog through an open API. Every track carries an
explicit Creative-Commons license, which is exactly what the autonomous
pipeline needs: we can legally obtain publication rights for a track
source without waiting on a human reply.
"""

from __future__ import annotations

import logging
from datetime import date

import httpx

from ..config import get_settings
from .spotify.base import SpotifyTrackMeta

log = logging.getLogger("beatscout.discovery.jamendo")

API_BASE = "https://api.jamendo.com/v3.0/tracks/"

# Licenses that allow commercial use + derivative works (our visualizers).
ALLOWED_LICENSES = {"by", "by-sa", "zero", "cc0", "cc"}

TAG_ALIASES = {
    "lo-fi": ["lofi", "chillout", "chill", "downtempo"],
    "lofi": ["lofi", "chillout", "chill", "downtempo"],
    "ambient": ["ambient", "chillout", "atmospheric"],
    "electronic": ["electronic", "electronica", "dance"],
}


def license_allows(license_name: str) -> bool:
    """Return True only for CC licenses permitting commercial derivatives."""
    raw = (license_name or "").strip().lower()
    if not raw:
        return False
    if "/" in raw:
        code = license_code_from_url(raw)
        if code:
            return code in ALLOWED_LICENSES
    normalized = (
        raw.replace("creative commons", "")
           .replace("creativecommons", "")
           .replace("attribution-sharealike", "by-sa")
           .replace("attribution-noncommercial-sharealike", "by-nc-sa")
           .replace("attribution-noncommercial-noderivatives", "by-nc-nd")
           .replace("attribution-noderivatives", "by-nd")
           .replace("attribution-noncommercial", "by-nc")
           .replace("attribution", "by")
           .replace("sharealike", "sa")
           .replace("noderivatives", "nd")
           .replace("noncommercial", "nc")
           .replace(" ", "-")
           .replace("_", "-")
    )
    return bool(_first_code(normalized))


def _first_code(code: str) -> str:
    for part in code.split(";"):
        tokens = [t for t in part.replace(".", "-").split("-") if t]
        if not tokens:
            continue
        base = tokens[0]
        if base in ALLOWED_LICENSES and not ({"nc", "nd"} & set(tokens)):
            return base
    return ""


def license_code_from_url(ccurl: str) -> str:
    url = (ccurl or "").rstrip("/")
    if not url:
        return ""
    for frag in reversed(url.lower().split("/")):
        if frag in ALLOWED_LICENSES:
            return frag
    return ""


def track_from_item(item: dict) -> SpotifyTrackMeta:
    jam_id = str(item.get("id", ""))
    tags = item.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    license_url = item.get("license_ccurl") or ""
    license_name = license_code_from_url(license_url) or item.get("license_ccname") or "unknown"
    release = item.get("releasedate")
    rdate = None
    if release:
        try:
            rdate = date.fromisoformat(release[:10])
        except ValueError:
            rdate = None
    return SpotifyTrackMeta(
        spotify_track_id="jamendo:" + jam_id,
        spotify_artist_id="jamendo-art:" + str(item.get("artist_id") or jam_id),
        track_name=item.get("name") or "Untitled",
        artist_name=item.get("artist_name") or "Unknown Artist",
        album_name=item.get("album_name"),
        release_date=rdate,
        spotify_url=item.get("shareurl") or item.get("page") or "",
        album_art_url=item.get("image") or item.get("album_image") or "",
        duration_ms=int(float(item.get("duration", 0)) * 1000) if item.get("duration") else None,
        popularity_signal=int(item.get("popularity", 0) or 0),
        genres=tags,
        external_ids={
            "jamendo_id": jam_id,
            "audio_url": item.get("audio") or item.get("audiodownload") or "",
            "license_url": license_url,
            "license_name": license_name,
            "album_id": str(item.get("album_id", "")),
        },
    )


class JamendoProvider:
    """Real discovery provider: free CC-licensed tracks via the Jamendo API."""

    name = "JAMENDO"

    def __init__(self, client_id: str | None = None) -> None:
        settings = get_settings()
        self.client_id = client_id or settings.JAMENDO_CLIENT_ID
        if not self.client_id:
            raise ValueError("JAMENDO_CLIENT_ID is required for Jamendo discovery.")
        self._http = httpx.Client(timeout=30.0, follow_redirects=True)

    def _tags_for_genre(self, genre: str) -> list[str]:
        key = (genre or "").strip().lower()
        return TAG_ALIASES.get(key, [genre.strip()] if genre.strip() else [])

    def discover(self, *, genres: list[str], release_from: date,
                 release_to: date, limit: int = 30,
                 country: str | None = None) -> list[SpotifyTrackMeta]:
        """Discover enough valid tracks by trying aliases and API pages.

        Jamendo documents ``ccnc``/``ccnd`` as license filters, but in
        production responses those filters can produce an empty catalog for
        otherwise valid searches. We therefore query the normal catalog and
        enforce the commercial/derivative license requirement locally using
        the returned license_ccurl. This keeps discovery observable and makes
        the rights gate deterministic.
        """
        if limit <= 0:
            return []

        base = {
            "client_id": self.client_id,
            "format": "json",
            "include": "licenses,musicinfo",
            "audioformat": "mp32",
            "audiodlformat": "mp32",
            "order": "relevance",
            "boost": "popularity_week",
        }
        page_size = min(max(limit * 2, 50), 200)
        max_pages_per_tag = 5
        out: list[SpotifyTrackMeta] = []
        seen: set[str] = set()
        tags: list[str] = []
        for genre in genres or ["electronic", "ambient"]:
            for tag in self._tags_for_genre(genre):
                if tag and tag not in tags:
                    tags.append(tag)
        for tag in ["electronic", "ambient", "chillout", "instrumental"]:
            if tag not in tags:
                tags.append(tag)

        rejected_license = 0
        rejected_audio = 0
        empty_pages = 0
        api_failures = 0
        for tag in tags:
            if len(out) >= limit:
                break
            for page in range(max_pages_per_tag):
                offset = page * page_size
                params = dict(base, fuzzytags=tag, limit=str(page_size), offset=str(offset))
                try:
                    resp = self._http.get(API_BASE, params=params)
                    resp.raise_for_status()
                    payload = resp.json()
                except (httpx.HTTPError, ValueError) as exc:
                    log.warning("Jamendo query failed tag=%s page=%s: %s", tag, page + 1, exc)
                    break

                headers = payload.get("headers") or {}
                api_status = headers.get("status")
                api_code = headers.get("code")
                api_error = headers.get("error_message") or headers.get("error") or ""
                if api_status != "success":
                    api_failures += 1
                    log.warning(
                        "Jamendo API rejected query tag=%s page=%s status=%s code=%s error=%s",
                        tag, page + 1, api_status or "unknown", api_code if api_code is not None else "unknown",
                        api_error or "<no error message>",
                    )
                    # An authentication/client-id error will repeat for every tag;
                    # stop immediately instead of hammering the API.
                    if api_code not in (None, 0, "0"):
                        break
                    continue

                items = payload.get("results") or []
                if not items:
                    empty_pages += 1
                    log.info(
                        "Jamendo query tag=%s page=%s returned 0 results (api_status=%s code=%s)",
                        tag, page + 1, api_status, api_code,
                    )
                    break

                for item in items:
                    if len(out) >= limit:
                        break
                    license_url = item.get("license_ccurl") or ""
                    license_name = license_code_from_url(license_url) or item.get("license_ccname") or ""
                    if not license_allows(license_name):
                        rejected_license += 1
                        continue
                    # `audio` is the stream URL; `audiodownload` is optional
                    # and can be empty when the artist disables downloads.
                    audio_url = item.get("audiodownload") or item.get("audio") or ""
                    if not audio_url:
                        rejected_audio += 1
                        continue
                    item = dict(item)
                    item["audio"] = audio_url
                    meta = track_from_item(item)
                    if meta.spotify_track_id in seen:
                        continue
                    seen.add(meta.spotify_track_id)
                    out.append(meta)
                if len(items) < page_size:
                    break

        log.info(
            "Jamendo discovery: %d valid candidates from %d tags "
            "(rejected_license=%d rejected_audio=%d empty_pages=%d api_failures=%d)",
            len(out), len(tags), rejected_license, rejected_audio, empty_pages, api_failures,
        )
        return out

    def search(self, query: str, limit: int = 20) -> list[SpotifyTrackMeta]:
        return self.discover(genres=[query], release_from=date(2000, 1, 1),
                             release_to=date.today(), limit=limit)

    def get_track(self, spotify_track_id: str) -> SpotifyTrackMeta | None:
        jam_id = spotify_track_id.removeprefix("jamendo:")
        resp = self._http.get(API_BASE, params={
            "client_id": self.client_id, "format": "json", "id": jam_id,
            "include": "licenses,musicinfo",
        })
        if resp.status_code != 200:
            return None
        payload = resp.json()
        headers = payload.get("headers") or {}
        if headers.get("status") != "success":
            log.warning(
                "Jamendo get_track rejected id=%s status=%s code=%s error=%s",
                jam_id, headers.get("status") or "unknown",
                headers.get("code") if headers.get("code") is not None else "unknown",
                headers.get("error_message") or headers.get("error") or "<no error message>",
            )
            return None
        items = payload.get("results") or []
        return track_from_item(items[0]) if items else None

    def rate_limit_message(self) -> str:
        return "Jamendo API rate limit exceeded. Retry later."

    def close(self) -> None:
        self._http.close()
