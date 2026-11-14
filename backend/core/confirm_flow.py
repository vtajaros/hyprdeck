"""Generic arm-before-apply / confirm / revert / watchdog transaction flow."""

from __future__ import annotations

import hashlib
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from backend.core import revert_guard
from backend.core.constants import OVERRIDES_FILENAME, SHA256_ABSENT
from backend.core.include_block import IncludeBlockError, has_include
from backend.core.overrides import OverridesError, remove_section, replace_section
from backend.core.revert_guard import (
    RevertGuardError,
    RevertGuardHandle,
    clear_active_handle,
    load_active_handle,
    resolve_state_dir,
    save_active_handle,
)
from backend.core.revert_watchdog import _append_log, _pid_alive
from backend.core.transaction import (
    VALID_RELOAD_MODES,
    TransactionResult,
    apply_managed_change,
    run_reload_and_check,
)
from backend.editor.backups import (
    BackupConflictError,
    BackupError,
    compute_file_sha256,
    create_backup,
    resolve_backup_dir,
    restore_backup,
)

DEFAULT_CONFIRM_TIMEOUT_SECONDS = 15.0


@dataclass(slots=True)
class ConfirmDomainValidation:
    """Result returned by a domain validator callback before transaction arming."""

    section_body: str | None = None
    section_updates: dict[str, str | None] | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: Any = None


@dataclass(slots=True)
class ConfirmFlowResult:
    """Result of apply_with_confirm_flow."""

    applied: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    diff: str = ""
    deadline_epoch: float = 0.0
    timeout_seconds: float = DEFAULT_CONFIRM_TIMEOUT_SECONDS
    handle: RevertGuardHandle | None = None
    transaction: TransactionResult | None = None
    metadata: Any = None


def _check_lua_include_installed(entrypoint: str) -> str | None:
    abs_entry = os.path.abspath(os.path.expanduser(entrypoint))
    if not abs_entry.lower().endswith(".lua"):
        return f"Settings overrides require a Lua (.lua) entrypoint, got: {abs_entry}"
    if not os.path.isfile(abs_entry):
        return f"Entrypoint does not exist: {abs_entry}"
    try:
        with open(abs_entry, "r", encoding="utf-8") as f:
            if not has_include(f.read()):
                return (
                    "Overrides include block is not installed in hyprland.lua. "
                    "Run `python3 -m backend.cli overrides install-include --apply --scan-sha256 <sha>` first."
                )
    except IncludeBlockError as exc:
        return f"Malformed include block in {abs_entry}: {exc}"
    return None


def _wait_pid_exit(pid: int, timeout_s: float = 0.6) -> None:
    if pid <= 1:
        return
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            waited_pid, _ = os.waitpid(pid, os.WNOHANG)
            if waited_pid == pid:
                return
        except ChildProcessError:
            pass
        if not _pid_alive(pid):
            return
        time.sleep(0.03)


