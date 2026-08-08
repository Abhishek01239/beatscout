"""Mock Spotify provider.

Serves a rich, deterministic catalog of fictional low-exposure artists so
the whole product (discovery → rights → render → publish) can be explored
and tested with zero credentials.  Everything marked MOCK.

All entries are fictional.  Popularity is a *signal* (0-100) and is
displayed as "Low exposure / Emerging artist" — never as an exact
stream count.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from .base import SpotifyProviderBase, SpotifyTrackMeta

_ART = [
    # (artist, genre, country, pop_signal, followers_signal)
    ("KAZUMA", "lo-fi", "JP", 14, 812),
    ("Orchid Motel", "ambient", "US", 9, 340),
    ("neubau", "electronic", "DE", 21, 1400),
    ("Mira Voss", "pop", "SE", 32, 5200),
    ("The Paper Lanterns", "indie", "GB", 11, 480),
    ("DCLXVI", "hip-hop", "US", 27, 3100),
    ("Fernando Luz", "experimental", "BR", 7, 95),
    ("Sekai Yoru", "lo-fi", "JP", 15, 990),
    ("Verdant", "ambient", "CA", 6, 64),
    ("Nova Pulse", "edm", "US", 33, 4200),
    ("Ash & Ember", "rock", "GB", 18, 1500),
    ("kindred", "indie", "AU", 12, 730),
    ("Østerby", "electronic", "DK", 8, 210),
    ("Lumen Kids", "pop", "NL", 5, 42),
    ("Basalt", "hip-hop", "IN", 21, 1870),
    ("Driftbreaker", "ambient", "IS", 4, 31),
    ("Roy Greens", "indie", "US", 29, 2650),
    ("Pulso Uno", "edm", "MX", 17, 1100),
    ("Cassette Fortunes", "lo-fi", "US", 24, 2400),
    ("Ojalá", "experimental", "ES", 3, 18),
    ("Night Harbor", "ambient", "NO", 10, 410),
    ("Void Choir", "electronic", "PL", 12, 620),
    ("Meadowweave", "folk", "US", 8, 190),
    ("Aerolith", "rock", "CA", 2, 27),
]

_TRACKS = [
    ("velvet horizon", "glass tides", 180000),
    ("midnight slow dance", "neon reverie", 214000),
    ("paper moons", "the last bus home", 197000),
    ("static garden", "temporary seasons", 233000),
    ("count the stars", "sleepless epigraph", 168000),
    ("ember light", "small fires", 251000),
    ("cobalt", "fracture", 220000),
    ("moonwater", "tidal sites", 245000),
    ("low tide serenade", "harbour songs", 205000),
    ("numb at dusk", "dusk archives", 192000),
    ("feral bloom", "wild taxonomy", 227000),
    ("i-80", "night highway", 199000),
    ("salt city", "coastal static", 238000),
    ("gravitational", "orbits", 264000),
    ("slow satellite", "relay", 178000),
    ("monotown", "spectrum", 216000),
    ("quiet riot", "contrast", 190000),
    ("seabed", "deep current", 301000),
    ("amber outline", "light studies", 156000),
    ("after the flood", "watermark", 285000),
    ("snowblind", "day zero", 208000),
    ("lantern v", "signals", 224000),
    ("undone map", "wander", 246000),
    ("tremor", "shake & settle", 187000),
]


def _build_catalog() -> list[SpotifyTrackMeta]:
    rng = random.Random(42)
    catalog: list[SpotifyTrackMeta] = []
    today = date.today()
    for idx, ((artist, genre, country, pop, followers), (track, album, dur)) in enumerate(
        zip(_ART, _TRACKS)
    ):
        days_ago = rng.choice([1, 3, 6, 9, 14, 22, 31, 45, 71, 110, 200, 340])
        if idx % 5 == 0:
            days_ago = rng.choice([1, 2, 4, 8])   # a few very fresh drops
        artist_pop = max(1, pop - rng.randint(0, 6))
        catalog.append(
            SpotifyTrackMeta(
                spotify_track_id=f"mock{idx:07d}",
                spotify_artist_id=f"mockartist{idx:05d}",
                track_name=track,
                artist_name=artist,
                album_name=album,
                release_date=today - timedelta(days=days_ago),
                spotify_url=f"https://open.spotify.com/track/mock{idx:07d}",
                album_art_url=f"mock://art/{idx}",  # rendered locally by the artwork service
                duration_ms=dur * 1000,
                popularity_signal=pop,
                artist_popularity_signal=artist_pop,
                artist_followers_signal=followers,
                genres=[genre],
                country=country,
                external_ids={"isrc": f"MOCK{idx:03d}"},
                isrc=f"US{country}{idx:05d}",
            )
        )
    return catalog


class MockSpotifyProvider(SpotifyProviderBase):
    """Deterministic offline provider — no network, no credentials."""

    name = "MOCK"

    def __init__(self) -> None:
        self.catalog = _build_catalog()

    def search(self, query: str, limit: int = 20) -> list[SpotifyTrackMeta]:
        q = query.lower()
        results = [
            t for t in self.catalog
            if q in t.track_name.lower() or q in t.artist_name.lower()
            or q in " ".join(t.genres).lower()
        ]
        return results[:limit]

    def discover(self, *, genres, release_from: date, release_to: date,
                  limit: int = 30, country: str | None = None) -> list[SpotifyTrackMeta]:
        results = []
        for t in self.catalog:
            if genres and not (set(t.genres) & set(genres)):
                continue
            if t.release_date is None:
                continue
            if not (release_from <= t.release_date <= release_to):
                continue
            if country and t.country != country:
                continue
            results.append(t)
        # Deterministic "freshness-biased" shuffle so the newest drops float up
        results.sort(key=lambda t: (t.release_date or date.min), reverse=True)
        return results[:limit]

    def get_track(self, spotify_track_id: str) -> SpotifyTrackMeta | None:
        return next((t for t in self.catalog if t.spotify_track_id == spotify_track_id), None)