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
from backend.core.confirm_flow import (
    DEFAULT_CONFIRM_TIMEOUT_SECONDS,
    ConfirmDomainValidation,
    apply_with_confirm_flow,
    confirm_flow_changes,
    revert_flow_changes,
)
from backend.core.constants import MONITORS_SECTION_NAME
from backend.core.revert_guard import RevertGuardHandle
from backend.core.transaction import TransactionResult, apply_managed_change
from backend.editor.codegen import encode_lua_string
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
    timeout_seconds: float = DEFAULT_CONFIRM_TIMEOUT_SECONDS,
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

    def _validate(existing_text: str | None) -> ConfirmDomainValidation:
        validated_rules, val_errs = validate_display_changes(changes, current_outputs)
        if val_errs:
            return ConfirmDomainValidation(errors=val_errs)
        existing_monitors = (
            extract_monitors_overrides(existing_text) if existing_text is not None else {}
        )
        merged_rules = _merge_rules_with_existing(existing_monitors, validated_rules)
        section_body = render_monitors_section(merged_rules)
        return ConfirmDomainValidation(section_body=section_body, metadata=merged_rules)

    cf_res = apply_with_confirm_flow(
        section_name=MONITORS_SECTION_NAME,
        domain_validator=_validate,
        config_dir=config_dir,
        entrypoint=entrypoint,
        expected_sha256=expected_sha256,
        reload_mode=reload_mode,
        timeout_seconds=timeout_seconds,
        watch_pid=watch_pid,
        backup_dir=backup_dir,
        state_dir=state_dir,
        env=env,
        hyprland_runner=hyprland_runner,
        reload_runner=reload_runner,
        sleep_fn=sleep_fn,
        dry_run=dry_run,
        apply_fn=apply_managed_change,
    )
    merged_rules = cf_res.metadata if isinstance(cf_res.metadata, list) else []
    return DisplayApplyResult(
        applied=cf_res.applied,
        errors=cf_res.errors,
        diff=cf_res.diff,
        deadline_epoch=cf_res.deadline_epoch,
        timeout_seconds=cf_res.timeout_seconds,
        handle=cf_res.handle,
        transaction=cf_res.transaction,
        rules=merged_rules,
    )


def confirm_display_changes(
    *,
    handle: RevertGuardHandle | None = None,
    state_dir: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Confirm pending display changes by signaling the watchdog's confirm_path."""
    return confirm_flow_changes(
        handle=handle,
        state_dir=state_dir,
        env=env,
        label="display",
    )


def revert_display_changes(
    *,
    handle: RevertGuardHandle | None = None,
    state_dir: str | None = None,
    env: Mapping[str, str] | None = None,
    reload_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Immediately revert pending display changes and disarm the watchdog."""
    return revert_flow_changes(
        handle=handle,
        state_dir=state_dir,
        env=env,
        reload_runner=reload_runner,
        sleep_fn=sleep_fn,
        default_reload_mode="full",
        label="display",
    )
