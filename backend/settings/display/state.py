"""Monitor probing (`hyprctl monitors all -j`), clean-scale math, and overrides extraction."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from backend.core.constants import (
    ENV_SETTINGS_MONITORS_FIXTURE,
    MONITORS_SECTION_NAME,
    OVERRIDES_FILENAME,
    SHA256_ABSENT,
)
from backend.core.include_block import IncludeBlockError, has_include
from backend.core.overrides import OverridesError, parse_sections
from backend.core.revert_guard import load_active_handle
from backend.core.revert_watchdog import _pid_alive
from backend.discovery.config_discovery import discover_config
from backend.editor.backups import compute_file_sha256
from backend.settings.display.brightness import read_brightness
from backend.settings.state import _parse_lua_literal, _tokenize_lua_table

PRESET_SCALES: tuple[float, ...] = (
    0.5,
    0.75,
    1.0,
    1.25,
    1.5,
    1.6,
    1.75,
    2.0,
    2.25,
    2.5,
    3.0,
)

_MODE_RE = re.compile(r"^(\d+)x(\d+)@([0-9]+(?:\.[0-9]+)?)(?:[Hh][Zz])?$")
_MONITOR_CALL_RE = re.compile(r"hl\.monitor\s*\(\s*(\{)")


def is_clean_scale(width: int, height: int, scale: float) -> bool:
    """Return True if `width / scale` and `height / scale` are exact integers."""
    if width <= 0 or height <= 0 or scale <= 0:
        return False
    denom = round(float(scale) * 10000)
    if denom <= 0:
        return False
    return (int(width) * 10000) % denom == 0 and (int(height) * 10000) % denom == 0


def build_scale_options(width: int, height: int, current_scale: float) -> list[dict[str, Any]]:
    """Build preset scale options annotated with clean vs fractional blur warnings."""
    candidates: set[float] = set(PRESET_SCALES)
    if current_scale > 0:
        candidates.add(round(float(current_scale), 4))
    out: list[dict[str, Any]] = []
    for s in sorted(candidates):
        clean = is_clean_scale(width, height, s)
        out.append(
            {
                "scale": s,
                "label": f"{s:g}x",
                "clean": clean,
                "warning": None if clean else "fractional: may blur",
            }
        )
    return out


def normalize_mode_str(mode: str) -> str:
    """Strip whitespace and trailing Hz/hz from a monitor mode string."""
    s = str(mode or "").strip()
    if s.lower().endswith("hz"):
        s = s[:-2].strip()
    return s


def mode_matches_available(candidate: str, available_modes: Sequence[str]) -> str | None:
    """Return canonical mode string if `candidate` matches `available_modes`, else None."""
    norm_cand = normalize_mode_str(candidate)
    if not norm_cand:
        return None
    for avail in available_modes:
        norm_avail = normalize_mode_str(avail)
        if norm_cand == norm_avail:
            return norm_avail
    m_cand = _MODE_RE.match(norm_cand)
    if not m_cand:
        return None
    cw, ch, cr_str = int(m_cand.group(1)), int(m_cand.group(2)), float(m_cand.group(3))
    for avail in available_modes:
        norm_avail = normalize_mode_str(avail)
        m_avail = _MODE_RE.match(norm_avail)
        if not m_avail:
            continue
        aw, ah, ar = int(m_avail.group(1)), int(m_avail.group(2)), float(m_avail.group(3))
        if cw == aw and ch == ah and abs(cr_str - ar) < 0.05:
            return norm_avail
    return None


@dataclass(slots=True)
class MonitorOutput:
    id: int
    name: str
    description: str
    make: str
    model: str
    serial: str
    width: int
    height: int
    refresh_rate: float
    current_mode: str
    available_modes: list[str]
    x: int
    y: int
    position: str
    scale: float
    scale_clean: bool
    scale_warning: str | None
    scale_options: list[dict[str, Any]]
    transform: int
    vrr: int
    disabled: bool
    mirror_of: str
    color_management_preset: str
    vrr_capable: bool
    hdr_capable: bool
    focused: bool = False
    reserved: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "make": self.make,
            "model": self.model,
            "serial": self.serial,
            "width": self.width,
            "height": self.height,
            "refresh_rate": self.refresh_rate,
            "current_mode": self.current_mode,
            "available_modes": list(self.available_modes),
            "x": self.x,
            "y": self.y,
            "position": self.position,
            "scale": self.scale,
            "scale_clean": self.scale_clean,
            "scale_warning": self.scale_warning,
            "scale_options": list(self.scale_options),
            "transform": self.transform,
            "vrr": self.vrr,
            "disabled": self.disabled,
            "mirror_of": self.mirror_of,
            "color_management_preset": self.color_management_preset,
            "vrr_capable": self.vrr_capable,
            "hdr_capable": self.hdr_capable,
            "focused": self.focused,
            "reserved": list(self.reserved),
        }


def _normalize_vrr(raw_vrr: Any) -> int:
    if isinstance(raw_vrr, bool):
        return 1 if raw_vrr else 0
    if isinstance(raw_vrr, int):
        return max(0, min(3, raw_vrr))
    return 0


def parse_monitors_json(raw_list: Sequence[Mapping[str, Any]]) -> list[MonitorOutput]:
    """Parse JSON list returned by `hyprctl monitors all -j`."""
    outputs: list[MonitorOutput] = []
    for item in raw_list:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        refresh = round(float(item.get("refreshRate") or 0.0), 3)
        avail = [str(m) for m in (item.get("availableModes") or []) if str(m).strip()]
        raw_mode = f"{width}x{height}@{refresh:.2f}" if width > 0 and height > 0 else ""
        matched_mode = mode_matches_available(raw_mode, avail) if raw_mode and avail else None
        if matched_mode:
            current_mode = matched_mode
        elif raw_mode:
            current_mode = raw_mode
        elif avail:
            current_mode = normalize_mode_str(avail[0])
        else:
            current_mode = "preferred"

        x = int(item.get("x") or 0)
        y = int(item.get("y") or 0)
        scale = round(float(item.get("scale") or 1.0), 4)
        if width > 0 and height > 0:
            clean = is_clean_scale(width, height, scale)
            scale_options = build_scale_options(width, height, scale)
        else:
            clean = True
            scale_options = build_scale_options(1920, 1080, scale)

        hw = item.get("hardwareDetails")
        if not isinstance(hw, Mapping):
            hw = {}
        mirror_raw = str(item.get("mirrorOf") or "none").strip() or "none"

        outputs.append(
            MonitorOutput(
                id=int(item.get("id") or 0),
                name=name,
                description=str(item.get("description") or ""),
                make=str(item.get("make") or ""),
                model=str(item.get("model") or ""),
                serial=str(item.get("serial") or ""),
                width=width,
                height=height,
                refresh_rate=refresh,
                current_mode=current_mode,
                available_modes=avail,
                x=x,
                y=y,
                position=f"{x}x{y}",
                scale=scale,
                scale_clean=clean,
                scale_warning=None if clean else "fractional: may blur",
                scale_options=scale_options,
                transform=int(item.get("transform") or 0),
                vrr=_normalize_vrr(item.get("vrr", 0)),
                disabled=bool(item.get("disabled", False)),
                mirror_of=mirror_raw,
                color_management_preset=str(item.get("colorManagementPreset") or "srgb"),
                vrr_capable=bool(hw.get("vrrCapable", False)),
                hdr_capable=bool(hw.get("hdr", False)),
                focused=bool(item.get("focused", False)),
                reserved=[int(v) for v in (item.get("reserved") or [])],
            )
        )
    return outputs


def probe_monitors(
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    fixture_path: str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = 5.0,
) -> list[MonitorOutput]:
    """Query `hyprctl monitors all -j` (or read fixture JSON if specified)."""
    environ = env if env is not None else os.environ
    eff_fixture = fixture_path or environ.get(ENV_SETTINGS_MONITORS_FIXTURE, "").strip()
    if eff_fixture:
        with open(os.path.expanduser(eff_fixture), "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError(f"Monitor fixture must contain a JSON array: {eff_fixture}")
        return parse_monitors_json(data)

    run_fn = runner if runner is not None else subprocess.run
    proc = run_fn(
        ["hyprctl", "monitors", "all", "-j"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"`hyprctl monitors all -j` exited with {proc.returncode}: {detail}")
    data = json.loads(proc.stdout or "[]")
    if not isinstance(data, list):
        raise RuntimeError("`hyprctl monitors all -j` returned non-array JSON")
    return parse_monitors_json(data)


def _extract_balanced_braces(src: str, start_brace: int) -> tuple[str, int] | None:
    depth = 0
    in_quote = False
    escaped = False
    i = start_brace
    n = len(src)
    while i < n:
        ch = src[i]
        if in_quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_quote = False
        else:
            if ch == '"':
                in_quote = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return src[start_brace : i + 1], i + 1
        i += 1
    return None


def extract_monitors_overrides(overrides_text: str) -> dict[str, dict[str, Any]]:
    """Extract {output_name: {field: value}} from the 'monitors' section of hks-overrides.lua."""
    if not overrides_text.strip():
        return {}
    sections = parse_sections(overrides_text)
    body = sections.get(MONITORS_SECTION_NAME)
    if not body:
        return {}
    result: dict[str, dict[str, Any]] = {}
    pos = 0
    while pos < len(body):
        m = _MONITOR_CALL_RE.search(body, pos)
        if not m:
            break
        extracted = _extract_balanced_braces(body, m.start(1))
        if not extracted:
            break
        table_src, next_pos = extracted
        pos = next_pos
        try:
            tokens = _tokenize_lua_table(table_src)
            parsed, _ = _parse_lua_literal(tokens, 0)
        except Exception:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("output"), str):
            out_name = parsed["output"].strip()
            if out_name:
                result[out_name] = parsed
    return result


def get_display_state(
    *,
    config_dir: str | None = None,
    entrypoint: str | None = None,
    no_live: bool = False,
    enable_ddc: bool = False,
    monitors_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    brightness_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    fixture_path: str | None = None,
    state_dir: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Assemble full Display settings state (monitors, overrides, brightness, active guard)."""
    environ = env if env is not None else os.environ
    disc = discover_config(
        config_dir=config_dir,
        entrypoint=entrypoint,
        no_live=no_live,
        env=dict(environ),
    )
    env_info = disc.environment

    include_installed = False
    if env_info.language == "lua" and os.path.isfile(env_info.entrypoint):
        try:
            with open(env_info.entrypoint, "r", encoding="utf-8") as f:
                include_installed = has_include(f.read())
        except IncludeBlockError:
            include_installed = False

    ov_path = os.path.join(env_info.config_dir, OVERRIDES_FILENAME)
    ov_present = os.path.isfile(ov_path)
    ov_sha = compute_file_sha256(ov_path) if ov_present else SHA256_ABSENT
    monitor_overrides: dict[str, dict[str, Any]] = {}
    if ov_present:
        with open(ov_path, "r", encoding="utf-8") as f:
            try:
                monitor_overrides = extract_monitors_overrides(f.read())
            except OverridesError:
                monitor_overrides = {}

    outputs_error: str | None = None
    outputs: list[MonitorOutput] = []
    if not no_live or monitors_runner is not None or fixture_path or environ.get(ENV_SETTINGS_MONITORS_FIXTURE):
        try:
            outputs = probe_monitors(
                runner=monitors_runner,
                fixture_path=fixture_path,
                env=environ,
            )
        except Exception as exc:
            outputs_error = str(exc)

    brightness = read_brightness(
        runner=brightness_runner,
        enable_ddc=enable_ddc,
    )

    active_guard: dict[str, Any] | None = None
    loaded = load_active_handle(state_dir=state_dir, env=environ)
    if loaded is not None:
        handle, deadline_epoch, timeout_seconds = loaded
        if handle.pid > 0 and _pid_alive(handle.pid) and not os.path.exists(handle.confirm_path):
            active_guard = {
                "pid": handle.pid,
                "deadline_epoch": deadline_epoch,
                "timeout_seconds": timeout_seconds,
                "plan_path": handle.plan_path,
            }

    return {
        "config_dir": env_info.config_dir,
        "entrypoint": env_info.entrypoint,
        "include_installed": include_installed,
        "overrides_path": ov_path,
        "overrides_present": ov_present,
        "overrides_sha256": ov_sha,
        "outputs": [o.to_dict() for o in outputs],
        "outputs_error": outputs_error,
        "monitor_overrides": monitor_overrides,
        "brightness": brightness.to_dict(),
        "active_guard": active_guard,
    }
