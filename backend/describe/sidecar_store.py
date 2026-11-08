"""Persistent sidecar storage: atomic read-modify-write, locking, migration, and backups."""

from __future__ import annotations

import datetime
import fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile
from typing import Any

from backend.editor.backups import resolve_backup_dir
from backend.models.types import (
    VALID_CATEGORIES,
    BindRecord,
    DisabledBindRecord,
)
from backend.parser.modifiers import resolve_modifier_tokens


class SidecarStoreError(Exception):
    """Base exception for sidecar storage errors."""


class SidecarCollisionError(SidecarStoreError):
    """Raised when migrating a sidecar entry collides with an existing entry."""


def normalize_match_dict(match: dict[str, Any]) -> dict[str, Any]:
    """Normalize a match dictionary into canonical form."""
    raw_mods = match.get("modifiers") or []
    if isinstance(raw_mods, str):
        toks = [t.strip() for t in re.split(r"[,+\s]+", raw_mods) if t.strip()]
    else:
        toks = [str(m).strip() for m in raw_mods if str(m).strip()]
    parsed = resolve_modifier_tokens(toks)
    if parsed.unknown_tokens:
        raise SidecarStoreError(
            f"Unknown modifier(s) in match: {', '.join(parsed.unknown_tokens)}"
        )

    key = str(match.get("key", "")).strip()
    if not key:
        raise SidecarStoreError("Sidecar match must have a non-empty key")

    submap = str(match.get("submap", "") or "").strip()
    dsp = match.get("dispatcher")
    clean_dsp: str | None = None
    if dsp is not None and str(dsp).strip():
        clean_dsp = str(dsp).strip()

    result: dict[str, Any] = {
        "modifiers": parsed.modifiers,
        "key": key,
        "submap": submap,
    }
    if clean_dsp is not None:
        result["dispatcher"] = clean_dsp
    return result


def matches_equal(m1: dict[str, Any], m2: dict[str, Any]) -> bool:
    """Check if two match dictionaries refer to the same keybinding."""
    mods1 = frozenset(m1.get("modifiers") or [])
    mods2 = frozenset(m2.get("modifiers") or [])
    if mods1 != mods2:
        return False
    if str(m1.get("key", "")).strip().lower() != str(m2.get("key", "")).strip().lower():
        return False
    if str(m1.get("submap", "") or "") != str(m2.get("submap", "") or ""):
        return False

    dsp1 = m1.get("dispatcher")
    dsp2 = m2.get("dispatcher")
    dsp1_clean = str(dsp1).strip() if dsp1 else None
    dsp2_clean = str(dsp2).strip() if dsp2 else None
    if dsp1_clean is not None and dsp2_clean is not None:
        if not _dispatcher_matches(dsp2_clean, dsp1_clean) and not _dispatcher_matches(dsp1_clean, dsp2_clean):
            return False
    return True


def _dispatcher_matches(bind_dsp_path: str, filter_dsp: str) -> bool:
    full = bind_dsp_path.strip()
    leaf = full.rsplit(".", 1)[-1]
    return filter_dsp == full or filter_dsp == leaf


def match_override_to_bind(ov_match: dict[str, Any], bind: BindRecord) -> bool:
    """Check if an override match matches an active BindRecord."""
    ov_mods = frozenset(ov_match.get("modifiers") or [])
    bind_mods = frozenset(bind.modifiers or [])
    if ov_mods != bind_mods:
        return False
    if str(ov_match.get("key", "")).strip().lower() != str(bind.key or "").strip().lower():
        return False
    ov_submap = str(ov_match.get("submap", "") or "")
    bind_submap = str(bind.submap or "")
    if ov_submap != bind_submap:
        return False
    ov_dsp = ov_match.get("dispatcher")
    if ov_dsp:
        bind_dsp = bind.dispatcher.path if bind.dispatcher else ""
        if not bind_dsp or not _dispatcher_matches(bind_dsp, str(ov_dsp)):
            return False
    return True


