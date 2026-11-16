"""Settings Backups operations: enriched listing, capped diff, and safe atomic restore."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import os
import subprocess
import time
from typing import Any, Callable, Iterator, Mapping

from backend.discovery.config_discovery import discover_config
from backend.core.revert_guard import load_active_handle
from backend.core.transaction import run_reload_and_check
from backend.editor.backups import (
    BackupConflictError,
    BackupError,
    BackupRecord,
    compute_file_sha256,
    create_backup,
    enrich_backup_record,
    list_backups,
    resolve_backup_dir,
    resolve_backup_record_path,
    restore_backup,
)
from backend.editor.edit_plan import generate_unified_diff
from backend.editor.validator import stage_candidate_config, verify_with_hyprland
from backend.core.live_cmd import run_live_cmd
from backend.settings.power.ops import default_detached_spawner

MAX_DIFF_LINES = 400
MAX_DIFF_BYTES = 1024 * 1024  # 1 MiB


@contextlib.contextmanager
def _restore_lock(backup_dir: str) -> Iterator[None]:
    """Acquire non-blocking advisory lock on <backup_dir>/restore.lock."""
    os.makedirs(backup_dir, exist_ok=True)
    lock_path = os.path.join(backup_dir, "restore.lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise BackupConflictError(
                "Another backup restore is already in progress."
            ) from exc
        try:
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        os.close(fd)


def _find_record(
    backup_id: str,
    *,
    backup_dir: str | None = None,
    env: Mapping[str, str] | None = None,
) -> BackupRecord:
    env_dict = dict(env) if env is not None else None
    records = list_backups(backup_dir=backup_dir, env=env_dict)
    for rec in records:
        if rec.id == backup_id or rec.backup_path == backup_id:
            return rec
    raise BackupError(f"Backup record not found: {backup_id}")


def list_enriched_backups(
    path: str | None = None,
    *,
    backup_dir: str | None = None,
    env: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Return enriched backup records (with available, size, is_current, reason)."""
    env_dict = dict(env) if env is not None else None
    records = list_backups(path=path, backup_dir=backup_dir, env=env_dict)
    sha_cache: dict[str, str | None] = {}
    return [
        enrich_backup_record(
            rec,
            backup_dir=backup_dir,
            env=env_dict,
            current_sha_cache=sha_cache,
        )
        for rec in records
    ]


