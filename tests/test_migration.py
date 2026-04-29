"""Tests for the legacy config.json -> profiles.json migration."""

import json

import pytest

from forbin import config, profiles


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    """Point both stores at a temp dir and clear any per-env env vars
    that would otherwise re-seed the migration logic."""
    legacy = tmp_path / "config.json"
    new = tmp_path / "profiles.json"
    monkeypatch.setattr(config, "FORBIN_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", legacy)
    monkeypatch.setattr(profiles, "PROFILES_FILE", new)
    for k in profiles.PER_ENV_FIELDS + profiles.GLOBAL_FIELDS:
        monkeypatch.delenv(k, raising=False)
    return tmp_path


def test_no_state_seeds_from_env_when_present(isolated_dirs, monkeypatch):
    """A clean install with .env-supplied connection vars should produce
    a default/default profile pre-populated from those vars."""
    monkeypatch.setenv("MCP_SERVER_URL", "https://from-env.example.com/mcp")
    monkeypatch.setenv("MCP_TOKEN", "envtok")
    ran = config.migrate_legacy_config_if_needed()
    assert ran is True
    doc = profiles.load_profiles()
    env = doc["profiles"]["default"]["environments"]["default"]
    assert env["MCP_SERVER_URL"] == "https://from-env.example.com/mcp"
    assert env["MCP_TOKEN"] == "envtok"


def test_clean_slate_does_not_migrate(isolated_dirs):
    """No legacy file and no .env values → wizard branch (caller's
    responsibility), so migrate returns False."""
    ran = config.migrate_legacy_config_if_needed()
    assert ran is False
    assert not profiles.PROFILES_FILE.exists()


def test_legacy_config_imports_per_env_and_globals(isolated_dirs):
    config.CONFIG_FILE.write_text(
        json.dumps(
            {
                "MCP_SERVER_URL": "https://legacy.example.com/mcp",
                "MCP_TOKEN": "legtok",
                "MCP_HEALTH_URL": "https://legacy.example.com/health",
                "MCP_TOOL_TIMEOUT": "900",
                "VERBOSE": "true",
            }
        )
    )
    ran = config.migrate_legacy_config_if_needed()
    assert ran is True
    doc = profiles.load_profiles()
    env = doc["profiles"]["default"]["environments"]["default"]
    assert env["MCP_SERVER_URL"] == "https://legacy.example.com/mcp"
    assert env["MCP_TOKEN"] == "legtok"
    assert env["MCP_HEALTH_URL"] == "https://legacy.example.com/health"
    assert doc["globals"]["MCP_TOOL_TIMEOUT"] == "900"
    assert doc["globals"]["VERBOSE"] == "true"


def test_legacy_renamed_to_bak(isolated_dirs):
    config.CONFIG_FILE.write_text(json.dumps({"MCP_SERVER_URL": "x", "MCP_TOKEN": "y"}))
    config.migrate_legacy_config_if_needed()
    assert not config.CONFIG_FILE.exists()
    assert (isolated_dirs / "config.json.bak").exists()


def test_migration_is_idempotent(isolated_dirs):
    config.CONFIG_FILE.write_text(json.dumps({"MCP_SERVER_URL": "x", "MCP_TOKEN": "y"}))
    first = config.migrate_legacy_config_if_needed()
    second = config.migrate_legacy_config_if_needed()
    assert first is True
    assert second is False  # profiles.json now exists


def test_legacy_takes_priority_over_env(isolated_dirs, monkeypatch):
    """Legacy file present + .env vars: the file wins, env vars are ignored
    (the warning is shown, but the imported values come from the file)."""
    monkeypatch.setenv("MCP_SERVER_URL", "https://envwins.example.com/mcp")
    config.CONFIG_FILE.write_text(
        json.dumps(
            {
                "MCP_SERVER_URL": "https://legacy.example.com/mcp",
                "MCP_TOKEN": "legtok",
            }
        )
    )
    config.migrate_legacy_config_if_needed()
    doc = profiles.load_profiles()
    assert (
        doc["profiles"]["default"]["environments"]["default"]["MCP_SERVER_URL"]
        == "https://legacy.example.com/mcp"
    )
