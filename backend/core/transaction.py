"""Transactional file-change engine for HKS managed configuration files."""

from __future__ import annotations

import difflib
import hashlib
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.core.constants import OVERRIDES_FILENAME, SHA256_ABSENT
from backend.core.include_block import IncludeBlockError, insert_include, remove_include
from backend.core.overrides import create_overrides_text
from backend.editor.backups import (
    BackupConflictError,
    BackupError,
    BackupRecord,
    atomic_write_bytes,
    compute_file_sha256,
    create_backup,
    restore_backup,
)
from backend.editor.validator import (
    RecorderVerificationError,
    VerifyResult,
    compare_bind_sets,
    stage_candidate_config,
    verify_with_hyprland,
    verify_with_recorder,
)

VALID_RELOAD_MODES = ("none", "config-only", "full")


@dataclass(slots=True)
class TransactionResult:
    applied: bool
    rolled_back: bool
    created: bool
    backup: BackupRecord | None
    diff: str
    verify: VerifyResult | None
    errors: list[str] = field(default_factory=list)
    sha_before: str = ""
    sha_after: str = ""
    reload_mode: str = "config-only"
    target_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "rolled_back": self.rolled_back,
            "created": self.created,
            "backup": self.backup.to_dict() if self.backup is not None else None,
            "diff": self.diff,
            "verify": self.verify.to_dict() if self.verify is not None else None,
            "errors": list(self.errors),
            "sha_before": self.sha_before,
            "sha_after": self.sha_after,
            "reload_mode": self.reload_mode,
            "target_path": self.target_path,
        }