def diff_backup(
    backup_id: str,
    *,
    backup_dir: str | None = None,
    env: Mapping[str, str] | None = None,
    max_lines: int = MAX_DIFF_LINES,
    max_bytes: int = MAX_DIFF_BYTES,
) -> dict[str, Any]:
    """Compute unified diff between current file on disk and a backup snapshot."""
    env_dict = dict(env) if env is not None else None
    rec = _find_record(backup_id, backup_dir=backup_dir, env=env_dict)
    bak_path = resolve_backup_record_path(rec, backup_dir=backup_dir, env=env_dict)
    if not os.path.isfile(bak_path):
        return {
            "ok": False,
            "id": rec.id,
            "original_path": rec.original_path,
            "file_name": os.path.basename(rec.original_path),
            "error": f"Backup file is missing on disk: {bak_path}",
        }

    bak_size = os.path.getsize(bak_path)
    orig_exists = os.path.isfile(rec.original_path)
    orig_size = os.path.getsize(rec.original_path) if orig_exists else 0

    with open(bak_path, "rb") as bf:
        bak_bytes = bf.read()
    bak_sha = hashlib.sha256(bak_bytes).hexdigest()
    if bak_sha != rec.sha256:
        return {
            "ok": False,
            "id": rec.id,
            "original_path": rec.original_path,
            "file_name": os.path.basename(rec.original_path),
            "error": f"Backup integrity mismatch for {rec.id} (expected {rec.sha256}, got {bak_sha}).",
        }

    if orig_exists:
        with open(rec.original_path, "rb") as of:
            curr_bytes = of.read()
    else:
        curr_bytes = b""

    curr_text = curr_bytes.decode("utf-8", errors="replace")
    bak_text = bak_bytes.decode("utf-8", errors="replace")
    identical = curr_bytes == bak_bytes

    full_diff = generate_unified_diff(
        curr_text,
        bak_text,
        file_path=os.path.basename(rec.original_path),
    )
    diff_lines = full_diff.splitlines()
    added_lines = sum(
        1 for ln in diff_lines if ln.startswith("+") and not ln.startswith("+++")
    )
    removed_lines = sum(
        1 for ln in diff_lines if ln.startswith("-") and not ln.startswith("---")
    )

    if bak_size > max_bytes or orig_size > max_bytes:
        return {
            "ok": True,
            "id": rec.id,
            "original_path": rec.original_path,
            "file_name": os.path.basename(rec.original_path),
            "identical": identical,
            "stats_only": True,
            "truncated": True,
            "total_diff_lines": len(diff_lines),
            "added_lines": added_lines,
            "removed_lines": removed_lines,
            "backup_size": bak_size,
            "current_size": orig_size,
            "diff": "",
            "note": "File exceeds 1 MiB; showing diff stats only.",
        }

    truncated = len(diff_lines) > max_lines
    shown_lines = diff_lines[:max_lines] if truncated else diff_lines
    shown_diff = "\n".join(shown_lines) + ("\n" if shown_lines else "")

    return {
        "ok": True,
        "id": rec.id,
        "original_path": rec.original_path,
        "file_name": os.path.basename(rec.original_path),
        "identical": identical,
        "stats_only": False,
        "truncated": truncated,
        "total_diff_lines": len(diff_lines),
        "added_lines": added_lines,
        "removed_lines": removed_lines,
        "backup_size": bak_size,
        "current_size": orig_size,
        "diff": shown_diff,
        "note": (
            f"Diff truncated to first {max_lines} of {len(diff_lines)} lines."
            if truncated
            else ""
        ),
    }


