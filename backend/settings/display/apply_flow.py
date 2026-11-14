"""Validation, Lua generation, and confirm-or-revert display apply flow."""

from __future__ import annotations

import hashlib
import math
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from backend.core import revert_guard
from backend.core.constants import MONITORS_SECTION_NAME, OVERRIDES_FILENAME, SHA256_ABSENT
from backend.core.overrides import OverridesError, replace_section
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
from backend.editor.codegen import encode_lua_string
from backend.settings.commit import _check_include_installed
from backend.settings.display.state import (
    MonitorOutput,
    extract_monitors_overrides,
    mode_matches_available,
    normalize_mode_str,
)

_POS_RE = re.compile(r"^-?\d+x-?\d+$")


@dataclass(slots=True)
class MonitorRuleSpec:
    output: str
    disabled: bool = False
    mode: str = "preferred"
    position: str = "0x0"
    scale: float = 1.0
    transform: int = 0
    vrr: int = 0
    mirror_of: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "output": self.output,
            "disabled": self.disabled,
            "mode": self.mode,
            "position": self.position,
            "scale": self.scale,
            "transform": self.transform,
            "vrr": self.vrr,
            "mirror_of": self.mirror_of,
        }


@dataclass(slots=True)
class DisplayApplyResult:
    applied: bool
    errors: list[str] = field(default_factory=list)
    diff: str = ""
    deadline_epoch: float = 0.0
    timeout_seconds: float = 15.0
    handle: RevertGuardHandle | None = None
    transaction: TransactionResult | None = None
    rules: list[MonitorRuleSpec] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "errors": list(self.errors),
            "diff": self.diff,
            "deadline_epoch": self.deadline_epoch,
            "timeout_seconds": self.timeout_seconds,
            "plan_path": self.handle.plan_path if self.handle else None,
            "watchdog_pid": self.handle.pid if self.handle else None,
            "transaction": self.transaction.to_dict() if self.transaction else None,
            "rules": [r.to_dict() for r in self.rules],
        }


def _coerce_changes_list(
    changes: Sequence[Mapping[str, Any]] | Mapping[str, Any],
) -> list[dict[str, Any]]:
    if isinstance(changes, Mapping):
        if "monitors" in changes and isinstance(changes["monitors"], Sequence):
            return [dict(c) for c in changes["monitors"] if isinstance(c, Mapping)]
        if "output" in changes:
            return [dict(changes)]
        out: list[dict[str, Any]] = []
        for k, v in changes.items():
            if isinstance(v, Mapping):
                item = dict(v)
                item.setdefault("output", k)
                out.append(item)
        return out
    return [dict(c) for c in changes if isinstance(c, Mapping)]


def _default_mode_for_output(info: MonitorOutput) -> str:
    if not info.disabled and info.current_mode and (
        not info.available_modes or mode_matches_available(info.current_mode, info.available_modes)
    ):
        return info.current_mode
    if info.available_modes:
        return normalize_mode_str(info.available_modes[0])
    return info.current_mode or "preferred"