def match_override_to_disabled(ov_match: dict[str, Any], d: DisabledBindRecord) -> bool:
    """Check if an override match matches a DisabledBindRecord."""
    hint = getattr(d, "key_hint", "") or getattr(d, "original_text", "")
    if not hint:
        return False
    for pfx in ("-- HKS-DISABLED:", "# HKS-DISABLED:", "--", "#"):
        if hint.startswith(pfx):
            hint = hint[len(pfx):].strip()
    tokens = [t.strip() for t in re.split(r"[,+\s]+", hint) if t.strip()]
    if not tokens:
        return False
    d_key = tokens[-1].lower()
    ov_key = str(ov_match.get("key", "")).strip().lower()
    if d_key != ov_key:
        return False
    d_parsed = resolve_modifier_tokens(tokens[:-1])
    ov_parsed = resolve_modifier_tokens(ov_match.get("modifiers") or [])
    return d_parsed.modmask == ov_parsed.modmask


def validate_description_and_category(
    description: str | None,
    category: str | None,
) -> tuple[str | None, str | None]:
    """Validate description length/control characters and category enum."""
    clean_desc = None
    if description is not None:
        if not isinstance(description, str):
            raise SidecarStoreError("Description must be a string")
        if len(description) > 200:
            raise SidecarStoreError(
                f"Description exceeds maximum length of 200 characters ({len(description)} chars)"
            )
        if any(ord(c) < 32 for c in description):
            raise SidecarStoreError("Description must not contain control characters or newlines")
        clean_desc = description.strip()

    clean_cat = None
    if category is not None:
        if not isinstance(category, str):
            raise SidecarStoreError("Category must be a string")
        cat_str = category.strip()
        if cat_str not in VALID_CATEGORIES:
            raise SidecarStoreError(
                f"Invalid category '{cat_str}'. Must be one of: {', '.join(VALID_CATEGORIES)}"
            )
        clean_cat = cat_str

    return clean_desc, clean_cat


def backup_sidecar_file(
    sidecar_path: str,
    *,
    backup_dir: str | None = None,
    env: dict[str, str] | None = None,
) -> str | None:
    """Snapshot existing sidecar file into <backup_dir>/sidecar/, keeping last 20."""
    abs_path = os.path.abspath(os.path.expanduser(sidecar_path))
    if not os.path.isfile(abs_path):
        return None

    resolved_bdir = resolve_backup_dir(backup_dir=backup_dir, env=env)
    sidecar_bdir = os.path.join(resolved_bdir, "sidecar")
    os.makedirs(sidecar_bdir, exist_ok=True)

    with open(abs_path, "rb") as f:
        data = f.read()

    sha256 = hashlib.sha256(data).hexdigest()
    shorthash = sha256[:8]
    now = datetime.datetime.now(datetime.timezone.utc)
    ts_str = now.strftime("%Y%m%d-%H%M%S")
    snapshot_filename = f"descriptions_{ts_str}_{shorthash}.json"
    snapshot_path = os.path.join(sidecar_bdir, snapshot_filename)

    counter = 2
    while os.path.exists(snapshot_path):
        snapshot_filename = f"descriptions_{ts_str}_{shorthash}_{counter}.json"
        snapshot_path = os.path.join(sidecar_bdir, snapshot_filename)
        counter += 1

    with open(snapshot_path, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())

    # Prune: keep newest 20 snapshots
    try:
        entries = [
            os.path.join(sidecar_bdir, name)
            for name in os.listdir(sidecar_bdir)
            if name.startswith("descriptions_") and name.endswith(".json")
        ]
        entries.sort(key=lambda p: os.path.getmtime(p))
        if len(entries) > 20:
            for old_path in entries[:-20]:
                try:
                    os.unlink(old_path)
                except OSError:
                    pass
    except Exception:
        pass

    return snapshot_path


