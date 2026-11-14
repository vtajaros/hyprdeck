"""Validation and live `hyprctl eval` preview for Hyprland settings."""

from __future__ import annotations

import math
import re
import subprocess
from typing import Any, Callable, Mapping

from backend.core.overrides import OverridesError, render_config_call
from backend.settings.catalog import CATALOG_BY_ID, OptionSpec

_COLOR_RE = re.compile(r"^(?:0x[0-9a-fA-F]{6,8}|#[0-9a-fA-F]{6,8})$")


class PreviewValidationError(ValueError):
    """Raised when a settings change set fails schema/range/type validation."""


def validate_option_value(spec: OptionSpec, value: Any) -> Any:
    """Validate and normalize a single option value against its OptionSpec."""
    if value is None:
        raise PreviewValidationError(f"Option {spec.id!r} value cannot be null")

    if spec.type == "bool":
        if not isinstance(value, bool):
            raise PreviewValidationError(f"Option {spec.id!r} requires a bool, got {type(value).__name__}")
        return value

    if spec.type == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise PreviewValidationError(f"Option {spec.id!r} requires an int, got {type(value).__name__}")
        if spec.min is not None and value < spec.min:
            raise PreviewValidationError(f"Option {spec.id!r} value {value} < min {spec.min}")
        if spec.max is not None and value > spec.max:
            raise PreviewValidationError(f"Option {spec.id!r} value {value} > max {spec.max}")
        return value

    if spec.type == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PreviewValidationError(f"Option {spec.id!r} requires a float, got {type(value).__name__}")
        fval = float(value)
        if math.isnan(fval) or math.isinf(fval):
            raise PreviewValidationError(f"Option {spec.id!r} cannot be NaN or inf")
        if spec.min is not None and fval < spec.min:
            raise PreviewValidationError(f"Option {spec.id!r} value {fval} < min {spec.min}")
        if spec.max is not None and fval > spec.max:
            raise PreviewValidationError(f"Option {spec.id!r} value {fval} > max {spec.max}")
        return fval

    if spec.type == "enum":
        if not isinstance(value, str) or value not in spec.enum_values:
            raise PreviewValidationError(
                f"Option {spec.id!r} must be one of {list(spec.enum_values)}, got {value!r}"
            )
        return value

    if spec.type == "color":
        if not isinstance(value, str) or not _COLOR_RE.match(value):
            raise PreviewValidationError(
                f"Option {spec.id!r} requires a color (#RRGGBB or 0xAARRGGBB), got {value!r}"
            )
        return value

    if spec.type == "string":
        if not isinstance(value, str):
            raise PreviewValidationError(f"Option {spec.id!r} requires a string")
        if "\x00" in value or "\n" in value or "\r" in value:
            raise PreviewValidationError(f"Option {spec.id!r} string contains forbidden control chars")
        return value

    raise PreviewValidationError(f"Unsupported option type {spec.type!r}")


def validate_changes(changes: Mapping[str, Any]) -> dict[str, Any]:
    """Validate all {option_id: value} pairs and return normalized dict."""
    if not isinstance(changes, Mapping):
        raise PreviewValidationError("Changes payload must be a JSON object")
    out: dict[str, Any] = {}
    for opt_id, raw_val in changes.items():
        if opt_id not in CATALOG_BY_ID:
            raise PreviewValidationError(f"Unknown option id: {opt_id!r}")
        spec = CATALOG_BY_ID[opt_id]
        out[opt_id] = validate_option_value(spec, raw_val)
    return out


def build_nested_config(validated: Mapping[str, Any]) -> dict[str, Any]:
    """Nest flat {option_id: value} into {section: {sub: val}} using hyprland_path."""
    root: dict[str, Any] = {}
    for opt_id, val in validated.items():
        spec = CATALOG_BY_ID[opt_id]
        parts = spec.hyprland_path.split(".")
        cur = root
        for part in parts[:-1]:
            if part not in cur or not isinstance(cur[part], dict):
                cur[part] = {}
            cur = cur[part]
        cur[parts[-1]] = val
    return root


def preview_settings(
    changes: Mapping[str, Any],
    *,
    hyprctl_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    """Validate changes, render `hl.config(...)`, and apply ephemerally via `hyprctl eval`."""
    validated = validate_changes(changes)
    if not validated:
        return {"ok": True, "rendered": "", "message": "No changes to preview."}

    nested = build_nested_config(validated)
    try:
        rendered = render_config_call(nested)
    except OverridesError as exc:
        raise PreviewValidationError(str(exc)) from exc

    run_fn = hyprctl_runner if hyprctl_runner is not None else subprocess.run
    try:
        proc = run_fn(
            ["hyprctl", "eval", rendered],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "rendered": rendered, "error": f"Failed to run hyprctl eval: {exc}"}

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return {"ok": False, "rendered": rendered, "error": f"hyprctl eval failed ({proc.returncode}): {detail}"}

    return {"ok": True, "rendered": rendered, "output": (proc.stdout or "").strip()}


def revert_preview(
    *,
    hyprctl_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    """Revert ephemeral preview changes via `hyprctl reload config-only`."""
    run_fn = hyprctl_runner if hyprctl_runner is not None else subprocess.run
    try:
        proc = run_fn(
            ["hyprctl", "reload", "config-only"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": f"Failed to run hyprctl reload config-only: {exc}"}

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return {"ok": False, "error": f"hyprctl reload config-only failed ({proc.returncode}): {detail}"}

    return {"ok": True, "output": (proc.stdout or "").strip()}