def apply_with_confirm_flow(
    *,
    section_name: str,
    domain_validator: Callable[[str | None], ConfirmDomainValidation],
    config_dir: str,
    entrypoint: str,
    expected_sha256: str,
    reload_mode: str = "full",
    timeout_seconds: float = DEFAULT_CONFIRM_TIMEOUT_SECONDS,
    watch_pid: int | None = None,
    backup_dir: str | None = None,
    state_dir: str | None = None,
    env: dict[str, str] | None = None,
    hyprland_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    reload_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    dry_run: bool = False,
    apply_fn: Callable[..., TransactionResult] | None = None,
) -> ConfirmFlowResult:
    """Validate via `domain_validator`, arm revert_guard strictly before write, and apply."""
    if reload_mode not in VALID_RELOAD_MODES:
        return ConfirmFlowResult(
            applied=False,
            errors=[f"Invalid reload_mode: {reload_mode!r}"],
            timeout_seconds=float(timeout_seconds),
        )

    abs_config_dir = os.path.abspath(os.path.expanduser(config_dir))
    abs_entry = os.path.abspath(os.path.expanduser(entrypoint))
    ov_path = os.path.join(abs_config_dir, OVERRIDES_FILENAME)

    inc_err = _check_lua_include_installed(abs_entry)
    if inc_err is not None:
        return ConfirmFlowResult(
            applied=False,
            errors=[inc_err],
            timeout_seconds=float(timeout_seconds),
        )

    existing_text: str | None = None
    was_absent = not os.path.exists(ov_path)
    if not was_absent:
        if not os.path.isfile(ov_path):
            return ConfirmFlowResult(
                applied=False,
                errors=[f"Overrides path is not a regular file: {ov_path}"],
                timeout_seconds=float(timeout_seconds),
            )
        cur_sha = compute_file_sha256(ov_path)
        if cur_sha != expected_sha256:
            return ConfirmFlowResult(
                applied=False,
                errors=[
                    f"SHA-256 mismatch on {ov_path}: current {cur_sha} != expected {expected_sha256}."
                ],
                timeout_seconds=float(timeout_seconds),
            )
        with open(ov_path, "r", encoding="utf-8") as f:
            existing_text = f.read()
    else:
        if expected_sha256 != SHA256_ABSENT:
            return ConfirmFlowResult(
                applied=False,
                errors=[
                    f"Target file does not exist: {ov_path} "
                    f"(expected sha256 {expected_sha256!r}; pass {SHA256_ABSENT!r} to create)."
                ],
                timeout_seconds=float(timeout_seconds),
            )

    try:
        validation = domain_validator(existing_text)
    except OverridesError as exc:
        return ConfirmFlowResult(
            applied=False,
            errors=[f"Malformed overrides file: {exc}"],
            timeout_seconds=float(timeout_seconds),
        )

    if validation.errors:
        return ConfirmFlowResult(
            applied=False,
            errors=list(validation.errors),
            warnings=list(validation.warnings),
            timeout_seconds=float(timeout_seconds),
            metadata=validation.metadata,
        )

    doc = existing_text
    try:
        if validation.section_updates is not None:
            for sec_name, sec_body in validation.section_updates.items():
                if sec_body is None:
                    if doc is not None:
                        doc = remove_section(doc, sec_name)
                else:
                    doc = replace_section(doc, sec_name, sec_body)
            candidate_text = doc if doc is not None else ""
        elif validation.section_body is not None:
            candidate_text = replace_section(doc, section_name, validation.section_body)
        else:
            candidate_text = doc if doc is not None else ""
    except OverridesError as exc:
        return ConfirmFlowResult(
            applied=False,
            errors=[f"Malformed overrides file: {exc}"],
            warnings=list(validation.warnings),
            timeout_seconds=float(timeout_seconds),
            metadata=validation.metadata,
        )

    candidate_bytes = candidate_text.encode("utf-8")
    candidate_sha = hashlib.sha256(candidate_bytes).hexdigest()
    eff_apply = apply_fn if apply_fn is not None else apply_managed_change

    if dry_run:
        tx_dry = eff_apply(
            ov_path,
            candidate_bytes,
            expected_sha256=expected_sha256,
            config_dir=abs_config_dir,
            entrypoint=abs_entry,
            reload_mode=reload_mode,
            verify=True,
            require_binds_unchanged=True,
            backup_dir=backup_dir,
            env=env,
            hyprland_runner=hyprland_runner,
            reload_runner=reload_runner,
            sleep_fn=sleep_fn,
            dry_run=True,
        )
        return ConfirmFlowResult(
            applied=False,
            errors=list(tx_dry.errors),
            warnings=list(validation.warnings),
            diff=tx_dry.diff,
            timeout_seconds=float(timeout_seconds),
            transaction=tx_dry,
            metadata=validation.metadata,
        )

    resolved_bdir = resolve_backup_dir(backup_dir=backup_dir, env=env)
    resolved_sdir = resolve_state_dir(state_dir=state_dir, env=env)

    pre_backup = None
    if not was_absent:
        try:
            pre_backup = create_backup(
                ov_path,
                backup_dir=resolved_bdir,
                config_dir=abs_config_dir,
                env=env,
            )
        except BackupError as exc:
            return ConfirmFlowResult(
                applied=False,
                errors=[f"Failed to create pre-apply backup before arming guard: {exc}"],
                warnings=list(validation.warnings),
                timeout_seconds=float(timeout_seconds),
                metadata=validation.metadata,
            )

    try:
        handle = revert_guard.arm(
            plan={
                "backup_id": pre_backup.id if pre_backup is not None else None,
                "backup_dir": resolved_bdir,
                "target_path": ov_path,
                "expected_current_sha256": candidate_sha,
                "created": was_absent,
                "reload_mode": reload_mode,
            },
            timeout_seconds=timeout_seconds,
            watch_pid=watch_pid,
            state_dir=resolved_sdir,
            env=env,
        )
    except RevertGuardError as exc:
        return ConfirmFlowResult(
            applied=False,
            errors=[f"Revert guard failed to arm: {exc}"],
            warnings=list(validation.warnings),
            timeout_seconds=float(timeout_seconds),
            metadata=validation.metadata,
        )

    try:
        tx_res = eff_apply(
            ov_path,
            candidate_bytes,
            expected_sha256=expected_sha256,
            config_dir=abs_config_dir,
            entrypoint=abs_entry,
            reload_mode=reload_mode,
            verify=True,
            require_binds_unchanged=True,
            backup_dir=resolved_bdir,
            env=env,
            hyprland_runner=hyprland_runner,
            reload_runner=reload_runner,
            sleep_fn=sleep_fn,
            dry_run=False,
        )
    except Exception as exc:
        try:
            revert_guard.confirm(handle)
        except Exception:
            pass
        revert_guard.cancel(handle)
        clear_active_handle(state_dir=resolved_sdir, env=env)
        return ConfirmFlowResult(
            applied=False,
            errors=[f"Apply failed unexpectedly after arming guard: {exc}"],
            warnings=list(validation.warnings),
            timeout_seconds=float(timeout_seconds),
            metadata=validation.metadata,
        )

    if not tx_res.applied:
        try:
            revert_guard.confirm(handle)
        except Exception:
            pass
        revert_guard.cancel(handle)
        clear_active_handle(state_dir=resolved_sdir, env=env)
        return ConfirmFlowResult(
            applied=False,
            errors=list(tx_res.errors) or ["Transaction failed without specific error."],
            warnings=list(validation.warnings),
            diff=tx_res.diff,
            timeout_seconds=float(timeout_seconds),
            transaction=tx_res,
            metadata=validation.metadata,
        )

    deadline_epoch = time.time() + float(timeout_seconds)
    save_active_handle(
        handle,
        deadline_epoch=deadline_epoch,
        timeout_seconds=timeout_seconds,
        state_dir=resolved_sdir,
        env=env,
    )
    return ConfirmFlowResult(
        applied=True,
        errors=[],
        warnings=list(validation.warnings),
        diff=tx_res.diff,
        deadline_epoch=deadline_epoch,
        timeout_seconds=float(timeout_seconds),
        handle=handle,
        transaction=tx_res,
        metadata=validation.metadata,
    )