def run_reload_and_check(
    reload_mode: str,
    *,
    reload_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    timeout: float = 10.0,
) -> tuple[bool, str]:
    """Run hyprctl reload for `reload_mode` and verify `hyprctl configerrors` is empty."""
    if reload_mode not in VALID_RELOAD_MODES:
        return False, f"Invalid reload_mode: {reload_mode!r}"
    if reload_mode == "none":
        return True, ""

    run_fn = reload_runner if reload_runner is not None else subprocess.run
    argv = (
        ["hyprctl", "reload", "config-only"]
        if reload_mode == "config-only"
        else ["hyprctl", "reload"]
    )
    cmd_label = " ".join(argv)

    try:
        reload_proc = run_fn(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Failed to run `{cmd_label}`: {exc}"

    if reload_proc.returncode != 0:
        detail = (reload_proc.stderr or reload_proc.stdout or "").strip()
        return False, f"`{cmd_label}` exited with {reload_proc.returncode}: {detail}"

    sleep_fn(1.0)

    try:
        err_proc = run_fn(
            ["hyprctl", "configerrors"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Failed to run `hyprctl configerrors`: {exc}"

    if err_proc.returncode != 0:
        detail = (err_proc.stderr or err_proc.stdout or "").strip()
        return False, f"`hyprctl configerrors` exited with {err_proc.returncode}: {detail}"

    err_lines = [ln.strip() for ln in (err_proc.stdout or "").splitlines() if ln.strip()]
    if err_lines:
        return False, "; ".join(err_lines)

    return True, ""


def _build_diff(original_bytes: bytes, new_bytes: bytes, label: str) -> str:
    old_lines = original_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)
    new_lines = new_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{label}", tofile=f"b/{label}")
    )


def _rollback_write(
    abs_target: str,
    was_absent: bool,
    backup_rec: BackupRecord | None,
    *,
    backup_dir: str | None,
    env: dict[str, str] | None,
) -> None:
    if was_absent:
        if os.path.exists(abs_target):
            os.unlink(abs_target)
    elif backup_rec is not None:
        restore_backup(backup_rec, force=True, backup_dir=backup_dir, env=env)


def apply_managed_change(
    target_path: str,
    new_bytes: bytes,
    *,
    expected_sha256: str,
    config_dir: str,
    entrypoint: str,
    reload_mode: str = "config-only",
    verify: bool = True,
    require_binds_unchanged: bool = True,
    backup_dir: str | None = None,
    env: dict[str, str] | None = None,
    hyprland_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    reload_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    dry_run: bool = True,
) -> TransactionResult:
    """Safely verify, back up, atomically write, and reload a managed config file change."""
    if reload_mode not in VALID_RELOAD_MODES:
        raise ValueError(f"reload_mode must be one of {VALID_RELOAD_MODES}, got {reload_mode!r}")

    abs_config_dir = os.path.abspath(os.path.expanduser(config_dir))
    abs_entrypoint = os.path.abspath(os.path.expanduser(entrypoint))
    abs_target = os.path.abspath(os.path.expanduser(target_path))

    # a. Read target and verify expected_sha256
    if not os.path.exists(abs_target):
        if expected_sha256 != SHA256_ABSENT:
            return TransactionResult(
                applied=False,
                rolled_back=False,
                created=False,
                backup=None,
                diff="",
                verify=None,
                errors=[
                    f"Target file does not exist: {abs_target} "
                    f"(expected sha256 {expected_sha256!r}; pass {SHA256_ABSENT!r} to create)."
                ],
                sha_before=SHA256_ABSENT,
                sha_after=SHA256_ABSENT,
                reload_mode=reload_mode,
                target_path=abs_target,
            )
        original_bytes = b""
        sha_before = SHA256_ABSENT
        was_absent = True
    else:
        if not os.path.isfile(abs_target):
            return TransactionResult(
                applied=False,
                rolled_back=False,
                created=False,
                backup=None,
                diff="",
                verify=None,
                errors=[f"Target path is not a regular file: {abs_target}"],
                reload_mode=reload_mode,
                target_path=abs_target,
            )
        with open(abs_target, "rb") as f:
            original_bytes = f.read()
        sha_before = hashlib.sha256(original_bytes).hexdigest()
        if sha_before != expected_sha256:
            return TransactionResult(
                applied=False,
                rolled_back=False,
                created=False,
                backup=None,
                diff="",
                verify=None,
                errors=[
                    f"SHA-256 mismatch on {abs_target}: "
                    f"current {sha_before} != expected {expected_sha256}."
                ],
                sha_before=sha_before,
                sha_after=sha_before,
                reload_mode=reload_mode,
                target_path=abs_target,
            )
        was_absent = False

    try:
        rel_label = os.path.relpath(abs_target, abs_config_dir)
        if rel_label.startswith(".."):
            rel_label = os.path.basename(abs_target)
    except ValueError:
        rel_label = os.path.basename(abs_target)

    diff = _build_diff(original_bytes, new_bytes, rel_label)

    # b. Stage candidate tree and verify
    verify_res: VerifyResult | None = None
    if verify or require_binds_unchanged:
        before_binds = None
        if require_binds_unchanged:
            try:
                before_binds = verify_with_recorder(abs_entrypoint, abs_config_dir, env=env)
            except RecorderVerificationError as exc:
                return TransactionResult(
                    applied=False,
                    rolled_back=False,
                    created=was_absent,
                    backup=None,
                    diff=diff,
                    verify=None,
                    errors=[f"Baseline config failed recorder check: {exc}"],
                    sha_before=sha_before,
                    sha_after=sha_before,
                    reload_mode=reload_mode,
                    target_path=abs_target,
                )

        with stage_candidate_config(
            config_dir=abs_config_dir,
            entrypoint=abs_entrypoint,
            target_file=abs_target,
            new_bytes=new_bytes,
        ) as (staged_dir, staged_entrypoint, _):
            if verify:
                verify_res = verify_with_hyprland(staged_entrypoint, runner=hyprland_runner)
                if verify_res.ok is False:
                    return TransactionResult(
                        applied=False,
                        rolled_back=False,
                        created=was_absent,
                        backup=None,
                        diff=diff,
                        verify=verify_res,
                        errors=[f"Hyprland verification failed: {verify_res.message}"],
                        sha_before=sha_before,
                        sha_after=sha_before,
                        reload_mode=reload_mode,
                        target_path=abs_target,
                    )

            if require_binds_unchanged and before_binds is not None:
                try:
                    after_binds = verify_with_recorder(staged_entrypoint, staged_dir, env=env)
                except RecorderVerificationError as exc:
                    return TransactionResult(
                        applied=False,
                        rolled_back=False,
                        created=was_absent,
                        backup=None,
                        diff=diff,
                        verify=verify_res,
                        errors=[f"Recorder verification failed: {exc}"],
                        sha_before=sha_before,
                        sha_after=sha_before,
                        reload_mode=reload_mode,
                        target_path=abs_target,
                    )

                bind_cmp = compare_bind_sets(
                    before_binds=before_binds,
                    after_binds=after_binds,
                    ops=[],
                    before_dir=abs_config_dir,
                    after_dir=staged_dir,
                )
                if not bind_cmp.ok:
                    return TransactionResult(
                        applied=False,
                        rolled_back=False,
                        created=was_absent,
                        backup=None,
                        diff=diff,
                        verify=verify_res,
                        errors=[f"Bind-set comparison failed: {bind_cmp.message}"],
                        sha_before=sha_before,
                        sha_after=sha_before,
                        reload_mode=reload_mode,
                        target_path=abs_target,
                    )

    if dry_run:
        return TransactionResult(
            applied=False,
            rolled_back=False,
            created=was_absent,
            backup=None,
            diff=diff,
            verify=verify_res,
            errors=[],
            sha_before=sha_before,
            sha_after=sha_before,
            reload_mode=reload_mode,
            target_path=abs_target,
        )

    # c. Re-check target SHA immediately before write (TOCTOU)
    if was_absent:
        if os.path.exists(abs_target):
            return TransactionResult(
                applied=False,
                rolled_back=False,
                created=True,
                backup=None,
                diff=diff,
                verify=verify_res,
                errors=[f"Concurrent creation detected at {abs_target} during verification."],
                sha_before=sha_before,
                sha_after=sha_before,
                reload_mode=reload_mode,
                target_path=abs_target,
            )
        backup_rec: BackupRecord | None = None
    else:
        if not os.path.isfile(abs_target) or compute_file_sha256(abs_target) != sha_before:
            return TransactionResult(
                applied=False,
                rolled_back=False,
                created=False,
                backup=None,
                diff=diff,
                verify=verify_res,
                errors=[f"Concurrent modification detected on {abs_target} during verification."],
                sha_before=sha_before,
                sha_after=sha_before,
                reload_mode=reload_mode,
                target_path=abs_target,
            )
        backup_rec = create_backup(
            abs_target,
            backup_dir=backup_dir,
            config_dir=abs_config_dir,
            env=env,
        )

    # d. Atomic write + post-write SHA check
    atomic_write_bytes(
        abs_target,
        new_bytes,
        mode_source=backup_rec.backup_path if backup_rec is not None else None,
    )

    expected_new_sha = hashlib.sha256(new_bytes).hexdigest()
    actual_new_sha = compute_file_sha256(abs_target)
    if actual_new_sha != expected_new_sha:
        _rollback_write(abs_target, was_absent, backup_rec, backup_dir=backup_dir, env=env)
        return TransactionResult(
            applied=False,
            rolled_back=True,
            created=was_absent,
            backup=backup_rec,
            diff=diff,
            verify=verify_res,
            errors=[
                f"Post-write SHA-256 verification failed "
                f"(expected {expected_new_sha}, got {actual_new_sha}); rolled back."
            ],
            sha_before=sha_before,
            sha_after=sha_before,
            reload_mode=reload_mode,
            target_path=abs_target,
        )

    # e. Reload + configerrors check
    if reload_mode != "none":
        reload_ok, reload_err = run_reload_and_check(
            reload_mode,
            reload_runner=reload_runner,
            sleep_fn=sleep_fn,
        )
        if not reload_ok:
            _rollback_write(abs_target, was_absent, backup_rec, backup_dir=backup_dir, env=env)
            re_ok, re_err = run_reload_and_check(
                reload_mode,
                reload_runner=reload_runner,
                sleep_fn=sleep_fn,
            )
            extra = "" if re_ok else f" (rollback reload also reported: {re_err})"
            return TransactionResult(
                applied=False,
                rolled_back=True,
                created=was_absent,
                backup=backup_rec,
                diff=diff,
                verify=verify_res,
                errors=[f"Live reload failed ({reload_err}); rolled back.{extra}"],
                sha_before=sha_before,
                sha_after=sha_before,
                reload_mode=reload_mode,
                target_path=abs_target,
            )

    return TransactionResult(
        applied=True,
        rolled_back=False,
        created=was_absent,
        backup=backup_rec,
        diff=diff,
        verify=verify_res,
        errors=[],
        sha_before=sha_before,
        sha_after=actual_new_sha,
        reload_mode=reload_mode,
        target_path=abs_target,
    )


def undo_managed_change(
    result: TransactionResult,
    *,
    backup_dir: str | None = None,
    env: dict[str, str] | None = None,
    reload_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> TransactionResult:
    """Undo a previously applied TransactionResult with an expected-current-SHA precondition."""
    if not result.applied:
        return TransactionResult(
            applied=False,
            rolled_back=False,
            created=result.created,
            backup=result.backup,
            diff="",
            verify=None,
            errors=["Cannot undo a transaction that was not applied."],
            sha_before=result.sha_after,
            sha_after=result.sha_after,
            reload_mode=result.reload_mode,
            target_path=result.target_path,
        )

    abs_target = os.path.abspath(os.path.expanduser(result.target_path))
    if result.created:
        if not os.path.isfile(abs_target):
            return TransactionResult(
                applied=False,
                rolled_back=False,
                created=True,
                backup=None,
                diff="",
                verify=None,
                errors=[f"Cannot undo created file; target does not exist: {abs_target}"],
                sha_before=SHA256_ABSENT,
                sha_after=SHA256_ABSENT,
                reload_mode=result.reload_mode,
                target_path=abs_target,
            )
        cur_sha = compute_file_sha256(abs_target)
        if cur_sha != result.sha_after:
            return TransactionResult(
                applied=False,
                rolled_back=False,
                created=True,
                backup=None,
                diff="",
                verify=None,
                errors=[
                    f"Refusing to delete {abs_target}: current sha256 {cur_sha} "
                    f"!= expected {result.sha_after}."
                ],
                sha_before=cur_sha,
                sha_after=cur_sha,
                reload_mode=result.reload_mode,
                target_path=abs_target,
            )
        os.unlink(abs_target)
    else:
        if result.backup is None:
            return TransactionResult(
                applied=False,
                rolled_back=False,
                created=False,
                backup=None,
                diff="",
                verify=None,
                errors=["Cannot undo change without a BackupRecord."],
                sha_before=result.sha_after,
                sha_after=result.sha_after,
                reload_mode=result.reload_mode,
                target_path=abs_target,
            )
        try:
            restore_backup(
                result.backup,
                expected_current_sha256=result.sha_after,
                backup_dir=backup_dir,
                env=env,
            )
        except (BackupConflictError, BackupError) as exc:
            return TransactionResult(
                applied=False,
                rolled_back=False,
                created=False,
                backup=result.backup,
                diff="",
                verify=None,
                errors=[str(exc)],
                sha_before=result.sha_after,
                sha_after=result.sha_after,
                reload_mode=result.reload_mode,
                target_path=abs_target,
            )

    if result.reload_mode != "none":
        ok, err = run_reload_and_check(
            result.reload_mode,
            reload_runner=reload_runner,
            sleep_fn=sleep_fn,
        )
        if not ok:
            return TransactionResult(
                applied=False,
                rolled_back=False,
                created=result.created,
                backup=result.backup,
                diff="",
                verify=None,
                errors=[f"Undo restored file, but reload failed: {err}"],
                sha_before=result.sha_after,
                sha_after=result.sha_before,
                reload_mode=result.reload_mode,
                target_path=abs_target,
            )

    return TransactionResult(
        applied=True,
        rolled_back=False,
        created=result.created,
        backup=result.backup,
        diff="",
        verify=None,
        errors=[],
        sha_before=result.sha_after,
        sha_after=result.sha_before,
        reload_mode=result.reload_mode,
        target_path=abs_target,
    )


def _ensure_lua_entrypoint(abs_entrypoint: str) -> str | None:
    if not abs_entrypoint.lower().endswith(".lua"):
        return f"Overrides include requires a Lua (.lua) entrypoint, got: {abs_entrypoint}"
    if not os.path.isfile(abs_entrypoint):
        return f"Entrypoint does not exist: {abs_entrypoint}"
    return None


def install_include(
    config_dir: str,
    entrypoint: str,
    *,
    expected_sha256: str | None = None,
    reload_mode: str = "config-only",
    verify: bool = True,
    backup_dir: str | None = None,
    env: dict[str, str] | None = None,
    hyprland_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    reload_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    dry_run: bool = True,
    create_overrides_if_absent: bool = True,
) -> TransactionResult:
    """Install the HKS overrides include block into a Lua entrypoint (and create overrides file if absent)."""
    abs_config_dir = os.path.abspath(os.path.expanduser(config_dir))
    abs_entrypoint = os.path.abspath(os.path.expanduser(entrypoint))
    err = _ensure_lua_entrypoint(abs_entrypoint)
    if err is not None:
        return TransactionResult(
            applied=False,
            rolled_back=False,
            created=False,
            backup=None,
            diff="",
            verify=None,
            errors=[err],
            reload_mode=reload_mode,
            target_path=abs_entrypoint,
        )

    with open(abs_entrypoint, "rb") as f:
        orig_bytes = f.read()
    sha_now = hashlib.sha256(orig_bytes).hexdigest()
    eff_sha = expected_sha256 if expected_sha256 is not None else sha_now

    try:
        new_text = insert_include(orig_bytes.decode("utf-8"))
    except IncludeBlockError as exc:
        return TransactionResult(
            applied=False,
            rolled_back=False,
            created=False,
            backup=None,
            diff="",
            verify=None,
            errors=[str(exc)],
            sha_before=sha_now,
            sha_after=sha_now,
            reload_mode=reload_mode,
            target_path=abs_entrypoint,
        )

    if create_overrides_if_absent and not dry_run:
        overrides_path = os.path.join(abs_config_dir, OVERRIDES_FILENAME)
        if not os.path.exists(overrides_path):
            ov_res = apply_managed_change(
                overrides_path,
                create_overrides_text().encode("utf-8"),
                expected_sha256=SHA256_ABSENT,
                config_dir=abs_config_dir,
                entrypoint=abs_entrypoint,
                reload_mode="none",
                verify=verify,
                require_binds_unchanged=True,
                backup_dir=backup_dir,
                env=env,
                hyprland_runner=hyprland_runner,
                reload_runner=reload_runner,
                sleep_fn=sleep_fn,
                dry_run=False,
            )
            if not ov_res.applied:
                return ov_res

    return apply_managed_change(
        abs_entrypoint,
        new_text.encode("utf-8"),
        expected_sha256=eff_sha,
        config_dir=abs_config_dir,
        entrypoint=abs_entrypoint,
        reload_mode=reload_mode,
        verify=verify,
        require_binds_unchanged=True,
        backup_dir=backup_dir,
        env=env,
        hyprland_runner=hyprland_runner,
        reload_runner=reload_runner,
        sleep_fn=sleep_fn,
        dry_run=dry_run,
    )


def uninstall_include(
    config_dir: str,
    entrypoint: str,
    *,
    expected_sha256: str | None = None,
    reload_mode: str = "config-only",
    verify: bool = True,
    backup_dir: str | None = None,
    env: dict[str, str] | None = None,
    hyprland_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    reload_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    dry_run: bool = True,
) -> TransactionResult:
    """Remove the HKS overrides include block from a Lua entrypoint."""
    abs_config_dir = os.path.abspath(os.path.expanduser(config_dir))
    abs_entrypoint = os.path.abspath(os.path.expanduser(entrypoint))
    err = _ensure_lua_entrypoint(abs_entrypoint)
    if err is not None:
        return TransactionResult(
            applied=False,
            rolled_back=False,
            created=False,
            backup=None,
            diff="",
            verify=None,
            errors=[err],
            reload_mode=reload_mode,
            target_path=abs_entrypoint,
        )

    with open(abs_entrypoint, "rb") as f:
        orig_bytes = f.read()
    sha_now = hashlib.sha256(orig_bytes).hexdigest()
    eff_sha = expected_sha256 if expected_sha256 is not None else sha_now

    try:
        new_text = remove_include(orig_bytes.decode("utf-8"))
    except IncludeBlockError as exc:
        return TransactionResult(
            applied=False,
            rolled_back=False,
            created=False,
            backup=None,
            diff="",
            verify=None,
            errors=[str(exc)],
            sha_before=sha_now,
            sha_after=sha_now,
            reload_mode=reload_mode,
            target_path=abs_entrypoint,
        )

    return apply_managed_change(
        abs_entrypoint,
        new_text.encode("utf-8"),
        expected_sha256=eff_sha,
        config_dir=abs_config_dir,
        entrypoint=abs_entrypoint,
        reload_mode=reload_mode,
        verify=verify,
        require_binds_unchanged=True,
        backup_dir=backup_dir,
        env=env,
        hyprland_runner=hyprland_runner,
        reload_runner=reload_runner,
        sleep_fn=sleep_fn,
        dry_run=dry_run,
    )
