"""YouTube provider tests: factory auto-mock, mock OAuth + upload flows."""

from __future__ import annotations


def test_factory_auto_mocks_without_credentials():
    from app.services.youtube import get_youtube_provider

    provider = get_youtube_provider()
    assert provider.name == "MOCK"


def test_mock_connect_and_channel():
    from app.services.youtube import connect_info, exchange_oauth_callback
    from app.database import SessionLocal
    from app.models import User
    from app.security import hash_password

    db = SessionLocal()
    try:
        user = db.query(User).first()
        if user is None:
            user = User(email="yt@test.dev", password_hash=hash_password("x"), name="YT")
            db.add(user)
            db.commit()
            db.refresh(user)

        info = connect_info(db, user)
        assert info["auth_url"]  # mock returns a fake local URL
        acc = exchange_oauth_callback(db, user, "mock-code-123")
        assert acc.channel_name
    finally:
        db.close()


def test_mock_upload_returns_url(db, demo_user):
    from app.services.youtube import exchange_oauth_callback, upload_video

    exchange_oauth_callback(db, demo_user, "mock-code-123")   # connect first
    from types import SimpleNamespace
    fake_video = SimpleNamespace(file_path="C:/nonexistent/v.mp4", thumbnail_path=None)
    fake_upload = SimpleNamespace()
    res = upload_video(
        db, demo_user, fake_upload, fake_video,
        title="Test Upload", description="x", tags=["a", "b"],
        category="Music", privacy="private", playlist_id=None, scheduled_at=None,
    )
    assert res.youtube_video_id
    assert res.youtube_url.startswith("https://www.youtube.com/watch")
    assert res.status == "uploaded"


def test_dashboard_shape(client, auth_headers):
    r = client.get("/api/dashboard", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body["stats"]) == {
        "tracks_discovered", "awaiting_permission", "licensed_tracks",
        "videos_generated", "uploaded_to_youtube", "failed_jobs",
    }
    assert "recent_tracks" in body and "queue" in body
    assert body["provider_mode"] in ("MOCK", "REAL")