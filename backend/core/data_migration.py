"""XDG data/config directory resolution and atomic migration (hks -> hyprdeck)."""

from __future__ import annotations

import hashlib
import os
from typing import Any, Mapping

from backend.core.constants import ACTIVE_GUARD_FILENAME, LEGACY_STATE_DIR_NAME, REVERT_GUARD_SUBDIR, STATE_DIR_NAME


def _home_from_env(environ: Mapping[str, str]) -> str:
    return os.path.abspath(os.path.expanduser(environ.get("HOME", "").strip() or "~"))


def _config_base(environ: Mapping[str, str]) -> str:
    xdg = environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg:
        return os.path.abspath(os.path.expanduser(xdg))
    return os.path.join(_home_from_env(environ), ".config")


def _data_base(environ: Mapping[str, str]) -> str:
    xdg = environ.get("XDG_DATA_HOME", "").strip()
    if xdg:
        return os.path.abspath(os.path.expanduser(xdg))
    return os.path.join(_home_from_env(environ), ".local", "share")


def resolve_config_app_dir(environ: Mapping[str, str] | None = None) -> str:
    """Resolve HyprDeck config dir: new if exists > legacy if exists > new default."""
    env_map = os.environ if environ is None else environ
    base = _config_base(env_map)
    new_dir = os.path.join(base, STATE_DIR_NAME)
    old_dir = os.path.join(base, LEGACY_STATE_DIR_NAME)
    if os.path.exists(new_dir):
        return os.path.abspath(new_dir)
    if os.path.exists(old_dir):
        return os.path.abspath(old_dir)
    return os.path.abspath(new_dir)


def resolve_data_app_dir(environ: Mapping[str, str] | None = None) -> str:
    """Resolve HyprDeck data dir: new if exists > legacy if exists > new default."""
    env_map = os.environ if environ is None else environ
    base = _data_base(env_map)
    new_dir = os.path.join(base, STATE_DIR_NAME)
    old_dir = os.path.join(base, LEGACY_STATE_DIR_NAME)
    if os.path.exists(new_dir):
        return os.path.abspath(new_dir)
    if os.path.exists(old_dir):
        return os.path.abspath(old_dir)
    return os.path.abspath(new_dir)


def _snapshot_tree(root: str) -> dict[str, str]:
    """Return {rel_path: sha256} for all regular files under `root`."""
    out: dict[str, str] = {}
    if not os.path.isdir(root):
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fname in sorted(filenames):
            full = os.path.join(dirpath, fname)
            rel = os.path.relpath(full, root)
            if os.path.islink(full):
                out[rel] = f"symlink:{os.readlink(full)}"
            else:
                with open(full, "rb") as f:
                    out[rel] = hashlib.sha256(f.read()).hexdigest()
    return out


def migrate_data(
    *,
    apply: bool = False,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Migrate ~/.config/hks -> ~/.config/hyprdeck and ~/.local/share/hks -> ~/.local/share/hyprdeck."""
    env_map = os.environ if env is None else env
    cfg_base = _config_base(env_map)
    data_base = _data_base(env_map)

    candidates = [
        ("config", os.path.join(cfg_base, LEGACY_STATE_DIR_NAME), os.path.join(cfg_base, STATE_DIR_NAME)),
        ("data", os.path.join(data_base, LEGACY_STATE_DIR_NAME), os.path.join(data_base, STATE_DIR_NAME)),
    ]

    # Check pending revert-guard state before any changes
    for data_dir in (os.path.join(data_base, LEGACY_STATE_DIR_NAME), os.path.join(data_base, STATE_DIR_NAME)):
        guard_file = os.path.join(data_dir, REVERT_GUARD_SUBDIR, ACTIVE_GUARD_FILENAME)
        if os.path.exists(guard_file):
            return {
                "ok": False,
                "applied": False,
                "error": f"Pending revert-guard state detected ({guard_file}); resolve or cancel before migrating.",
                "pairs": [],
                "undo_commands": [],
            }

    pairs: list[dict[str, Any]] = []
    any_pending = False
    any_migrated = False

    for kind, old_p, new_p in candidates:
        old_is_link = os.path.islink(old_p)
        old_exists = os.path.exists(old_p) or old_is_link
        new_exists = os.path.exists(new_p) or os.path.islink(new_p)

        if old_is_link and new_exists and os.path.realpath(old_p) == os.path.realpath(new_p):
            any_migrated = True
            pairs.append({
                "kind": kind,
                "source": old_p,
                "destination": new_p,
                "status": "already_migrated",
                "files": _snapshot_tree(new_p),
            })
            continue

        if new_exists:
            if os.path.isdir(new_p) and os.listdir(new_p):
                return {
                    "ok": False,
                    "applied": False,
                    "error": f"Destination directory already exists and is non-empty: {new_p}",
                    "pairs": pairs,
                    "undo_commands": [],
                }
            if not os.path.isdir(new_p):
                return {
                    "ok": False,
                    "applied": False,
                    "error": f"Destination path already exists and is not an empty directory: {new_p}",
                    "pairs": pairs,
                    "undo_commands": [],
                }

        if not old_exists:
            pairs.append({
                "kind": kind,
                "source": old_p,
                "destination": new_p,
                "status": "missing_source",
                "files": {},
            })
            continue

        any_pending = True
        pairs.append({
            "kind": kind,
            "source": old_p,
            "destination": new_p,
            "status": "pending",
            "files": _snapshot_tree(old_p),
        })

    if not any_pending and not any_migrated:
        return {
            "ok": False,
            "applied": False,
            "error": "No legacy hks directories found to migrate.",
            "pairs": pairs,
            "undo_commands": [],
        }

    undo_commands: list[str] = []
    for item in pairs:
        if item["status"] in ("pending", "already_migrated"):
            undo_commands.append(f"rm -f {item['source']!r} && mv {item['destination']!r} {item['source']!r}")

    if not apply:
        return {
            "ok": True,
            "applied": False,
            "already_migrated": (not any_pending and any_migrated),
            "pairs": pairs,
            "undo_commands": undo_commands,
        }

    # Execute atomic same-filesystem rename + compatibility symlink + SHA-256 verification
    for item in pairs:
        if item["status"] != "pending":
            continue
        old_p = item["source"]
        new_p = item["destination"]
        before_snap = item["files"]
        if os.path.isdir(new_p) and not os.listdir(new_p):
            os.rmdir(new_p)
        os.makedirs(os.path.dirname(new_p), exist_ok=True)
        os.rename(old_p, new_p)
        os.symlink(new_p, old_p)
        after_snap = _snapshot_tree(new_p)
        if before_snap != after_snap:
            return {
                "ok": False,
                "applied": True,
                "error": f"Verification mismatch after moving {old_p} -> {new_p}",
                "pairs": pairs,
                "undo_commands": undo_commands,
            }
        item["status"] = "migrated"
        item["verified"] = True

    return {
        "ok": True,
        "applied": True,
        "already_migrated": (not any_pending and any_migrated),
        "pairs": pairs,
        "undo_commands": undo_commands,
    }
