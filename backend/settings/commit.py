"""Transactional commit and reset for Hyprland System Settings."""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any, Callable, Mapping

from backend.core.constants import OVERRIDES_FILENAME, SHA256_ABSENT
from backend.core.include_block import IncludeBlockError, has_include
from backend.core.overrides import (
    OverridesError,
    remove_section,
    render_config_call,
    replace_section,
)
from backend.core.transaction import TransactionResult, apply_managed_change
from backend.settings.catalog import CATALOG_BY_ID
from backend.settings.preview import PreviewValidationError, build_nested_config, validate_changes
from backend.settings.state import extract_overrides_map


def _check_include_installed(entrypoint: str) -> str | None:
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


def _render_overrides_document(
    existing_text: str | None,
    merged_values: Mapping[str, Any],
) -> str:
    """Update 'appearance' and 'desktop' sections in overrides text; remove empty sections."""
    doc = existing_text
    for sec in ("appearance", "desktop"):
        sec_vals = {
            opt_id: val
            for opt_id, val in merged_values.items()
            if CATALOG_BY_ID[opt_id].section == sec
        }
        if sec_vals:
            body = render_config_call(build_nested_config(sec_vals))
            doc = replace_section(doc, sec, body)
        elif doc is not None:
            doc = remove_section(doc, sec)
    return doc if doc is not None else ""


def commit_settings(
    changes: Mapping[str, Any],
    *,
    config_dir: str,
    entrypoint: str,
    expected_sha256: str,
    resets: list[str] | tuple[str, ...] = (),
    backup_dir: str | None = None,
    env: dict[str, str] | None = None,
    hyprland_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    reload_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    reload_mode: str = "config-only",
    dry_run: bool = True,
) -> TransactionResult:
    """Validate, merge, and transactionally commit settings changes to hks-overrides.lua."""
    abs_config_dir = os.path.abspath(os.path.expanduser(config_dir))
    abs_entry = os.path.abspath(os.path.expanduser(entrypoint))
    ov_path = os.path.join(abs_config_dir, OVERRIDES_FILENAME)

    inc_err = _check_include_installed(abs_entry)
    if inc_err is not None:
        return TransactionResult(
            applied=False,
            rolled_back=False,
            created=False,
            backup=None,
            diff="",
            verify=None,
            errors=[inc_err],
            reload_mode=reload_mode,
            target_path=ov_path,
        )

    try:
        validated = validate_changes(changes)
    except PreviewValidationError as exc:
        return TransactionResult(
            applied=False,
            rolled_back=False,
            created=False,
            backup=None,
            diff="",
            verify=None,
            errors=[str(exc)],
            reload_mode=reload_mode,
            target_path=ov_path,
        )

    existing_text: str | None = None
    existing_map: dict[str, Any] = {}
    if os.path.isfile(ov_path):
        with open(ov_path, "r", encoding="utf-8") as f:
            existing_text = f.read()
        try:
            existing_map = extract_overrides_map(existing_text)
        except OverridesError as exc:
            return TransactionResult(
                applied=False,
                rolled_back=False,
                created=False,
                backup=None,
                diff="",
                verify=None,
                errors=[f"Malformed overrides file: {exc}"],
                reload_mode=reload_mode,
                target_path=ov_path,
            )

    merged = dict(existing_map)
    for opt_id in resets:
        merged.pop(opt_id, None)
    merged.update(validated)

    new_text = _render_overrides_document(existing_text, merged)
    return apply_managed_change(
        ov_path,
        new_text.encode("utf-8"),
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
        dry_run=dry_run,
    )


def reset_settings(
    *,
    section: str | None = None,
    option_id: str | None = None,
    config_dir: str,
    entrypoint: str,
    expected_sha256: str,
    backup_dir: str | None = None,
    env: dict[str, str] | None = None,
    hyprland_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    reload_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    reload_mode: str = "config-only",
    dry_run: bool = True,
) -> TransactionResult:
    """Reset either an entire section or a single option_id back to compositor defaults."""
    if option_id is not None:
        if option_id not in CATALOG_BY_ID:
            return TransactionResult(
                applied=False,
                rolled_back=False,
                created=False,
                backup=None,
                diff="",
                verify=None,
                errors=[f"Unknown option id: {option_id!r}"],
                reload_mode=reload_mode,
                target_path=os.path.join(os.path.abspath(config_dir), OVERRIDES_FILENAME),
            )
        resets = [option_id]
    elif section is not None:
        if section not in ("appearance", "desktop"):
            return TransactionResult(
                applied=False,
                rolled_back=False,
                created=False,
                backup=None,
                diff="",
                verify=None,
                errors=[f"Unknown section: {section!r}"],
                reload_mode=reload_mode,
                target_path=os.path.join(os.path.abspath(config_dir), OVERRIDES_FILENAME),
            )
        resets = [opt.id for opt in CATALOG_BY_ID.values() if opt.section == section]
    else:
        resets = list(CATALOG_BY_ID.keys())

    return commit_settings(
        {},
        resets=resets,
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
