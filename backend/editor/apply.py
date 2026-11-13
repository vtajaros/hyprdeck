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
from backend.editor.codegen import (
    _normalize_mods,
    generate_hyprlang_bind,
    generate_lua_bind,
)
from backend.editor.edit_plan import (
    HYPRLANG_DISABLED_PREFIX,
    LUA_DISABLED_PREFIX,
    EditOp,
    NotEditableError,
    apply_ops_to_text,
    generate_unified_diff,
)
from backend.editor.insert_policy import InsertPlan, plan_insert_bind
from backend.editor.validator import (
    BindSetComparison,
    RecorderVerificationError,
    VerifyResult,
    compare_bind_sets,
    stage_candidate_config,
    verify_with_hyprland,
    verify_with_recorder,
)
from backend.models.types import BindRecord, DispatcherInfo
from backend.parser import compute_bind_id, parse_hyprlang_config, parse_lua_config
from backend.parser.modifiers import MODIFIER_BITS
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
    anchor_created: bool = False
    dispatcher_unchanged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_created": self.anchor_created,
            "applied": self.applied,
            "backup": self.backup.to_dict() if self.backup else None,
            "bind_comparison": (
                self.bind_comparison.to_dict() if self.bind_comparison else None
            ),
            "companion_warning": self.companion_warning,
            "diff": self.diff,
            "dispatcher_unchanged": self.dispatcher_unchanged,
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
    op_kind: str | None = None,
    expected_new_bind: BindRecord | None = None,
    anchor_created: bool = False,
    sidecar_path: str | None = None,
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
            op_kind=op_kind,
            expected_new_bind=expected_new_bind,
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

    dispatcher_unchanged = any(getattr(op, "dispatcher_unchanged", False) for op in ops)

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
            anchor_created=anchor_created,
            dispatcher_unchanged=dispatcher_unchanged,
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
        sidecar_path=sidecar_path,
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
        anchor_created=anchor_created,
        dispatcher_unchanged=dispatcher_unchanged,
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
        from backend.editor.disabled import collect_disabled_uncomment_ops
        ops_list = collect_disabled_uncomment_ops(lines, fpath, lang)
        disabled_ops: dict[int, EditOp] = {op.line_number: op for op in ops_list}

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


def make_expected_bind(
    language: str,
    mods: list[str] | str | None,
    key: str,
    dispatcher: str,
    args: str | None = None,
    source_file: str = "",
    submap: str = "",
    flags: dict[str, bool] | None = None,
) -> BindRecord:
    """Construct a lightweight BindRecord matching expected user-specified bind attributes."""
    canonical_mods = _normalize_mods(mods)
    modmask = sum(MODIFIER_BITS[m] for m in canonical_mods if m in MODIFIER_BITS)
    dsp_clean = dispatcher.strip()
    args_clean = args.strip() if args else ""
    if language == "hyprlang":
        from backend.editor.dispatchers import map_lua_dispatcher_to_hyprlang
        dsp_clean, mapped_args = map_lua_dispatcher_to_hyprlang(dsp_clean, args)
        args_clean = mapped_args.strip() if mapped_args else ""

    from backend.models.types import default_flags
    final_flags = default_flags()
    if flags:
        final_flags.update(flags)

    if language == "hyprlang" and flags:
        from backend.parser.modifiers import derive_bind_type_from_flags
        bind_type = derive_bind_type_from_flags(final_flags)
    else:
        bind_type = "bind"

    return BindRecord(
        id="expected_preview",
        language=language,
        bind_type=bind_type,
        declared_via=bind_type,
        modifiers=canonical_mods,
        modifiers_raw=" + ".join(canonical_mods),
        modmask=modmask,
        key=key.strip(),
        key_kind="keysym",
        keys_raw=" + ".join(canonical_mods + [key.strip()]) if canonical_mods else key.strip(),
        flags=final_flags,
        flags_extra={},
        description=None,
        dispatcher=DispatcherInfo(
            path=dsp_clean,
            args=[args_clean] if args_clean else [],
            arg_summary=args_clean,
        ),
        submap=submap,
        source_file=source_file,
        source_line=1,
        original_line="",
        original_line_number=1,
        generated=False,
        occurrence=0,
        occurrences_at_site=1,
        trace=[],
        parse_status="ok",
        args_raw=args_clean,
    )