def validate_display_changes(
    changes: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    current_outputs: Sequence[MonitorOutput],
) -> tuple[list[MonitorRuleSpec], list[str]]:
    """Validate monitor changes against live output capabilities and topology safety rules."""
    items = _coerce_changes_list(changes)
    if not items:
        return [], ["At least one monitor configuration entry is required."]

    current_by_name = {o.name: o for o in current_outputs}
    errors: list[str] = []
    seen_in_changes: set[str] = set()
    changed_specs: dict[str, MonitorRuleSpec] = {}

    for item in items:
        raw_out = item.get("output")
        if not isinstance(raw_out, str) or not raw_out.strip():
            errors.append("Each monitor rule must specify a non-empty 'output' name.")
            continue
        name = raw_out.strip()
        if name in seen_in_changes:
            errors.append(f"Duplicate monitor rule for output {name!r}.")
            continue
        seen_in_changes.add(name)

        info = current_by_name.get(name)
        if info is None:
            errors.append(f"Unknown output {name!r}; connected outputs are {sorted(current_by_name.keys())}.")
            continue

        disabled = item.get("disabled", info.disabled)
        if not isinstance(disabled, bool):
            errors.append(f"Output {name!r}: 'disabled' must be a boolean.")
            continue

        mode_raw = item.get("mode", _default_mode_for_output(info))
        if not isinstance(mode_raw, str):
            errors.append(f"Output {name!r}: 'mode' must be a string.")
            continue
        canonical_mode = normalize_mode_str(mode_raw)

        pos_raw = item.get("position", info.position or "0x0")
        if not isinstance(pos_raw, str) or not _POS_RE.match(pos_raw.strip()):
            errors.append(f"Output {name!r}: invalid position {pos_raw!r} (expected '<x>x<y>').")
            continue
        pos = pos_raw.strip()

        scale_raw = item.get("scale", info.scale)
        if isinstance(scale_raw, bool) or not isinstance(scale_raw, (int, float)):
            errors.append(f"Output {name!r}: 'scale' must be a number.")
            continue
        scale_val = round(float(scale_raw), 4)
        if math.isnan(scale_val) or math.isinf(scale_val) or scale_val < 0.25 or scale_val > 4.0:
            errors.append(f"Output {name!r}: scale {scale_val} out of supported range [0.25, 4.0].")
            continue

        tr_raw = item.get("transform", info.transform)
        if isinstance(tr_raw, bool) or not isinstance(tr_raw, int) or tr_raw < 0 or tr_raw > 7:
            errors.append(f"Output {name!r}: transform {tr_raw!r} must be an integer in 0..7.")
            continue

        vrr_raw = item.get("vrr", info.vrr)
        if isinstance(vrr_raw, bool):
            vrr_val = 1 if vrr_raw else 0
        elif isinstance(vrr_raw, int) and 0 <= vrr_raw <= 3:
            vrr_val = vrr_raw
        else:
            errors.append(f"Output {name!r}: vrr {vrr_raw!r} must be 0..3.")
            continue

        mirror_raw = item.get("mirror_of", item.get("mirror", info.mirror_of))
        if mirror_raw is None:
            mirror_val = ""
        elif not isinstance(mirror_raw, str):
            errors.append(f"Output {name!r}: 'mirror_of' must be a string.")
            continue
        else:
            m_clean = mirror_raw.strip()
            mirror_val = "" if m_clean in ("", "none") else m_clean

        if not disabled:
            if info.available_modes:
                matched = mode_matches_available(canonical_mode, info.available_modes)
                if matched is None:
                    errors.append(
                        f"Output {name!r}: mode {mode_raw!r} is not in availableModes ({info.available_modes})."
                    )
                    continue
                canonical_mode = matched
            if vrr_val > 0 and not info.vrr_capable:
                errors.append(f"Output {name!r} does not support VRR (vrrCapable=false).")
                continue
            if mirror_val:
                if mirror_val == name:
                    errors.append(f"Output {name!r} cannot mirror itself.")
                    continue
                if mirror_val not in current_by_name:
                    errors.append(f"Output {name!r}: unknown mirror target {mirror_val!r}.")
                    continue

        changed_specs[name] = MonitorRuleSpec(
            output=name,
            disabled=disabled,
            mode=canonical_mode,
            position=pos,
            scale=scale_val,
            transform=tr_raw,
            vrr=vrr_val,
            mirror_of="" if disabled else mirror_val,
        )

    if errors:
        return [], errors

    # Build final combined monitor state across all connected outputs for safety checks.
    final_disabled: dict[str, bool] = {}
    final_mirrors: dict[str, str] = {}
    for name, info in current_by_name.items():
        if name in changed_specs:
            sp = changed_specs[name]
            final_disabled[name] = sp.disabled
            final_mirrors[name] = sp.mirror_of if not sp.disabled else ""
        else:
            final_disabled[name] = info.disabled
            m_cur = "" if info.mirror_of in ("", "none") or info.disabled else info.mirror_of
            final_mirrors[name] = m_cur

    if current_by_name and sum(1 for d in final_disabled.values() if not d) < 1:
        errors.append(
            "Cannot disable the last enabled output; at least one monitor must remain enabled."
        )

    for src, target in final_mirrors.items():
        if not target:
            continue
        if target in final_disabled and final_disabled[target]:
            errors.append(f"Cannot mirror output {src!r} to disabled output {target!r}.")
            continue
        # Detect mirror chains / cycles
        visited = {src}
        curr = target
        while curr:
            if curr in visited:
                errors.append(f"Mirror cycle detected involving output {src!r}.")
                break
            visited.add(curr)
            curr = final_mirrors.get(curr, "")

    if errors:
        return [], errors

    ordered = [changed_specs[k] for k in sorted(changed_specs.keys())]
    return ordered, []


