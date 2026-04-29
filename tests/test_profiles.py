"""Tests for forbin/profiles.py — schema validation, CRUD, refusal cases."""

import json

import pytest

from forbin import profiles


@pytest.fixture
def isolated_profiles(tmp_path, monkeypatch):
    """Point PROFILES_FILE at a temporary file and reload the module
    attribute so tests don't touch ~/.forbin/."""
    target = tmp_path / "profiles.json"
    monkeypatch.setattr(profiles, "PROFILES_FILE", target)
    monkeypatch.setattr("forbin.config.FORBIN_DIR", tmp_path)
    return target


def test_default_doc_validates():
    doc = profiles.default_profiles_doc()
    ok, why = profiles.validate_doc(doc)
    assert ok, why


def test_validate_rejects_wrong_version():
    doc = profiles.default_profiles_doc()
    doc["version"] = 99
    ok, why = profiles.validate_doc(doc)
    assert not ok
    assert "version" in why


def test_validate_rejects_empty_profiles():
    doc = profiles.default_profiles_doc()
    doc["profiles"] = {}
    ok, _ = profiles.validate_doc(doc)
    assert not ok


def test_validate_rejects_profile_with_no_envs():
    doc = profiles.default_profiles_doc()
    doc["profiles"]["broken"] = {"environments": {}}
    ok, _ = profiles.validate_doc(doc)
    assert not ok


def test_validate_rejects_invalid_name():
    doc = profiles.default_profiles_doc()
    doc["profiles"]["has space"] = {"environments": {"default": {}}}
    ok, _ = profiles.validate_doc(doc)
    assert not ok


def test_save_then_load_roundtrip(isolated_profiles):
    doc = profiles.default_profiles_doc()
    profiles.add_profile(doc, "staging", "us-east", {"MCP_SERVER_URL": "x"})
    assert profiles.save_profiles(doc)
    loaded = profiles.load_profiles()
    assert "staging" in loaded["profiles"]
    assert loaded["profiles"]["staging"]["environments"]["us-east"]["MCP_SERVER_URL"] == "x"


def test_load_malformed_file_creates_backup_and_returns_default(isolated_profiles, capsys):
    isolated_profiles.write_text("{not valid json")
    doc = profiles.load_profiles()
    assert doc["version"] == profiles.SCHEMA_VERSION
    # The original file is gone; a *.malformed.*.bak sibling exists.
    backups = list(isolated_profiles.parent.glob("profiles.json.malformed.*.bak"))
    assert len(backups) == 1


def test_load_invalid_schema_creates_backup(isolated_profiles):
    isolated_profiles.write_text(json.dumps({"version": 999, "profiles": {}}))
    doc = profiles.load_profiles()
    assert doc["version"] == profiles.SCHEMA_VERSION
    backups = list(isolated_profiles.parent.glob("profiles.json.invalid.*.bak"))
    assert len(backups) == 1


def test_save_refuses_invalid_doc(isolated_profiles, capsys):
    bad = {"version": 1}  # missing profiles, active, globals
    assert not profiles.save_profiles(bad)
    assert not isolated_profiles.exists()


def test_add_profile_requires_valid_name():
    doc = profiles.default_profiles_doc()
    with pytest.raises(profiles.ProfileError):
        profiles.add_profile(doc, "has space")
    with pytest.raises(profiles.ProfileError):
        profiles.add_profile(doc, "")


def test_add_profile_rejects_duplicate():
    doc = profiles.default_profiles_doc()
    with pytest.raises(profiles.ProfileError):
        profiles.add_profile(doc, "default")


def test_rename_profile_moves_active_pointer():
    doc = profiles.default_profiles_doc()
    profiles.rename_profile(doc, "default", "main")
    assert "main" in doc["profiles"]
    assert "default" not in doc["profiles"]
    assert doc["active"]["profile"] == "main"


def test_rename_profile_rejects_collision():
    doc = profiles.default_profiles_doc()
    profiles.add_profile(doc, "staging")
    with pytest.raises(profiles.ProfileError):
        profiles.rename_profile(doc, "default", "staging")


def test_delete_only_profile_refused():
    doc = profiles.default_profiles_doc()
    with pytest.raises(profiles.ProfileError):
        profiles.delete_profile(doc, "default")


def test_delete_active_profile_repairs_pointer():
    doc = profiles.default_profiles_doc()
    profiles.add_profile(doc, "staging")
    profiles.set_active(doc, "staging", "default")
    profiles.delete_profile(doc, "staging")
    assert doc["active"]["profile"] == "default"


def test_add_environment_rejects_duplicate():
    doc = profiles.default_profiles_doc()
    with pytest.raises(profiles.ProfileError):
        profiles.add_environment(doc, "default", "default")


def test_rename_environment_moves_active():
    doc = profiles.default_profiles_doc()
    profiles.rename_environment(doc, "default", "default", "primary")
    assert "primary" in doc["profiles"]["default"]["environments"]
    assert doc["active"]["environment"] == "primary"


def test_delete_only_environment_refused():
    doc = profiles.default_profiles_doc()
    with pytest.raises(profiles.ProfileError):
        profiles.delete_environment(doc, "default", "default")


def test_repair_active_pointer_falls_back():
    doc = profiles.default_profiles_doc()
    profiles.add_profile(doc, "alpha")
    doc["active"] = {"profile": "missing", "environment": "missing"}
    profiles._repair_active_pointer(doc)
    # Falls back alphabetically — alpha < default.
    assert doc["active"]["profile"] == "alpha"


def test_set_active_validates_target():
    doc = profiles.default_profiles_doc()
    with pytest.raises(profiles.ProfileError):
        profiles.set_active(doc, "missing", "default")
    profiles.add_profile(doc, "staging")
    with pytest.raises(profiles.ProfileError):
        profiles.set_active(doc, "staging", "missing")


def test_get_set_global():
    doc = profiles.default_profiles_doc()
    assert profiles.get_global(doc, "VERBOSE") is None
    profiles.set_global(doc, "VERBOSE", "true")
    assert profiles.get_global(doc, "VERBOSE") == "true"
    profiles.set_global(doc, "VERBOSE", None)
    assert profiles.get_global(doc, "VERBOSE") is None
