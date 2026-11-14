"""Input state probing, validation, confirm-flow routing, and commit/confirm/revert."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from backend.core.confirm_flow import (
    DEFAULT_CONFIRM_TIMEOUT_SECONDS,
    ConfirmDomainValidation,
    apply_with_confirm_flow,
    confirm_flow_changes,
    revert_flow_changes,
)
from backend.core.constants import (
    DEVICES_SECTION_NAME,
    INPUT_SECTION_NAME,
    OVERRIDES_FILENAME,
    SHA256_ABSENT,
)
from backend.core.include_block import IncludeBlockError, has_include
from backend.core.overrides import OverridesError, render_config_call
from backend.core.revert_guard import RevertGuardHandle, load_active_handle
from backend.core.revert_watchdog import _pid_alive
from backend.core.transaction import VALID_RELOAD_MODES, TransactionResult
from backend.discovery.config_discovery import discover_config
from backend.editor.backups import compute_file_sha256
from backend.settings.catalog import CATALOG_BY_ID
from backend.settings.commit import commit_settings
from backend.settings.input.devices import (
    DeviceRuleSpec,
    InputDevice,
    extract_devices_overrides,
    probe_devices,
    render_devices_section,
    validate_device_rules,
)
from backend.settings.input.xkb import XkbRules, load_xkb_rules, validate_keyboard_layout
from backend.settings.preview import PreviewValidationError, build_nested_config, validate_changes
from backend.settings.state import current_state, extract_overrides_map


@dataclass(slots=True)
class InputApplyResult:
    applied: bool
    requires_confirm: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    diff: str = ""
    deadline_epoch: float = 0.0
    timeout_seconds: float = DEFAULT_CONFIRM_TIMEOUT_SECONDS
    handle: RevertGuardHandle | None = None
    transaction: TransactionResult | None = None
    device_rules: list[DeviceRuleSpec] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "requires_confirm": self.requires_confirm,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "diff": self.diff,
            "deadline_epoch": self.deadline_epoch,
            "timeout_seconds": self.timeout_seconds,
            "plan_path": self.handle.plan_path if self.handle else None,
            "watchdog_pid": self.handle.pid if self.handle else None,
            "transaction": self.transaction.to_dict() if self.transaction else None,
            "device_rules": [r.to_dict() for r in self.device_rules],
        }


def get_input_state(
    *,
    config_dir: str | None = None,
    entrypoint: str | None = None,
    no_live: bool = False,
    state_dir: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return full input settings state (catalog options, XKB rules, devices, active guard)."""
    environ = env if env is not None else os.environ
    disc = discover_config(
        config_dir=config_dir,
        entrypoint=entrypoint,
        no_live=no_live,
        env=dict(environ),
    )
    abs_cfg = disc.environment.config_dir
    abs_entry = disc.environment.entrypoint
    ov_path = os.path.join(abs_cfg, OVERRIDES_FILENAME)

    full_state = current_state(
        config_dir=abs_cfg,
        entrypoint=abs_entry,
        no_live=no_live,
        hyprctl_runner=runner,
    )
    input_options = [o for o in full_state.get("options", []) if o.get("section") == INPUT_SECTION_NAME]

    include_installed = False
    if os.path.isfile(abs_entry) and abs_entry.lower().endswith(".lua"):
        try:
            with open(abs_entry, "r", encoding="utf-8") as f:
                include_installed = has_include(f.read())
        except IncludeBlockError:
            include_installed = False

    ov_present = os.path.isfile(ov_path)
    ov_sha = compute_file_sha256(ov_path) if ov_present else SHA256_ABSENT
    device_overrides: dict[str, dict[str, Any]] = {}
    if ov_present:
        try:
            with open(ov_path, "r", encoding="utf-8") as f:
                device_overrides = extract_devices_overrides(f.read())
        except OverridesError:
            device_overrides = {}

    devices_error: str | None = None
    try:
        devices = probe_devices(runner=runner, env=env)
    except Exception as exc:
        devices = []
        devices_error = str(exc)

    xkb_error: str | None = None
    try:
        xkb = load_xkb_rules(env=env).to_dict()
    except Exception as exc:
        xkb = {"layouts": [], "variants": {}, "option_groups": []}
        xkb_error = str(exc)

    active_guard: dict[str, Any] | None = None
    loaded_guard = load_active_handle(state_dir=state_dir, env=environ)
    if loaded_guard is not None:
        handle, deadline_epoch, timeout_seconds = loaded_guard
        if handle.pid > 0 and _pid_alive(handle.pid) and not os.path.exists(handle.confirm_path):
            active_guard = {
                "plan_path": handle.plan_path,
                "watchdog_pid": handle.pid,
                "deadline_epoch": deadline_epoch,
                "timeout_seconds": timeout_seconds,
            }

    return {
        "config_dir": abs_cfg,
        "entrypoint": abs_entry,
        "include_installed": include_installed,
        "overrides_path": ov_path,
        "overrides_present": ov_present,
        "overrides_sha256": ov_sha,
        "options": input_options,
        "devices": [d.to_dict() for d in devices],
        "devices_error": devices_error,
        "device_overrides": device_overrides,
        "xkb": xkb,
        "xkb_error": xkb_error,
        "active_guard": active_guard,
    }