def _read_sidecar_raw(sidecar_path: str) -> dict[str, Any]:
    """Read sidecar JSON, validating integrity and preserving comments/unknown keys."""
    abs_path = os.path.abspath(os.path.expanduser(sidecar_path))
    if not os.path.isfile(abs_path):
        return {"version": 1, "overrides": []}

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as exc:
        raise SidecarStoreError(f"Cannot read sidecar file {abs_path}: {exc}") from exc

    if not content.strip():
        return {"version": 1, "overrides": []}

    try:
        data = json.loads(content)
    except Exception as exc:
        raise SidecarStoreError(
            f"Corrupt JSON in sidecar file {abs_path}: {exc}. Refusing to overwrite."
        ) from exc

    if not isinstance(data, dict):
        raise SidecarStoreError(
            f"Invalid sidecar file {abs_path}: root must be a JSON object. Refusing to overwrite."
        )

    from backend.describe.sidecar import validate_sidecar_data
    try:
        validate_sidecar_data(data)
    except Exception as exc:
        raise SidecarStoreError(
            f"Invalid sidecar file structure {abs_path}: {exc}. Refusing to overwrite."
        ) from exc

    return data


def _write_sidecar_atomic(
    sidecar_path: str,
    data: dict[str, Any],
) -> None:
    """Atomically write data to sidecar_path with fsync and os.replace."""
    abs_path = os.path.abspath(os.path.expanduser(sidecar_path))
    target_dir = os.path.dirname(abs_path)
    os.makedirs(target_dir, exist_ok=True)

    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    payload_bytes = payload.encode("utf-8")

    fd, tmp_path = tempfile.mkstemp(
        prefix=".descriptions.json.",
        suffix=".tmp",
        dir=target_dir,
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload_bytes)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, abs_path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