def resolve_replace_op(
    bind_id: str,
    new_mods: list[str] | str | None,
    new_key: str,
    new_dispatcher: str | None = None,
    new_args: str | None = None,
    binds: list[BindRecord] | None = None,
    preserve_dispatcher: bool = False,
) -> tuple[EditOp, BindRecord, BindRecord]:
    """Construct an EditOp for replacing an existing keybind line.

    Returns (EditOp, target_bind, expected_new_bind).
    """
    if not binds:
        raise KeyError(f"No active binds available to resolve replace op for '{bind_id}'.")

    target_bind = next((b for b in binds if b.id == bind_id), None)
    if target_bind is None:
        raise KeyError(f"Bind '{bind_id}' not found in active configuration.")

    if target_bind.generated:
        raise NotEditableError(
            f"Bind '{bind_id}' ({target_bind.keys_raw}) is generated by a loop "
            f"({target_bind.occurrences_at_site} binds at {target_bind.source_file}:{target_bind.source_line}) "
            f"and cannot be replaced individually. Edit the generating loop instead.",
            file=target_bind.source_file,
            line=target_bind.source_line,
        )

    cur_dsp = target_bind.dispatcher.path if target_bind.dispatcher else ""
    cur_arg = target_bind.dispatcher.arg_summary if (target_bind.dispatcher and target_bind.dispatcher.arg_summary) else None
    cur_raw = target_bind.args_raw or None

    if preserve_dispatcher or (new_dispatcher is None and new_args is None):
        dispatcher_unchanged = True
    elif (new_dispatcher is not None and new_dispatcher.strip().lower() == cur_dsp.strip().lower()) and (
        (new_args == cur_arg) or (new_args == cur_raw) or (new_args is None and cur_arg is None)
    ):
        dispatcher_unchanged = True
    else:
        dispatcher_unchanged = False

    final_dispatcher = cur_dsp if dispatcher_unchanged else (new_dispatcher or cur_dsp)
    final_args = cur_arg if dispatcher_unchanged else new_args

    from backend.editor.codegen import validate_required_args
    if not dispatcher_unchanged:
        validate_required_args(final_dispatcher, final_args)
        if target_bind.language == "hyprlang":
            from backend.editor.dispatchers import map_lua_dispatcher_to_hyprlang
            map_lua_dispatcher_to_hyprlang(final_dispatcher, final_args)

    if target_bind.language == "lua":
        new_line = generate_lua_bind(
            mods=new_mods,
            key=new_key,
            dispatcher=final_dispatcher,
            args=final_args,
            original_line=target_bind.original_line,
            preserve_dispatcher=dispatcher_unchanged,
        )
    else:
        new_line = generate_hyprlang_bind(
            mods=new_mods,
            key=new_key,
            dispatcher=final_dispatcher,
            args=final_args,
            original_line=target_bind.original_line,
            preserve_dispatcher=dispatcher_unchanged,
        )

    expected_new = make_expected_bind(
        language=target_bind.language,
        mods=new_mods,
        key=new_key,
        dispatcher=final_dispatcher,
        args=final_args,
        source_file=target_bind.source_file,
        submap=target_bind.submap,
    )

    op = EditOp(
        kind="replace_line",
        file=target_bind.source_file,
        line_number=target_bind.source_line,
        expected_text=target_bind.original_line,
        new_text=new_line,
        language=target_bind.language,
        dispatcher_unchanged=dispatcher_unchanged,
    )

    return op, target_bind, expected_new


def resolve_insert_op(
    file_path: str,
    language: str,
    mods: list[str] | str | None,
    key: str,
    dispatcher: str,
    args: str | None = None,
    *,
    flags: dict[str, bool] | None = None,
    submap: str | None = None,
    all_files: list[str] | None = None,
    prefer_mainmod: bool = False,
) -> tuple[EditOp, InsertPlan, BindRecord]:
    """Construct an EditOp for inserting a new keybinding per HKS insertion policy.

    Returns (EditOp, InsertPlan, expected_new_bind).
    """
    from backend.editor.codegen import validate_required_args
    validate_required_args(dispatcher, args)
    if language == "hyprlang":
        from backend.editor.dispatchers import map_lua_dispatcher_to_hyprlang
        map_lua_dispatcher_to_hyprlang(dispatcher, args)

    from backend.editor.insert_policy import HYPRLANG_ANCHOR, LUA_ANCHOR
    target_file = file_path
    anchor = LUA_ANCHOR if language == "lua" else HYPRLANG_ANCHOR

    # If anchor exists in one of the known files, insert there; otherwise use entrypoint file
    if all_files:
        for cand in all_files:
            if os.path.isfile(cand):
                try:
                    with open(cand, "r", encoding="utf-8", errors="ignore") as f:
                        cand_content = f.read()
                    if anchor in cand_content:
                        target_file = cand
                        break
                except OSError:
                    pass

    op, plan = plan_insert_bind(
        file_path=target_file,
        language=language,
        mods=mods,
        key=key,
        dispatcher=dispatcher,
        args=args,
        flags=flags,
        submap=submap,
        prefer_mainmod=prefer_mainmod,
    )
    expected_new = make_expected_bind(
        language=language,
        mods=mods,
        key=key,
        dispatcher=dispatcher,
        args=args,
        source_file=target_file,
        submap=submap or "",
        flags=flags,
    )
    return op, plan, expected_new

