"""Profile + environment storage for Forbin.

A profile is a named bundle of named environments; an environment is a
connection-fields triple (server URL, optional health URL, token).
The whole document — profiles, globals, and the active pointer — lives
in a single ``profiles.json`` file in ``~/.forbin/``.

This module owns the storage shape and CRUD; ``config.py`` owns the
value-resolution layer (module-level globals, env shadowing).
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import FORBIN_DIR, ensure_forbin_dir

# Single-file store. Env-overridable so tests can sandbox without touching
# the user's real ~/.forbin/.
PROFILES_FILE = Path(os.getenv("FORBIN_PROFILES_FILE", str(FORBIN_DIR / "profiles.json")))

SCHEMA_VERSION = 1

# Field-key sets — single source of truth used across the app to decide
# which storage slot a setting belongs in (per-environment vs. global).
PER_ENV_FIELDS = ("MCP_SERVER_URL", "MCP_HEALTH_URL", "MCP_TOKEN")
GLOBAL_FIELDS = ("VERBOSE", "MCP_TOOL_TIMEOUT")

# Names are JSON keys and appear in the picker UI; the regex avoids
# whitespace, slashes, and quoting headaches without being so strict that
# normal users hit it.
NAME_REGEX = re.compile(r"^[A-Za-z0-9_.-]+$")


class ProfileError(ValueError):
    """Raised on invalid profile/environment operations (bad name, missing
    target, refusal to delete the only profile / only environment)."""


def is_valid_name(name: str) -> bool:
    return bool(name) and bool(NAME_REGEX.match(name))


def default_profiles_doc() -> dict:
    """Return a fresh empty document with one empty default profile.

    The default profile starts with one (empty) default environment so the
    invariant 'every profile has at least one environment' holds from
    creation. Required connection fields are filled in by the wizard.
    """
    return {
        "version": SCHEMA_VERSION,
        "active": {"profile": "default", "environment": "default"},
        "globals": {},
        "profiles": {
            "default": {
                "environments": {
                    "default": {},
                },
            },
        },
    }


def _backup_path(suffix: str) -> Path:
    """Return a timestamped backup path next to PROFILES_FILE."""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return PROFILES_FILE.with_name(f"{PROFILES_FILE.name}.{suffix}.{ts}.bak")


def load_profiles() -> dict:
    """Load profiles.json, returning a fresh default doc on any failure.

    A malformed file is renamed to a timestamped ``.malformed.<ts>.bak``
    so we never silently destroy the user's data — they can hand-edit and
    restore. Missing file returns the default doc without writing.
    """
    if not PROFILES_FILE.exists():
        return default_profiles_doc()
    try:
        with open(PROFILES_FILE) as f:
            doc = json.load(f)
    except Exception as e:
        from .display import console

        backup = _backup_path("malformed")
        try:
            os.replace(PROFILES_FILE, backup)
            console.print(
                f"[yellow]Warning: profiles file was malformed ({e}); "
                f"backed up to {backup} and starting fresh.[/yellow]"
            )
        except Exception:
            console.print(
                f"[yellow]Warning: could not load profiles file ({e}); starting fresh.[/yellow]"
            )
        return default_profiles_doc()

    ok, why = validate_doc(doc)
    if not ok:
        from .display import console

        backup = _backup_path("invalid")
        try:
            os.replace(PROFILES_FILE, backup)
        except Exception:
            pass
        console.print(
            f"[yellow]Warning: profiles file failed validation ({why}); "
            f"backed up to {backup} and starting fresh.[/yellow]"
        )
        return default_profiles_doc()

    return _repair_active_pointer(doc)


def save_profiles(doc: dict) -> bool:
    """Write the document to disk. Validates first; refuses to write a
    malformed doc (logs and returns False) so a buggy caller can't
    corrupt the on-disk file."""
    ok, why = validate_doc(doc)
    if not ok:
        from .display import console

        console.print(f"[red]Refused to save invalid profiles doc: {why}[/red]")
        return False
    try:
        ensure_forbin_dir()
        with open(PROFILES_FILE, "w") as f:
            json.dump(doc, f, indent=2)
        return True
    except Exception as e:
        from .display import console

        console.print(f"[red]Error saving profiles file: {e}[/red]")
        return False


def validate_doc(doc: dict) -> tuple[bool, str]:
    """Schema check. Returns (ok, reason)."""
    if not isinstance(doc, dict):
        return False, "document is not a JSON object"
    version = doc.get("version")
    if version != SCHEMA_VERSION:
        return False, f"unsupported version {version!r}"
    profiles = doc.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        return False, "no profiles defined"
    for pname, pbody in profiles.items():
        if not is_valid_name(pname):
            return False, f"invalid profile name: {pname!r}"
        if not isinstance(pbody, dict):
            return False, f"profile {pname!r} is not an object"
        envs = pbody.get("environments")
        if not isinstance(envs, dict) or not envs:
            return False, f"profile {pname!r} has no environments"
        for ename, ebody in envs.items():
            if not is_valid_name(ename):
                return False, f"invalid environment name: {pname}/{ename!r}"
            if not isinstance(ebody, dict):
                return False, f"environment {pname}/{ename!r} is not an object"
    active = doc.get("active")
    if not isinstance(active, dict):
        return False, "missing or invalid 'active' pointer"
    if "profile" not in active or "environment" not in active:
        return False, "'active' pointer must have 'profile' and 'environment'"
    globals_ = doc.get("globals")
    if not isinstance(globals_, dict):
        return False, "'globals' must be an object"
    return True, ""


def _repair_active_pointer(doc: dict) -> dict:
    """If the active pointer references a missing profile/env, fall back
    to the first profile alphabetically and its first environment.

    The repair is in-memory; callers persist via save_profiles() when they
    next save. This keeps hand-edited files usable even if the user
    deleted the active profile manually.
    """
    profiles = doc["profiles"]
    active = doc["active"]
    p = active.get("profile")
    e = active.get("environment")
    if p in profiles and e in profiles[p]["environments"]:
        return doc

    fallback_profile = sorted(profiles.keys())[0]
    fallback_env = sorted(profiles[fallback_profile]["environments"].keys())[0]
    doc["active"] = {"profile": fallback_profile, "environment": fallback_env}

    from .display import console

    console.print(
        f"[yellow]Warning: active profile/environment "
        f"({p!r}/{e!r}) not found; falling back to "
        f"{fallback_profile}/{fallback_env}.[/yellow]"
    )
    return doc


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


def list_profiles(doc: dict) -> list[str]:
    return sorted(doc["profiles"].keys())


def list_environments(doc: dict, profile: str) -> list[str]:
    if profile not in doc["profiles"]:
        raise ProfileError(f"profile {profile!r} does not exist")
    return sorted(doc["profiles"][profile]["environments"].keys())


def get_active(doc: dict) -> tuple[str, str]:
    active = doc["active"]
    return active["profile"], active["environment"]


def get_active_environment(doc: dict) -> dict:
    """Return the connection-fields dict for the active environment.

    Caller may mutate the returned dict in place; it's a live reference
    into the doc, not a copy. save_profiles(doc) persists the change.
    """
    p, e = get_active(doc)
    return doc["profiles"][p]["environments"][e]


def set_active(doc: dict, profile: str, environment: str) -> None:
    if profile not in doc["profiles"]:
        raise ProfileError(f"profile {profile!r} does not exist")
    if environment not in doc["profiles"][profile]["environments"]:
        raise ProfileError(f"environment {profile}/{environment!r} does not exist")
    doc["active"] = {"profile": profile, "environment": environment}


def get_global(doc: dict, key: str) -> Optional[str]:
    """Read a global setting (VERBOSE / MCP_TOOL_TIMEOUT). Returns None if
    unset so callers can apply their own default."""
    val = doc["globals"].get(key)
    return None if val is None else str(val)


def set_global(doc: dict, key: str, value: Optional[str]) -> None:
    if value is None or value == "":
        doc["globals"].pop(key, None)
    else:
        doc["globals"][key] = str(value)


# ---------------------------------------------------------------------------
# Profile CRUD
# ---------------------------------------------------------------------------


def add_profile(
    doc: dict,
    name: str,
    seed_env_name: str = "default",
    seed_env_fields: Optional[dict] = None,
) -> None:
    if not is_valid_name(name):
        raise ProfileError(f"invalid profile name: {name!r}")
    if name in doc["profiles"]:
        raise ProfileError(f"profile {name!r} already exists")
    if not is_valid_name(seed_env_name):
        raise ProfileError(f"invalid environment name: {seed_env_name!r}")
    doc["profiles"][name] = {
        "environments": {seed_env_name: dict(seed_env_fields or {})},
    }


def rename_profile(doc: dict, old: str, new: str) -> None:
    if old not in doc["profiles"]:
        raise ProfileError(f"profile {old!r} does not exist")
    if old == new:
        return
    if not is_valid_name(new):
        raise ProfileError(f"invalid profile name: {new!r}")
    if new in doc["profiles"]:
        raise ProfileError(f"profile {new!r} already exists")
    doc["profiles"][new] = doc["profiles"].pop(old)
    if doc["active"]["profile"] == old:
        doc["active"]["profile"] = new


def delete_profile(doc: dict, name: str) -> None:
    if name not in doc["profiles"]:
        raise ProfileError(f"profile {name!r} does not exist")
    if len(doc["profiles"]) == 1:
        raise ProfileError("cannot delete the only profile")
    del doc["profiles"][name]
    if doc["active"]["profile"] == name:
        # Active was just deleted; let the repair logic relocate the pointer.
        _repair_active_pointer(doc)


# ---------------------------------------------------------------------------
# Environment CRUD
# ---------------------------------------------------------------------------


def add_environment(
    doc: dict,
    profile: str,
    env_name: str,
    fields: Optional[dict] = None,
) -> None:
    if profile not in doc["profiles"]:
        raise ProfileError(f"profile {profile!r} does not exist")
    if not is_valid_name(env_name):
        raise ProfileError(f"invalid environment name: {env_name!r}")
    envs = doc["profiles"][profile]["environments"]
    if env_name in envs:
        raise ProfileError(f"environment {profile}/{env_name!r} already exists")
    envs[env_name] = dict(fields or {})


def rename_environment(doc: dict, profile: str, old: str, new: str) -> None:
    if profile not in doc["profiles"]:
        raise ProfileError(f"profile {profile!r} does not exist")
    envs = doc["profiles"][profile]["environments"]
    if old not in envs:
        raise ProfileError(f"environment {profile}/{old!r} does not exist")
    if old == new:
        return
    if not is_valid_name(new):
        raise ProfileError(f"invalid environment name: {new!r}")
    if new in envs:
        raise ProfileError(f"environment {profile}/{new!r} already exists")
    envs[new] = envs.pop(old)
    if doc["active"]["profile"] == profile and doc["active"]["environment"] == old:
        doc["active"]["environment"] = new


def delete_environment(doc: dict, profile: str, name: str) -> None:
    if profile not in doc["profiles"]:
        raise ProfileError(f"profile {profile!r} does not exist")
    envs = doc["profiles"][profile]["environments"]
    if name not in envs:
        raise ProfileError(f"environment {profile}/{name!r} does not exist")
    if len(envs) == 1:
        raise ProfileError(f"cannot delete the only environment in profile {profile!r}")
    del envs[name]
    if doc["active"]["profile"] == profile and doc["active"]["environment"] == name:
        _repair_active_pointer(doc)
