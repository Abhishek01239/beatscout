"""Unit tests for the autonomous daily pipeline (app/auto.py, jamendo.py).

No network: exercises license gating, state/dedupe, and provider fallback.
"""

from __future__ import annotations

import json

import pytest

from app.auto import AutoState, SynthProvider
from app.services.jamendo import (
    license_allows,
    license_code_from_url,
)


# --- license gating ------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("by", True),
    ("CC BY 4.0", True),
    ("by-sa", True),
    ("zero", True),
    ("by-nc", False),     # no commercial use
    ("by-nc-sa", False),   # no commercial use
    ("by-nd", False),      # no derivatives
    ("", False),
    ("all rights reserved", False),
])
def test_license_gate(name: str, expected: bool) -> None:
    assert license_allows(name) is expected


def test_license_code_from_url() -> None:
    assert license_code_from_url("https://creativecommons.org/licenses/by/3.0/") == "by"
    assert license_code_from_url("https://creativecommons.org/licenses/by-sa/4.0/") == "by-sa"
    assert license_code_from_url("") == ""
    assert license_code_from_url("https://example.com/not-a-license") == ""


# --- state / dedupe ------------------------------------------------------

def test_state_dedupe(tmp_path) -> None:
    st = AutoState(tmp_path / "auto_state.json")
    assert st.already_processed("jamendo:1") is False
    st.record("jamendo:1", "published", extra={"title": "T"})
    st.record("jamendo:2", "error", extra={"error": "boom"})
    st.save()

    st2 = AutoState(tmp_path / "auto_state.json")
    assert st2.already_processed("jamendo:1") is True
    assert st2.already_processed("jamendo:2") is True
    assert st2.already_processed("jamendo:3") is False
    assert [p["title"] for p in st2.published] == ["T"]


def test_state_corrupt_file_starts_fresh(tmp_path) -> None:
    p = tmp_path / "auto_state.json"
    p.write_text("{not json", encoding="utf-8")
    st = AutoState(p)
    assert st.already_processed("x") is False  # no crash, clean slate


# --- synth provider (offline fallback) -----------------------------------

def test_synth_provider_returns_limited_cc_metas() -> None:
    prov = SynthProvider()
    metas = prov.discover(genres=["Lo-fi"], release_from=None, release_to=None, limit=5)
    assert len(metas) == 5
    assert all(m.spotify_track_id.startswith("synth:") for m in metas)
    assert all(m.external_ids["license_name"] == "by" for m in metas)


def test_get_provider_auto_falls_back_to_synth(monkeypatch) -> None:
    from app import auto
    monkeypatch.setattr(auto.SynthProvider, "__init__", lambda self: None)
    monkeypatch.setattr("app.config.get_settings", lambda: type("S", (), {"JAMENDO_CLIENT_ID": ""})())
    from app.auto import get_provider
    provider, name = get_provider("auto")
    assert name == "synth"