def _restart_hypridle(
    *,
    live_cmd_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    spawn_fn: Callable[[list[str]], int] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[bool, str]:
    runner = live_cmd_runner or run_live_cmd
    spawner = spawn_fn or default_detached_spawner
    try:
        runner(["pkill", "-x", "hypridle"], timeout=5.0)
        sleep_fn(0.2)
        spawner(["hypridle"])
        sleep_fn(0.3)
        pg = runner(["pgrep", "-x", "hypridle"], timeout=5.0)
        if pg.returncode != 0 or not (pg.stdout or "").strip():
            return False, "hypridle did not stay running after restart."
        return True, "hypridle restarted"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Failed to restart hypridle: {exc}"


def _reload_for_file(
    file_path: str,
    *,
    reload_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    live_cmd_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    spawn_fn: Callable[[list[str]], int] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[bool, str, str]:
    """Run per-file reload. Returns (ok, reload_status, note)."""
    base = os.path.basename(file_path)
    if base in ("hyprland.lua", "hks-overrides.lua"):
        ok, err = run_reload_and_check(
            "config-only",
            reload_runner=reload_runner,
            sleep_fn=sleep_fn,
        )
        if not ok:
            return False, f"hyprctl reload failed: {err}", ""
        return True, "hyprctl reload config-only ok", ""
    if base == "hypridle.conf":
        ok, msg = _restart_hypridle(
            live_cmd_runner=live_cmd_runner,
            spawn_fn=spawn_fn,
            sleep_fn=sleep_fn,
        )
        return ok, msg, ""
    if base in ("qt6ct.conf", "settings.ini"):
        return True, "no-reload", "Apps may need restart to pick up GTK/Qt changes."
    return True, "no-reload", ""


def _collect_companion_warnings(
    rec: BackupRecord,
    *,
    backup_dir: str | None = None,
    env: dict[str, str] | None = None,
) -> list[str]:
    warnings: list[str] = []
    base = os.path.basename(rec.original_path)
    if base == "hyprland.lua":
        overrides = os.path.join(os.path.dirname(rec.original_path), "hks-overrides.lua")
        if os.path.isfile(overrides):
            warnings.append(
                "Companion file hks-overrides.lua was not modified; verify it remains compatible if needed."
            )
    if rec.sidecar_backup_path and rec.sidecar_original_path:
        if rec.sidecar_backup_path == "none":
            warnings.append(
                "Snapshot predates sidecar descriptions; sidecar file was removed to match."
            )
    elif base == "hyprland.lua":
        warnings.append(
            "Snapshot has no paired sidecar record; descriptions.json was left unchanged."
        )
    return warnings


def safe_restore_backup(
    backup_id: str,
    *,
    apply: bool = False,
    reload: bool = True,
    force: bool = False,
    expected_sha256: str | None = None,
    backup_dir: str | None = None,
    env: Mapping[str, str] | None = None,
    state_dir: str | None = None,
    config_dir: str | None = None,
    entrypoint: str | None = None,
    hyprland_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    reload_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    live_cmd_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    spawn_fn: Callable[[list[str]], int] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Validate and safely restore a backup with pre-restore snapshot and auto-rollback."""
    env_dict = dict(env) if env is not None else None
    resolved_bdir = resolve_backup_dir(backup_dir=backup_dir, env=env_dict)

    active = load_active_handle(state_dir=state_dir, env=env_dict)
    if active is not None:
        return {
            "ok": False,
            "applied": False,
            "rolled_back": False,
            "blocked_by": "revert_guard",
            "error": (
                "An active display revert-guard is pending. Confirm or revert it before restoring a backup."
            ),
        }

    try:
        lock_ctx: contextlib.AbstractContextManager[None] = (
            _restore_lock(resolved_bdir) if apply else contextlib.nullcontext()
        )
        with lock_ctx:
            rec = _find_record(backup_id, backup_dir=resolved_bdir, env=env_dict)
            bak_path = resolve_backup_record_path(rec, backup_dir=resolved_bdir, env=env_dict)
            if not os.path.isfile(bak_path):
                return {
                    "ok": False,
                    "applied": False,
                    "rolled_back": False,
                    "error": f"Backup file is missing on disk: {bak_path}",
                }

            with open(bak_path, "rb") as bf:
                bak_bytes = bf.read()
            actual_bak_sha = hashlib.sha256(bak_bytes).hexdigest()
            if actual_bak_sha != rec.sha256:
                return {
                    "ok": False,
                    "applied": False,
                    "rolled_back": False,
                    "error": (
                        f"Backup file integrity check failed for {rec.id}: "
                        f"expected {rec.sha256}, got {actual_bak_sha}."
                    ),
                }

            if not force and expected_sha256 is not None:
                if not os.path.isfile(rec.original_path):
                    return {
                        "ok": False,
                        "applied": False,
                        "rolled_back": False,
                        "error": f"Target file does not exist: {rec.original_path}",
                    }
                curr_sha = compute_file_sha256(rec.original_path)
                if curr_sha != expected_sha256:
                    return {
                        "ok": False,
                        "applied": False,
                        "rolled_back": False,
                        "error": (
                            f"Concurrent modification detected on {rec.original_path} "
                            f"(current {curr_sha} != expected {expected_sha256})."
                        ),
                    }

            base_name = os.path.basename(rec.original_path)
            verify_res_dict: dict[str, Any] | None = None
            if base_name in ("hyprland.lua", "hks-overrides.lua"):
                eff_cfg_dir = config_dir or os.path.dirname(rec.original_path)
                eff_entry = entrypoint
                if eff_entry is None:
                    candidate_entry = os.path.join(eff_cfg_dir, "hyprland.lua")
                    if os.path.isfile(candidate_entry):
                        eff_entry = candidate_entry
                    else:
                        disc = discover_config(
                            config_dir=eff_cfg_dir,
                            no_live=True,
                            env=env_dict,
                        )
                        eff_entry = disc.environment.entrypoint

                if (
                    eff_cfg_dir
                    and os.path.isdir(eff_cfg_dir)
                    and eff_entry
                    and os.path.isfile(eff_entry)
                ):
                    with stage_candidate_config(
                        config_dir=eff_cfg_dir,
                        entrypoint=eff_entry,
                        target_file=rec.original_path,
                        new_bytes=bak_bytes,
                    ) as (_, staged_entrypoint, _):
                        verify_res = verify_with_hyprland(
                            staged_entrypoint,
                            runner=hyprland_runner,
                        )
                        verify_res_dict = verify_res.to_dict()
                        if verify_res.ok is False:
                            return {
                                "ok": False,
                                "applied": False,
                                "rolled_back": False,
                                "verify": verify_res_dict,
                                "error": f"Candidate validation failed: {verify_res.message}",
                            }

            if not apply:
                diff_info = diff_backup(rec.id, backup_dir=resolved_bdir, env=env_dict)
                return {
                    "ok": True,
                    "applied": False,
                    "dry_run": True,
                    "rolled_back": False,
                    "id": rec.id,
                    "original_path": rec.original_path,
                    "file_name": base_name,
                    "verify": verify_res_dict,
                    "diff": diff_info.get("diff", ""),
                    "identical": diff_info.get("identical", False),
                    "warnings": _collect_companion_warnings(
                        rec, backup_dir=resolved_bdir, env=env_dict
                    ),
                }

            pre_snap: BackupRecord | None = None
            if os.path.isfile(rec.original_path):
                pre_snap = create_backup(
                    rec.original_path,
                    backup_dir=resolved_bdir,
                    config_dir=config_dir or os.path.dirname(rec.original_path),
                    env=env_dict,
                    sidecar_path=rec.sidecar_original_path,
                    reason="pre-restore",
                )

            restore_backup(
                rec,
                expected_current_sha256=expected_sha256,
                force=force,
                backup_dir=resolved_bdir,
                env=env_dict,
            )

            reload_status = "skipped"
            note = ""
            if reload:
                r_ok, r_status, r_note = _reload_for_file(
                    rec.original_path,
                    reload_runner=reload_runner,
                    live_cmd_runner=live_cmd_runner,
                    spawn_fn=spawn_fn,
                    sleep_fn=sleep_fn,
                )
                reload_status = r_status
                note = r_note
                if not r_ok:
                    if pre_snap is not None:
                        restore_backup(
                            pre_snap,
                            force=True,
                            backup_dir=resolved_bdir,
                            env=env_dict,
                        )
                        _reload_for_file(
                            rec.original_path,
                            reload_runner=reload_runner,
                            live_cmd_runner=live_cmd_runner,
                            spawn_fn=spawn_fn,
                            sleep_fn=sleep_fn,
                        )
                    return {
                        "ok": False,
                        "applied": False,
                        "rolled_back": pre_snap is not None,
                        "restored_id": rec.id,
                        "snapshot_id": pre_snap.id if pre_snap else None,
                        "original_path": rec.original_path,
                        "file_name": base_name,
                        "reload_status": r_status,
                        "error": f"Post-restore reload failed ({r_status}); rolled back automatically.",
                    }

            return {
                "ok": True,
                "applied": True,
                "rolled_back": False,
                "restored_id": rec.id,
                "snapshot_id": pre_snap.id if pre_snap else None,
                "original_path": rec.original_path,
                "file_name": base_name,
                "reload_status": reload_status,
                "note": note,
                "verify": verify_res_dict,
                "warnings": _collect_companion_warnings(
                    rec, backup_dir=resolved_bdir, env=env_dict
                ),
            }
    except (BackupError, BackupConflictError) as exc:
        return {
            "ok": False,
            "applied": False,
            "rolled_back": False,
            "error": str(exc),
        }