class SidecarLock:
    """Advisory file lock context manager using fcntl.flock on <sidecar_path>.lock."""

    def __init__(self, sidecar_path: str) -> None:
        self.sidecar_path = os.path.abspath(os.path.expanduser(sidecar_path))
        self.lock_path = self.sidecar_path + ".lock"
        self._fd: int | None = None

    def __enter__(self) -> SidecarLock:
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
        self._fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        fcntl.flock(self._fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = None


def save_override(
    sidecar_path: str,
    match: dict[str, Any],
    *,
    description: str | None = None,
    category: str | None = None,
    label: str | None = None,
    backup_dir: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Upsert one override entry into the sidecar file under lock."""
    norm_match = normalize_match_dict(match)
    clean_desc, clean_cat = validate_description_and_category(description, category)
    if clean_desc is None and clean_cat is None and label is None:
        raise SidecarStoreError("Must specify at least one of 'description' or 'category'")

    with SidecarLock(sidecar_path):
        data = _read_sidecar_raw(sidecar_path)
        snapshot_path = backup_sidecar_file(sidecar_path, backup_dir=backup_dir, env=env)

        overrides = data.setdefault("overrides", [])
        matched_idx = -1
        for idx, ov in enumerate(overrides):
            ov_m = ov.get("match")
            if isinstance(ov_m, dict) and matches_equal(ov_m, norm_match):
                matched_idx = idx
                break

        if matched_idx >= 0:
            target = overrides[matched_idx]
            if clean_desc is not None:
                target["description"] = clean_desc
            if clean_cat is not None:
                target["category"] = clean_cat
            if label is not None:
                target["label"] = label
        else:
            new_entry: dict[str, Any] = {"match": norm_match}
            if clean_desc is not None:
                new_entry["description"] = clean_desc
            if clean_cat is not None:
                new_entry["category"] = clean_cat
            if label is not None:
                new_entry["label"] = label
            overrides.append(new_entry)

        _write_sidecar_atomic(sidecar_path, data)

        return {
            "success": True,
            "match": norm_match,
            "description": clean_desc,
            "category": clean_cat,
            "backup_path": snapshot_path,
        }


def delete_override(
    sidecar_path: str,
    match: dict[str, Any],
    *,
    backup_dir: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Delete an override entry matching `match` under lock."""
    norm_match = normalize_match_dict(match)

    with SidecarLock(sidecar_path):
        data = _read_sidecar_raw(sidecar_path)
        overrides = data.get("overrides", [])
        matched_idx = -1
        for idx, ov in enumerate(overrides):
            ov_m = ov.get("match")
            if isinstance(ov_m, dict) and matches_equal(ov_m, norm_match):
                matched_idx = idx
                break

        if matched_idx < 0:
            return {"success": True, "deleted": False, "match": norm_match, "backup_path": None}

        snapshot_path = backup_sidecar_file(sidecar_path, backup_dir=backup_dir, env=env)
        overrides.pop(matched_idx)
        _write_sidecar_atomic(sidecar_path, data)

        return {
            "success": True,
            "deleted": True,
            "match": norm_match,
            "backup_path": snapshot_path,
        }


def migrate_override(
    sidecar_path: str,
    old_match: dict[str, Any],
    new_match: dict[str, Any],
    *,
    backup_dir: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Migrate an override from old_match to new_match. Refuses on collision."""
    norm_old = normalize_match_dict(old_match)
    norm_new = normalize_match_dict(new_match)

    with SidecarLock(sidecar_path):
        data = _read_sidecar_raw(sidecar_path)
        overrides = data.get("overrides", [])

        old_idx = -1
        for idx, ov in enumerate(overrides):
            ov_m = ov.get("match")
            if isinstance(ov_m, dict) and matches_equal(ov_m, norm_old):
                old_idx = idx
                break

        if old_idx < 0:
            return {
                "migrated": False,
                "found": False,
                "collision": False,
                "from": norm_old,
                "to": norm_new,
            }

        # Check collision with new_match
        for idx, ov in enumerate(overrides):
            if idx == old_idx:
                continue
            ov_m = ov.get("match")
            if isinstance(ov_m, dict) and matches_equal(ov_m, norm_new):
                return {
                    "migrated": False,
                    "found": True,
                    "collision": True,
                    "from": norm_old,
                    "to": norm_new,
                    "existing": ov,
                }

        snapshot_path = backup_sidecar_file(sidecar_path, backup_dir=backup_dir, env=env)
        target = overrides[old_idx]
        if isinstance(target.get("match"), dict) and "dispatcher" not in target["match"]:
            new_match_dict = dict(norm_new)
            new_match_dict.pop("dispatcher", None)
            target["match"] = new_match_dict
        else:
            target["match"] = norm_new
        _write_sidecar_atomic(sidecar_path, data)

        return {
            "migrated": True,
            "found": True,
            "collision": False,
            "from": norm_old,
            "to": norm_new,
            "backup_path": snapshot_path,
        }


def list_orphans(
    sidecar_path: str,
    active_binds: list[BindRecord],
    disabled_binds: list[DisabledBindRecord],
) -> list[dict[str, Any]]:
    """Return all sidecar overrides that match neither active nor disabled binds."""
    abs_path = os.path.abspath(os.path.expanduser(sidecar_path))
    if not os.path.isfile(abs_path):
        return []

    data = _read_sidecar_raw(sidecar_path)
    overrides = data.get("overrides", [])
    orphans: list[dict[str, Any]] = []

    for idx, ov in enumerate(overrides):
        ov_match = ov.get("match")
        if not isinstance(ov_match, dict):
            continue

        # Check active binds
        matched = False
        for b in active_binds:
            if match_override_to_bind(ov_match, b):
                matched = True
                break

        if not matched:
            # Check disabled binds
            for d in disabled_binds:
                if match_override_to_disabled(ov_match, d):
                    matched = True
                    break

        if not matched:
            orphans.append({
                "index": idx,
                "match": ov_match,
                "description": ov.get("description"),
                "category": ov.get("category"),
            })

    return orphans
