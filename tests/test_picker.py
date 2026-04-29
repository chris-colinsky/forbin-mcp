"""Tests for forbin/picker.py — selection flow and CRUD."""

from unittest.mock import patch

import pytest

from forbin import picker, profiles


@pytest.fixture
def seeded_profiles(tmp_path, monkeypatch):
    """Seed profiles.json with a multi-profile, multi-env setup."""
    target = tmp_path / "profiles.json"
    monkeypatch.setattr(profiles, "PROFILES_FILE", target)
    monkeypatch.setattr("forbin.config.FORBIN_DIR", tmp_path)
    doc = profiles.default_profiles_doc()
    profiles.add_profile(doc, "staging", "us-east", {"MCP_SERVER_URL": "stg-east"})
    profiles.add_environment(doc, "staging", "eu-west", {"MCP_SERVER_URL": "stg-eu"})
    profiles.save_profiles(doc)
    return target


def _drive(inputs):
    """Replay scripted answers through Rich's Prompt.ask."""
    it = iter(inputs)

    def fake(*a, **k):
        return next(it)

    return patch("forbin.picker.Prompt.ask", side_effect=fake)


def test_selecting_single_env_profile_skips_env_picker(seeded_profiles):
    """Picking the 'default' profile (1 env) should immediately return."""
    # Profile list (alphabetical): default, staging.
    with _drive(["1"]):  # pick 'default'
        result = picker.pick_profile_and_environment()
    assert result == ("default", "default")


def test_selecting_multi_env_profile_drops_into_env_picker(seeded_profiles):
    # Pick 'staging' (idx 2), then env 'us-east' (idx 2 alphabetically: eu-west=1, us-east=2).
    with _drive(["2", "2"]):
        result = picker.pick_profile_and_environment()
    assert result == ("staging", "us-east")


def test_back_at_profile_picker_returns_none(seeded_profiles):
    with _drive(["b"]):
        assert picker.pick_profile_and_environment() is None


def test_back_at_env_picker_returns_to_profiles(seeded_profiles):
    """Picking 'staging' then 'b' goes back to profiles, then 'b' again cancels."""
    with _drive(["2", "b", "b"]):
        assert picker.pick_profile_and_environment() is None


def test_invalid_input_loops_at_profile_picker(seeded_profiles):
    # 'xyz' is invalid; then '99' is out of range; then '1' picks default.
    with _drive(["xyz", "99", "1"]):
        result = picker.pick_profile_and_environment()
    assert result == ("default", "default")


def test_create_profile_persists_and_lets_you_pick_it(seeded_profiles):
    # 'n' → name → seed env name → ENTER picks the new profile.
    # New profile has 1 env so env picker is skipped.
    with _drive(["n", "production", "primary", "2"]):
        # After creating 'production', list becomes: default, production, staging.
        # Pick idx 2 = production.
        result = picker.pick_profile_and_environment()
    assert result == ("production", "primary")
    doc = profiles.load_profiles()
    assert "production" in doc["profiles"]


def test_picker_persists_active_pointer(seeded_profiles):
    with _drive(["2", "1"]):  # staging / eu-west
        picker.pick_profile_and_environment()
    doc = profiles.load_profiles()
    assert profiles.get_active(doc) == ("staging", "eu-west")
