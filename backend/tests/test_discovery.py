"""Spotify discovery tests: mock provider, factory fallback, discovery pipeline."""

from __future__ import annotations

import datetime
import uuid


def test_mock_provider_returns_metadata():
    from app.services.spotify.mock import MockSpotifyProvider

    p = MockSpotifyProvider()
    tracks = p.search("lo-fi", limit=5)
    assert 0 < len(tracks) <= 5
    for t in tracks:
        # metadata-only surface, never audio
        assert isinstance(t.spotify_track_id, str)
        assert 0 <= t.popularity_signal <= 100
        assert t.release_date
        assert "lo-fi" in t.genres
        assert isinstance(t.release_date, datetime.date)
    assert MockSpotifyProvider.name == "MOCK"


def test_provider_factory_defaults_to_mock():
    # creds absent in tests => factory must return the mock provider
    from app.services.spotify import get_spotify_provider

    p = get_spotify_provider()
    assert p.name == "MOCK"


def test_discovery_persists_tracks(db, demo_user):
    from app.models import Track, User
    from app.services.discovery import DiscoveryConfig, discover_and_persist
    from app.security import hash_password

    # a fresh user => no spotify-track_id collisions and no orphan FK rows
    db.add(User(email=f"disc-{uuid.uuid4().hex[:8]}@beatscout.dev",
                password_hash=hash_password("pass"), name="Discovery"))
    db.commit()
    uid = db.query(User).order_by(User.id.desc()).first().id

    out = discover_and_persist(
        db, uid,
        DiscoveryConfig(max_tracks=8, release_window_days=500, min_freshness=0),
    )
    assert out["discovered"] >= 1
    assert 0 < out["new_tracks"] <= out["discovered"]
    assert db.query(Track).filter(Track.user_id == uid).count() == out["new_tracks"]


def test_freshness_scoring_orders_recent():
    from app.services.spotify import freshness_score

    old = freshness_score(datetime.date(2024, 1, 1))
    new = freshness_score(datetime.date.today())
    assert new > old


def test_spotify_endpoint_requires_auth(client):
    assert client.get("/api/spotify/status").status_code == 401