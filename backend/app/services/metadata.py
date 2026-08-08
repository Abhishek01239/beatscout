"""YouTube metadata generator.

Builds title/description/tags without ever claiming "official" release
status unless the track's license explicitly authorizes it.
"""

from __future__ import annotations

import logging
from datetime import date

from ..models import License, Track

log = logging.getLogger("beatscout.metadata")


def build_youtube_metadata(track: Track, license_row: License | None = None,
                           *, allow_official: bool = False) -> dict:
    """Return {title, description, tags, attribution, disclaimers}."""

    title = f"{track.artist_name} — {track.track_name} | Visualizer"
    if allow_official:
        title = f"{track.artist_name} — {track.track_name} | Official Visualizer"

    if license_row is None:
        license_row = track.license

    # --- description -------------------------------------------------------
    lines: list[str] = []
    lines.append(f"Track: {track.track_name}")
    lines.append(f"Artist: {track.artist_name}")
    if track.album_name:
        lines.append(f"Album: {track.album_name}")
    if track.release_date:
        lines.append(f"Released: {track.release_date.isoformat()}")
    if track.genre:
        lines.append(f"Genre: {track.genre}")
    lines.append("")

    if license_row:
        src = {
            "artist_upload": "Artist-provided audio",
            "permission": "Direct artist permission",
            "creative_commons": "Creative Commons license",
            "public_domain": "Public domain audio",
            "commercial_provider": "Licensed via a commercial music provider",
            "other": "License-compatible source",
        }.get(license_row.audio_source, license_row.audio_source)
        lines.append(f"Music source: {src}")
        if license_row.license_name:
            lines.append(f"License: {license_row.license_name}")
        if license_row.license_url:
            lines.append(f"License details: {license_row.license_url}")
        lines.append(f"Permission: {'Confirmed' if license_row.youtube_use else 'Limited'}")

    attribution = license_row.attribution_text if (license_row and license_row.attribution_required) else None
    if attribution:
        lines.append("")
        lines.append(f"Music by {attribution}.")
    lines.append("")
    lines.append("This is a fan-made beat visualizer. Support the artist by following them on Spotify.")
    if track.spotify_url:
        lines.append(f"Listen on Spotify: {track.spotify_url}")

    description = "\n".join(lines)

    tags = [
        track.artist_name, track.track_name, "visualizer", "beat visualizer",
        "music video", "new music",
    ]
    if track.genre:
        tags.append(track.genre)
        tags.append(f"{track.genre} music")
    if track.exposure_label:
        tags.append("emerging artist" if track.exposure_label == "emerging" else "independent artist")
    tags = dedupe_tags(tags)

    disclaimers = []
    if not allow_official:
        disclaimers.append("Not an official release — visualizer made with the track owner's permission.")
    if license_row and license_row.attribution_required:
        disclaimers.append("Attribution required — included in the description.")
    if disclaimers:
        description = description + "\n\n" + "\n".join(disclaimers)

    return {
        "title": title,
        "description": description,
        "tags": tags,
        "attribution": attribution,
        "disclaimers": disclaimers,
        "category_id": "10",   # YouTube Music category
    }


def dedupe_tags(tags: list[str], max_tags: int = 20) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        t = t.strip()
        if not t or t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append(t)
    return out[:max_tags]