def confirm_flow_changes(
    *,
    handle: RevertGuardHandle | None = None,
    state_dir: str | None = None,
    env: Mapping[str, str] | None = None,
    label: str = "settings",
) -> dict[str, Any]:
    """Confirm pending guarded changes by signaling the watchdog's confirm_path."""
    eff_handle = handle
    if eff_handle is None:
        loaded = load_active_handle(state_dir=state_dir, env=env)
        if loaded is None:
            return {"ok": False, "confirmed": False, "error": f"No pending {label} guard to confirm."}
        eff_handle = loaded[0]

    revert_guard.confirm(eff_handle)
    clear_active_handle(state_dir=state_dir, env=env)
    _wait_pid_exit(eff_handle.pid, timeout_s=0.6)
    return {
        "ok": True,
        "confirmed": True,
        "plan_path": eff_handle.plan_path,
        "confirm_path": eff_handle.confirm_path,
    }


def revert_flow_changes(
    *,
    handle: RevertGuardHandle | None = None,
    state_dir: str | None = None,
    env: Mapping[str, str] | None = None,
    reload_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    default_reload_mode: str = "full",
    label: str = "settings",
) -> dict[str, Any]:
    """Immediately revert pending guarded changes and disarm the watchdog."""
    eff_handle = handle
    if eff_handle is None:
        loaded = load_active_handle(state_dir=state_dir, env=env)
        if loaded is None:
            return {"ok": False, "reverted": False, "error": f"No pending {label} guard to revert."}
        eff_handle = loaded[0]

    try:
        revert_guard.confirm(eff_handle)
    except Exception:
        pass
    revert_guard.cancel(eff_handle)
    _wait_pid_exit(eff_handle.pid, timeout_s=0.5)
    clear_active_handle(state_dir=state_dir, env=env)

    plan = eff_handle.plan
    target_path = str(plan.get("target_path") or "")
    expected_sha = str(plan.get("expected_current_sha256") or "")
    created = bool(plan.get("created", False))
    reload_mode = str(plan.get("reload_mode", default_reload_mode))
    backup_id = plan.get("backup_id")
    backup_dir = plan.get("backup_dir")
    log_path = eff_handle.log_path or plan.get("log_path")

    already_reverted = False
    if created:
        if os.path.exists(target_path):
            cur_sha = compute_file_sha256(target_path)
            if cur_sha != expected_sha:
                return {
                    "ok": False,
                    "reverted": False,
                    "error": f"Concurrent modification on {target_path} (sha {cur_sha} != {expected_sha}).",
                }
            os.unlink(target_path)
            _append_log(log_path, f"Explicitly reverted created file {target_path} (deleted).")
        else:
            already_reverted = True
    else:
        if not backup_id:
            return {"ok": False, "reverted": False, "error": f"Missing backup_id for {target_path}."}
        try:
            restore_backup(
                str(backup_id),
                expected_current_sha256=expected_sha,
                backup_dir=str(backup_dir) if backup_dir else None,
                env=dict(env) if env is not None else None,
            )
            _append_log(log_path, f"Explicitly reverted {target_path} to backup {backup_id}.")
        except BackupConflictError:
            already_reverted = True
        except BackupError as exc:
            return {"ok": False, "reverted": False, "error": f"Revert failed: {exc}"}

    if reload_mode != "none" and not already_reverted:
        ok, err = run_reload_and_check(
            reload_mode,
            reload_runner=reload_runner,
            sleep_fn=sleep_fn,
        )
        if not ok:
            return {
                "ok": False,
                "reverted": False,
                "error": f"File reverted, but reload ({reload_mode}) failed: {err}",
            }

    return {
        "ok": True,
        "reverted": True,
        "already_reverted": already_reverted,
        "target_path": target_path,
    }