def render_monitors_section(rules: Sequence[MonitorRuleSpec]) -> str:
    """Render deterministic `hl.monitor({...})` calls for the 'monitors' overrides section."""
    blocks: list[str] = []
    for r in sorted(rules, key=lambda spec: spec.output):
        lines = [
            "hl.monitor({",
            f"    output = {encode_lua_string(r.output)},",
        ]
        if r.disabled:
            lines.append("    disabled = true,")
        else:
            lines.extend(
                [
                    f"    mode = {encode_lua_string(r.mode)},",
                    f"    position = {encode_lua_string(r.position)},",
                    f"    scale = {r.scale:g},",
                    f"    transform = {r.transform},",
                    f"    vrr = {r.vrr},",
                ]
            )
            if r.mirror_of and r.mirror_of != "none":
                lines.append(f"    mirror = {encode_lua_string(r.mirror_of)},")
        lines.append("})")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _merge_rules_with_existing(
    existing_map: Mapping[str, Mapping[str, Any]],
    new_rules: Sequence[MonitorRuleSpec],
) -> list[MonitorRuleSpec]:
    merged: dict[str, MonitorRuleSpec] = {}
    for out_name, fields in existing_map.items():
        merged[out_name] = MonitorRuleSpec(
            output=out_name,
            disabled=bool(fields.get("disabled", False)),
            mode=str(fields.get("mode", "preferred")),
            position=str(fields.get("position", "0x0")),
            scale=float(fields.get("scale", 1.0)),
            transform=int(fields.get("transform", 0)),
            vrr=int(fields.get("vrr", 0)),
            mirror_of=str(fields.get("mirror", "") or ""),
        )
    for r in new_rules:
        merged[r.output] = r
    return [merged[k] for k in sorted(merged.keys())]


