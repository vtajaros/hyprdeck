"""Safe edit pipeline with multi-layer verification, atomic write, and auto-rollback."""

from __future__ import annotations

import hashlib
import os
import subprocess
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.editor.backups import (
    BackupRecord,
    atomic_write_bytes,
    compute_file_sha256,
    create_backup,
    restore_backup,
)
from backend.editor.edit_plan import (
    HYPRLANG_DISABLED_PREFIX,
    LUA_DISABLED_PREFIX,
    EditOp,
    NotEditableError,
    apply_ops_to_text,
    generate_unified_diff,
)
from backend.editor.validator import (
    BindSetComparison,
    RecorderVerificationError,
    VerifyResult,
    compare_bind_sets,
    stage_candidate_config,
    verify_with_hyprland,
    verify_with_recorder,
)
from backend.models.types import BindRecord
from backend.parser import compute_bind_id, parse_hyprlang_config, parse_lua_config
from backend.validation.oracle import bind_record_to_tuple


@dataclass(slots=True)
class ApplyResult:
    applied: bool
    rolled_back: bool
    backup: BackupRecord | None
    diff: str
    verify: VerifyResult | None
    errors: list[str] = field(default_factory=list)
    bind_comparison: BindSetComparison | None = None
    companion_warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "backup": self.backup.to_dict() if self.backup else None,
            "bind_comparison": self.bind_comparison.to_dict() if self.bind_comparison else None,
            "companion_warning": self.companion_warning,
            "diff": self.diff,
            "errors": list(self.errors),
            "rolled_back": self.rolled_back,
            "verify": self.verify.to_dict() if self.verify else None,
        }


def _check_companion_parity(
    config_dir: str,
    entrypoint: str,
    after_binds: list[BindRecord],
    env: dict[str, str] | None = None,
) -> str | None:
    """Check if a companion .conf / .lua file exists in config_dir and is now out of sync."""
    abs_dir = os.path.abspath(os.path.expanduser(config_dir))
    abs_entry = os.path.abspath(os.path.expanduser(entrypoint))
    entry_base = os.path.basename(abs_entry)

    companion_path: str | None = None
    if entry_base == "hyprland.lua":
        cand = os.path.join(abs_dir, "hyprland.conf")
        if os.path.isfile(cand):
            companion_path = cand
    elif entry_base == "hyprland.conf":
        cand = os.path.join(abs_dir, "hyprland.lua")
        if os.path.isfile(cand):
            companion_path = cand

    if companion_path is None:
        return None

    try:
        if companion_path.endswith(".lua"):
            comp_binds, _, _, _, _ = parse_lua_config(
                entrypoint=companion_path,
                config_dir=abs_dir,
                env=env,
            )
        else:
            comp_binds, _, _, _, _, _ = parse_hyprlang_config(
                entrypoint=companion_path,
            )
    except Exception:
        return (
            f"Companion file {companion_path} exists and may be out of sync with "
            f"{entry_base} (not modified)."
        )

    def _cross_lang_sig(b: BindRecord) -> tuple[Any, ...]:
        return (
            b.submap or "",
            int(b.modmask),
            b.key.lower(),
            bool(b.flags.get("locked", False)),
            bool(b.flags.get("repeating", False)),
            bool(b.flags.get("release", False)),
            b.description_effective.text,
            b.category,
        )

    after_tuples = Counter(_cross_lang_sig(b) for b in after_binds)
    comp_tuples = Counter(_cross_lang_sig(b) for b in comp_binds)
    if after_tuples != comp_tuples:
        missing_in_comp = sum((after_tuples - comp_tuples).values())
        extra_in_comp = sum((comp_tuples - after_tuples).values())
        return (
            f"Companion file {companion_path} is now out of sync with {entry_base} "
            f"({entry_base}={len(after_binds)} binds vs {os.path.basename(companion_path)}={len(comp_binds)} binds; "
            f"delta: +{missing_in_comp}/-{extra_in_comp}). Companion file was not modified."
        )
    return None