def apply_input_changes(
    option_changes: Mapping[str, Any] | None = None,
    *,
    device_changes: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None,
    current_devices: Sequence[InputDevice] | None = None,
    xkb_rules: XkbRules | None = None,
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
    reload_mode: str = "config-only",
    dry_run: bool = False,
) -> InputApplyResult:
    """Validate and apply input option and/or device rule changes.

    Non-risky option-only changes route via `commit_settings`.
    Risky option changes or any device rule changes route via `confirm_flow`.
    """
    if reload_mode not in VALID_RELOAD_MODES:
        return InputApplyResult(
            applied=False,
            errors=[f"Invalid reload_mode: {reload_mode!r}"],
            timeout_seconds=float(timeout_seconds),
        )

    opts_map = dict(option_changes or {})
    if not opts_map and not device_changes:
        return InputApplyResult(
            applied=False,
            errors=["No input option or device changes supplied."],
            timeout_seconds=float(timeout_seconds),
        )

    for opt_id in opts_map:
        spec = CATALOG_BY_ID.get(opt_id)
        if spec is None or spec.section != INPUT_SECTION_NAME:
            return InputApplyResult(
                applied=False,
                errors=[f"Unknown or non-input option id: {opt_id!r}"],
                timeout_seconds=float(timeout_seconds),
            )

    try:
        validated_opts = validate_changes(opts_map)
    except PreviewValidationError as exc:
        return InputApplyResult(
            applied=False,
            errors=[str(exc)],
            timeout_seconds=float(timeout_seconds),
        )

    requires_confirm = bool(device_changes) or any(
        CATALOG_BY_ID[opt_id].risky for opt_id in validated_opts
    )

    eff_xkb = xkb_rules if xkb_rules is not None else load_xkb_rules(env=env)
    eff_devices = (
        list(current_devices)
        if current_devices is not None
        else (probe_devices(runner=reload_runner, env=env) if device_changes else [])
    )

    def _validate_xkb_merged(merged_opts: Mapping[str, Any]) -> tuple[list[str], list[str]]:
        if not any(
            k in validated_opts for k in ("input.kb_layout", "input.kb_variant", "input.kb_options")
        ):
            return [], []
        lay = str(merged_opts.get("input.kb_layout") or "us")
        if "input.kb_layout" in validated_opts:
            lay = str(validated_opts["input.kb_layout"])
        var = str(merged_opts.get("input.kb_variant") or "")
        opts = str(merged_opts.get("input.kb_options") or "")
        return validate_keyboard_layout(lay, var, opts, xkb_rules=eff_xkb)

    if not requires_confirm:
        tx_res = commit_settings(
            validated_opts,
            config_dir=config_dir,
            entrypoint=entrypoint,
            expected_sha256=expected_sha256,
            backup_dir=backup_dir,
            env=env,
            hyprland_runner=hyprland_runner,
            reload_runner=reload_runner,
            sleep_fn=sleep_fn,
            reload_mode=reload_mode,
            dry_run=dry_run,
        )
        return InputApplyResult(
            applied=tx_res.applied,
            requires_confirm=False,
            errors=list(tx_res.errors),
            diff=tx_res.diff,
            timeout_seconds=float(timeout_seconds),
            transaction=tx_res,
        )

    def _domain_validate(existing_text: str | None) -> ConfirmDomainValidation:
        existing_opts = extract_overrides_map(existing_text) if existing_text is not None else {}
        merged_opts = dict(existing_opts)
        merged_opts.update(validated_opts)

        xkb_errs, xkb_warns = _validate_xkb_merged(merged_opts)
        if xkb_errs:
            return ConfirmDomainValidation(errors=xkb_errs, warnings=xkb_warns)

        existing_devs = (
            extract_devices_overrides(existing_text) if existing_text is not None else {}
        )
        dev_rules: list[DeviceRuleSpec] = []
        if device_changes:
            dev_rules, dev_errs = validate_device_rules(
                device_changes, eff_devices, existing_overrides=existing_devs
            )
            if dev_errs:
                return ConfirmDomainValidation(errors=dev_errs, warnings=xkb_warns)

        section_updates: dict[str, str | None] = {}
        input_vals = {
            opt_id: val
            for opt_id, val in merged_opts.items()
            if opt_id in CATALOG_BY_ID and CATALOG_BY_ID[opt_id].section == INPUT_SECTION_NAME
        }
        if input_vals:
            section_updates[INPUT_SECTION_NAME] = render_config_call(build_nested_config(input_vals))
        if device_changes:
            dev_body = render_devices_section(dev_rules)
            section_updates[DEVICES_SECTION_NAME] = dev_body if dev_body else None

        return ConfirmDomainValidation(
            section_updates=section_updates,
            warnings=xkb_warns,
            metadata=dev_rules,
        )

    cf_res = apply_with_confirm_flow(
        section_name=INPUT_SECTION_NAME,
        domain_validator=_domain_validate,
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
    )
    dev_rules = cf_res.metadata if isinstance(cf_res.metadata, list) else []
    return InputApplyResult(
        applied=cf_res.applied,
        requires_confirm=True,
        errors=cf_res.errors,
        warnings=cf_res.warnings,
        diff=cf_res.diff,
        deadline_epoch=cf_res.deadline_epoch,
        timeout_seconds=cf_res.timeout_seconds,
        handle=cf_res.handle,
        transaction=cf_res.transaction,
        device_rules=dev_rules,
    )


def confirm_input_changes(
    *,
    handle: RevertGuardHandle | None = None,
    state_dir: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Confirm pending input/device changes by signaling the watchdog's confirm_path."""
    return confirm_flow_changes(
        handle=handle,
        state_dir=state_dir,
        env=env,
        label="input",
    )


def revert_input_changes(
    *,
    handle: RevertGuardHandle | None = None,
    state_dir: str | None = None,
    env: Mapping[str, str] | None = None,
    reload_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Immediately revert pending input/device changes and disarm the watchdog."""
    return revert_flow_changes(
        handle=handle,
        state_dir=state_dir,
        env=env,
        reload_runner=reload_runner,
        sleep_fn=sleep_fn,
        default_reload_mode="config-only",
        label="input",
    )