def apply_display_changes(
    changes: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    *,
    current_outputs: Sequence[MonitorOutput],
    config_dir: str,
    entrypoint: str,
    expected_sha256: str,
    timeout_seconds: float = 15.0,
    watch_pid: int | None = None,
    backup_dir: str | None = None,
    state_dir: str | None = None,
    env: dict[str, str] | None = None,
    hyprland_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    reload_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    reload_mode: str = "full",
    dry_run: bool = False,
) -> DisplayApplyResult:
    """Validate, build candidate overrides, arm revert_guard, apply_managed_change, and return handle."""
    if reload_mode not in VALID_RELOAD_MODES:
        return DisplayApplyResult(
            applied=False,
            errors=[f"Invalid reload_mode: {reload_mode!r}"],
        )

    abs_config_dir = os.path.abspath(os.path.expanduser(config_dir))
    abs_entry = os.path.abspath(os.path.expanduser(entrypoint))
    ov_path = os.path.join(abs_config_dir, OVERRIDES_FILENAME)

    # (a) Validate include block + monitor rules
    inc_err = _check_include_installed(abs_entry)
    if inc_err is not None:
        return DisplayApplyResult(applied=False, errors=[inc_err])

    validated_rules, val_errs = validate_display_changes(changes, current_outputs)
    if val_errs:
        return DisplayApplyResult(applied=False, errors=val_errs)

    # (b) Build candidate overrides
    existing_text: str | None = None
    existing_monitors: dict[str, dict[str, Any]] = {}
    was_absent = not os.path.exists(ov_path)
    if not was_absent:
        if not os.path.isfile(ov_path):
            return DisplayApplyResult(
                applied=False,
                errors=[f"Overrides path is not a regular file: {ov_path}"],
            )
        cur_sha = compute_file_sha256(ov_path)
        if cur_sha != expected_sha256:
            return DisplayApplyResult(
                applied=False,
                errors=[
                    f"SHA-256 mismatch on {ov_path}: current {cur_sha} != expected {expected_sha256}."
                ],
            )
        with open(ov_path, "r", encoding="utf-8") as f:
            existing_text = f.read()
        try:
            existing_monitors = extract_monitors_overrides(existing_text)
        except OverridesError as exc:
            return DisplayApplyResult(
                applied=False,
                errors=[f"Malformed overrides file: {exc}"],
            )
    else:
        if expected_sha256 != SHA256_ABSENT:
            return DisplayApplyResult(
                applied=False,
                errors=[
                    f"Target file does not exist: {ov_path} "
                    f"(expected sha256 {expected_sha256!r}; pass {SHA256_ABSENT!r} to create)."
                ],
            )

    merged_rules = _merge_rules_with_existing(existing_monitors, validated_rules)
    section_body = render_monitors_section(merged_rules)
    candidate_text = replace_section(existing_text, MONITORS_SECTION_NAME, section_body)
    candidate_bytes = candidate_text.encode("utf-8")
    candidate_sha = hashlib.sha256(candidate_bytes).hexdigest()

    if dry_run:
        tx_dry = apply_managed_change(
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
        return DisplayApplyResult(
            applied=False,
            errors=list(tx_dry.errors),
            diff=tx_dry.diff,
            transaction=tx_dry,
            rules=merged_rules,
        )

    # (c) Arm revert_guard BEFORE any write or live reload (fail closed)
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
            return DisplayApplyResult(
                applied=False,
                errors=[f"Failed to create pre-apply backup before arming guard: {exc}"],
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
        return DisplayApplyResult(
            applied=False,
            errors=[f"Revert guard failed to arm: {exc}"],
        )

    # (d) apply_managed_change (verifies with Hyprland --verify-config before writing)
    try:
        tx_res = apply_managed_change(
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
        return DisplayApplyResult(
            applied=False,
            errors=[f"Apply failed unexpectedly after arming guard: {exc}"],
        )

    if not tx_res.applied:
        try:
            revert_guard.confirm(handle)
        except Exception:
            pass
        revert_guard.cancel(handle)
        clear_active_handle(state_dir=resolved_sdir, env=env)
        return DisplayApplyResult(
            applied=False,
            errors=list(tx_res.errors) or ["Display transaction failed without specific error."],
            diff=tx_res.diff,
            transaction=tx_res,
            rules=merged_rules,
        )

    # (e) Persist active guard and return deadline + handle info
    deadline_epoch = time.time() + float(timeout_seconds)
    save_active_handle(
        handle,
        deadline_epoch=deadline_epoch,
        timeout_seconds=timeout_seconds,
        state_dir=resolved_sdir,
        env=env,
    )
    return DisplayApplyResult(
        applied=True,
        errors=[],
        diff=tx_res.diff,
        deadline_epoch=deadline_epoch,
        timeout_seconds=float(timeout_seconds),
        handle=handle,
        transaction=tx_res,
        rules=merged_rules,
    )


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


def confirm_display_changes(
    *,
    handle: RevertGuardHandle | None = None,
    state_dir: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Confirm pending display changes by signaling the watchdog's confirm_path."""
    eff_handle = handle
    if eff_handle is None:
        loaded = load_active_handle(state_dir=state_dir, env=env)
        if loaded is None:
            return {"ok": False, "confirmed": False, "error": "No pending display guard to confirm."}
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


def revert_display_changes(
    *,
    handle: RevertGuardHandle | None = None,
    state_dir: str | None = None,
    env: Mapping[str, str] | None = None,
    reload_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Immediately revert pending display changes and disarm the watchdog."""
    eff_handle = handle
    if eff_handle is None:
        loaded = load_active_handle(state_dir=state_dir, env=env)
        if loaded is None:
            return {"ok": False, "reverted": False, "error": "No pending display guard to revert."}
        eff_handle = loaded[0]

    # Disarm watchdog first so it does not race the synchronous restore below.
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
    reload_mode = str(plan.get("reload_mode", "full"))
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