def _run_live_reload_and_check(
    reload_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    timeout: float = 10.0,
) -> tuple[bool, str]:
    """Run `hyprctl reload config-only`, sleep 1s, then check `hyprctl configerrors`."""
    run_fn = reload_runner if reload_runner is not None else subprocess.run

    try:
        reload_proc = run_fn(
            ["hyprctl", "reload", "config-only"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Failed to run `hyprctl reload config-only`: {exc}"

    if reload_proc.returncode != 0:
        detail = (reload_proc.stderr or reload_proc.stdout or "").strip()
        return False, f"`hyprctl reload config-only` exited with {reload_proc.returncode}: {detail}"

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


def apply_edit(
    ops: list[EditOp],
    config_dir: str,
    entrypoint: str,
    *,
    dry_run: bool = True,
    reload: bool = False,
    scan_sha256: str | dict[str, str] | None = None,
    before_binds: list[BindRecord] | None = None,
    hyprland_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    reload_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    backup_dir: str | None = None,
    env: dict[str, str] | None = None,
) -> ApplyResult:
    """Execute the full Phase 4a edit verification, backup, atomic apply, and rollback pipeline."""
    if not ops:
        raise ValueError("apply_edit requires at least one EditOp")

    abs_config_dir = os.path.abspath(os.path.expanduser(config_dir))
    abs_entrypoint = os.path.abspath(os.path.expanduser(entrypoint))

    target_files = {os.path.abspath(os.path.expanduser(op.file)) for op in ops}
    if len(target_files) > 1:
        raise ValueError("All EditOps in a single apply_edit call must target the same file")
    target_file = next(iter(target_files))

    if not os.path.isfile(target_file):
        return ApplyResult(
            applied=False,
            rolled_back=False,
            backup=None,
            diff="",
            verify=None,
            errors=[f"Target file does not exist: {target_file}"],
        )

    with open(target_file, "rb") as f:
        original_bytes = f.read()
    current_sha256 = hashlib.sha256(original_bytes).hexdigest()

    # Check concurrent modification against scan_sha256 if provided
    expected_sha: str | None = None
    if isinstance(scan_sha256, str):
        expected_sha = scan_sha256
    elif isinstance(scan_sha256, dict):
        expected_sha = scan_sha256.get(target_file) or scan_sha256.get(op.file)

    if expected_sha is not None and current_sha256 != expected_sha:
        return ApplyResult(
            applied=False,
            rolled_back=False,
            backup=None,
            diff="",
            verify=None,
            errors=[
                f"Concurrent edit detected on {target_file}: "
                f"current sha256 {current_sha256} does not match scan sha256 {expected_sha}."
            ],
        )

    original_text = original_bytes.decode("utf-8")

    # Apply ops in memory (may raise NotEditableError or EditConflict)
    new_text = apply_ops_to_text(original_text, ops)
    new_bytes = new_text.encode("utf-8")

    try:
        rel_label = os.path.relpath(target_file, abs_config_dir)
        if rel_label.startswith(".."):
            rel_label = os.path.basename(target_file)
    except ValueError:
        rel_label = os.path.basename(target_file)

    diff = generate_unified_diff(original_text, new_text, file_path=rel_label)

    # Parse baseline binds if not pre-supplied
    if before_binds is None:
        try:
            before_binds = verify_with_recorder(abs_entrypoint, abs_config_dir, env=env)
        except RecorderVerificationError as exc:
            return ApplyResult(
                applied=False,
                rolled_back=False,
                backup=None,
                diff=diff,
                verify=None,
                errors=[f"Baseline config failed recorder check: {exc}"],
            )

    # Stage candidate in temp dir and run Layer 1 (Hyprland) + Layer 2 (Recorder) + Layer 3 (Bind-set diff)
    with stage_candidate_config(
        config_dir=abs_config_dir,
        entrypoint=abs_entrypoint,
        target_file=target_file,
        new_bytes=new_bytes,
    ) as (staged_dir, staged_entrypoint, _):
        verify_res = verify_with_hyprland(staged_entrypoint, runner=hyprland_runner)
        if verify_res.ok is False:
            return ApplyResult(
                applied=False,
                rolled_back=False,
                backup=None,
                diff=diff,
                verify=verify_res,
                errors=[f"Hyprland verification failed: {verify_res.message}"],
            )

        try:
            after_binds = verify_with_recorder(staged_entrypoint, staged_dir, env=env)
        except RecorderVerificationError as exc:
            return ApplyResult(
                applied=False,
                rolled_back=False,
                backup=None,
                diff=diff,
                verify=verify_res,
                errors=[f"Recorder verification failed: {exc}"],
            )

        bind_cmp = compare_bind_sets(
            before_binds=before_binds,
            after_binds=after_binds,
            ops=ops,
            before_dir=abs_config_dir,
            after_dir=staged_dir,
        )
        if not bind_cmp.ok:
            return ApplyResult(
                applied=False,
                rolled_back=False,
                backup=None,
                diff=diff,
                verify=verify_res,
                errors=[f"Bind-set comparison failed: {bind_cmp.message}"],
                bind_comparison=bind_cmp,
            )

    companion_warning = _check_companion_parity(
        config_dir=abs_config_dir,
        entrypoint=abs_entrypoint,
        after_binds=after_binds,
        env=env,
    )

    if dry_run:
        return ApplyResult(
            applied=False,
            rolled_back=False,
            backup=None,
            diff=diff,
            verify=verify_res,
            errors=[],
            bind_comparison=bind_cmp,
            companion_warning=companion_warning,
        )

    # Re-verify target file hash right before backup + write to prevent TOCTOU race
    if compute_file_sha256(target_file) != current_sha256:
        return ApplyResult(
            applied=False,
            rolled_back=False,
            backup=None,
            diff=diff,
            verify=verify_res,
            errors=[f"Concurrent modification detected on {target_file} during verification."],
            bind_comparison=bind_cmp,
            companion_warning=companion_warning,
        )

    backup_rec = create_backup(
        target_file,
        backup_dir=backup_dir,
        config_dir=abs_config_dir,
        env=env,
    )

    atomic_write_bytes(target_file, new_bytes, mode_source=backup_rec.backup_path)

    expected_new_sha = hashlib.sha256(new_bytes).hexdigest()
    actual_new_sha = compute_file_sha256(target_file)
    if actual_new_sha != expected_new_sha:
        restore_backup(backup_rec, force=True, backup_dir=backup_dir, env=env)
        return ApplyResult(
            applied=False,
            rolled_back=True,
            backup=backup_rec,
            diff=diff,
            verify=verify_res,
            errors=[
                f"Post-write sha256 verification failed (expected {expected_new_sha}, got {actual_new_sha}); rolled back."
            ],
            bind_comparison=bind_cmp,
            companion_warning=companion_warning,
        )

    if reload:
        reload_ok, reload_err = _run_live_reload_and_check(
            reload_runner=reload_runner,
            sleep_fn=sleep_fn,
        )
        if not reload_ok:
            restore_backup(backup_rec, force=True, backup_dir=backup_dir, env=env)
            return ApplyResult(
                applied=False,
                rolled_back=True,
                backup=backup_rec,
                diff=diff,
                verify=verify_res,
                errors=[f"Live reload failed ({reload_err}); automatically rolled back to {backup_rec.id}."],
                bind_comparison=bind_cmp,
                companion_warning=companion_warning,
            )

    return ApplyResult(
        applied=True,
        rolled_back=False,
        backup=backup_rec,
        diff=diff,
        verify=verify_res,
        errors=[],
        bind_comparison=bind_cmp,
        companion_warning=companion_warning,
    )


def resolve_uncomment_op(
    bind_id: str,
    config_dir: str,
    entrypoint: str,
    candidate_files: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> EditOp:
    """Locate an HKS-disabled line that would produce `bind_id` when uncommented and return its EditOp."""
    abs_config_dir = os.path.abspath(os.path.expanduser(config_dir))
    abs_entrypoint = os.path.abspath(os.path.expanduser(entrypoint))
    paths = [os.path.abspath(os.path.expanduser(p)) for p in (candidate_files or [abs_entrypoint])]

    for fpath in paths:
        if not os.path.isfile(fpath):
            continue
        is_lua = fpath.endswith(".lua")
        prefix = LUA_DISABLED_PREFIX if is_lua else HYPRLANG_DISABLED_PREFIX
        lang = "lua" if is_lua else "hyprlang"

        with open(fpath, "r", encoding="utf-8") as f:
            text = f.read()

        lines = text.splitlines()
        disabled_ops: dict[int, EditOp] = {}
        for idx, line_str in enumerate(lines, start=1):
            if line_str.lstrip(" \t").startswith(prefix):
                disabled_ops[idx] = EditOp(
                    kind="uncomment",
                    file=fpath,
                    line_number=idx,
                    expected_text=line_str,
                    language=lang,
                )

        if not disabled_ops:
            continue

        trial_text = apply_ops_to_text(text, list(disabled_ops.values()))
        trial_bytes = trial_text.encode("utf-8")

        with stage_candidate_config(
            config_dir=abs_config_dir,
            entrypoint=abs_entrypoint,
            target_file=fpath,
            new_bytes=trial_bytes,
        ) as (staged_dir, staged_entry, _):
            if staged_entry.endswith(".lua"):
                staged_binds, _, _, _, _ = parse_lua_config(
                    entrypoint=staged_entry,
                    config_dir=staged_dir,
                    env=env,
                )
            else:
                staged_binds, _, _, _, _, _ = parse_hyprlang_config(
                    entrypoint=staged_entry,
                )

            for b in staged_binds:
                if b.source_line not in disabled_ops:
                    continue
                try:
                    rel_src = os.path.relpath(b.source_file, staged_dir)
                    real_src = os.path.abspath(os.path.join(abs_config_dir, rel_src))
                except ValueError:
                    real_src = fpath

                if real_src != fpath:
                    continue

                recomputed_id = compute_bind_id(
                    abs_file=fpath,
                    line=b.source_line,
                    occurrence=b.occurrence,
                    keys=b.keys_raw,
                    dispatcher_path=b.dispatcher.path,
                )
                if recomputed_id == bind_id:
                    if b.generated:
                        raise NotEditableError(
                            f"Bind '{bind_id}' is generated by a loop at "
                            f"{fpath}:{b.source_line} ({b.occurrences_at_site} binds emitted at this call site) "
                            f"and cannot be edited individually. Edit the loop in {fpath}:{b.source_line} directly."
                        )
                    return disabled_ops[b.source_line]

    raise KeyError(
        f"Disabled bind '{bind_id}' not found in configuration (no matching HKS-disabled line)."
    )

