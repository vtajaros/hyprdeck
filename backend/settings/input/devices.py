"""Per-device probing (`hyprctl devices -j`), virtual heuristics, validation, and Lua generation."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from backend.core.constants import DEVICES_SECTION_NAME, ENV_SETTINGS_DEVICES_FIXTURE
from backend.core.overrides import parse_sections
from backend.editor.codegen import encode_lua_string
from backend.settings.state import _parse_lua_literal, _tokenize_lua_table

# Verified live via `Hyprland --verify-config` on Hyprland 0.57.1.
# Note: `force_no_accel` is NOT accepted by `hl.device` on 0.57.1 (`unknown field 'force_no_accel'`).
SUPPORTED_DEVICE_KEYS: frozenset[str] = frozenset(
    {
        "enabled",
        "sensitivity",
        "accel_profile",
        "natural_scroll",
        "scroll_factor",
        "left_handed",
        "tap_to_click",
        "disable_while_typing",
        "clickfinger_behavior",
        "middle_button_emulation",
        "drag_lock",
        "kb_layout",
        "kb_variant",
        "kb_options",
        "repeat_rate",
        "repeat_delay",
        "numlock_by_default",
    }
)

_DEVICE_CALL_RE = re.compile(r"hl\.device\s*\(\s*(\{)")

_VIRTUAL_NAME_EXACT: frozenset[str] = frozenset(
    {
        "power-button",
        "sleep-button",
        "video-bus",
        "lid-switch",
        "lid switch",
    }
)

_VIRTUAL_NAME_TOKENS: tuple[tuple[str, str], ...] = (
    ("power-button", "system power button"),
    ("sleep-button", "system sleep button"),
    ("video-bus", "ACPI video bus"),
    ("lid switch", "ACPI lid switch"),
    ("intel-hid", "ACPI HID event device"),
    ("wmi-hotkeys", "vendor WMI hotkey interface"),
    ("input-remapper", "virtual input-remapper device"),
    ("(avrcp)", "Bluetooth AVRCP media control"),
    ("headset", "headset/audio jack button interface"),
    ("ydotoold", "virtual ydotool device"),
    ("virtual-", "virtual device"),
)


def classify_virtual_device(name: str, category: str) -> tuple[bool, str | None]:
    """Classify virtual/noise devices (ACPI buttons, WMI hotkeys, AVRCP, secondary HID mouse-kbd)."""
    if category == "switch":
        return True, "hardware switch"
    low = name.strip().lower()
    if low in _VIRTUAL_NAME_EXACT:
        return True, "ACPI/system button"
    for tok, reason in _VIRTUAL_NAME_TOKENS:
        if tok in low:
            return True, reason
    if category == "mouse" and "keyboard" in low:
        return True, "secondary keyboard consumer/mouse HID interface"
    return False, None


@dataclass(slots=True)
class InputDevice:
    address: str
    name: str
    category: str  # "keyboard" | "mouse" | "touchpad" | "tablet" | "touch" | "switch"
    is_virtual: bool = False
    virtual_reason: str | None = None
    main: bool = False
    layout: str = ""
    variant: str = ""
    options: str = ""
    active_keymap: str = ""
    default_speed: float = 0.0
    scroll_factor: float = -1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "name": self.name,
            "category": self.category,
            "is_virtual": self.is_virtual,
            "virtual_reason": self.virtual_reason,
            "main": self.main,
            "layout": self.layout,
            "variant": self.variant,
            "options": self.options,
            "active_keymap": self.active_keymap,
            "default_speed": self.default_speed,
            "scroll_factor": self.scroll_factor,
        }


@dataclass(slots=True)
class DeviceRuleSpec:
    name: str
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name}
        d.update(self.properties)
        return d


def _is_touchpad_name(name: str) -> bool:
    low = name.lower()
    return any(tok in low for tok in ("touchpad", "trackpad", "synaptics"))


def parse_devices_json(raw_obj: Mapping[str, Any]) -> list[InputDevice]:
    """Parse JSON object returned by `hyprctl devices -j`."""
    devices: list[InputDevice] = []

    for item in raw_obj.get("keyboards") or []:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        virt, reason = classify_virtual_device(name, "keyboard")
        devices.append(
            InputDevice(
                address=str(item.get("address") or ""),
                name=name,
                category="keyboard",
                is_virtual=virt,
                virtual_reason=reason,
                main=bool(item.get("main", False)),
                layout=str(item.get("layout") or ""),
                variant=str(item.get("variant") or ""),
                options=str(item.get("options") or ""),
                active_keymap=str(item.get("active_keymap") or ""),
            )
        )

    for item in raw_obj.get("mice") or []:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        cat = "touchpad" if _is_touchpad_name(name) else "mouse"
        virt, reason = classify_virtual_device(name, cat)
        devices.append(
            InputDevice(
                address=str(item.get("address") or ""),
                name=name,
                category=cat,
                is_virtual=virt,
                virtual_reason=reason,
                default_speed=float(item.get("defaultSpeed") or 0.0),
                scroll_factor=float(item.get("scrollFactor") or -1.0),
            )
        )

    for group_key, cat in (("tablets", "tablet"), ("touch", "touch"), ("switches", "switch")):
        for item in raw_obj.get(group_key) or []:
            if not isinstance(item, Mapping):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            virt, reason = classify_virtual_device(name, cat)
            devices.append(
                InputDevice(
                    address=str(item.get("address") or ""),
                    name=name,
                    category=cat,
                    is_virtual=virt,
                    virtual_reason=reason,
                )
            )

    return devices


def probe_devices(
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    fixture_path: str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = 5.0,
) -> list[InputDevice]:
    """Query `hyprctl devices -j` (or read fixture JSON if specified)."""
    environ = env if env is not None else os.environ
    eff_fixture = fixture_path or environ.get(ENV_SETTINGS_DEVICES_FIXTURE, "").strip()
    if eff_fixture:
        with open(os.path.expanduser(eff_fixture), "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, Mapping):
            raise ValueError(f"Devices fixture must contain a JSON object: {eff_fixture}")
        return parse_devices_json(data)

    run_fn = runner if runner is not None else subprocess.run
    proc = run_fn(
        ["hyprctl", "devices", "-j"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"`hyprctl devices -j` exited with {proc.returncode}: {detail}")
    data = json.loads(proc.stdout or "{}")
    if not isinstance(data, Mapping):
        raise RuntimeError("`hyprctl devices -j` returned non-object JSON")
    return parse_devices_json(data)


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


def extract_devices_overrides(text: str) -> dict[str, dict[str, Any]]:
    """Extract `{device_name: {prop: val}}` from the 'devices' overrides section."""
    sections = parse_sections(text)
    body = sections.get(DEVICES_SECTION_NAME)
    if not body:
        return {}
    out: dict[str, dict[str, Any]] = {}
    pos = 0
    while True:
        m = _DEVICE_CALL_RE.search(body, pos)
        if not m:
            break
        extracted = _extract_balanced_braces(body, m.start(1))
        if not extracted:
            break
        tbl_src, pos = extracted
        tokens = _tokenize_lua_table(tbl_src)
        parsed, _ = _parse_lua_literal(tokens, 0)
        if isinstance(parsed, dict) and isinstance(parsed.get("name"), str):
            dev_name = parsed["name"]
            props = {k: v for k, v in parsed.items() if k != "name"}
            out[dev_name] = props
    return out


def validate_device_rules(
    changes: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    current_devices: Sequence[InputDevice],
    existing_overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[list[DeviceRuleSpec], list[str]]:
    """Validate per-device rules against live devices and safety guards."""
    if isinstance(changes, Mapping):
        items = [dict(changes)] if "name" in changes else [
            {"name": k, **v} for k, v in changes.items() if isinstance(v, Mapping)
        ]
    else:
        items = [dict(c) for c in changes if isinstance(c, Mapping)]

    by_name = {d.name: d for d in current_devices}
    errors: list[str] = []
    specs_by_name: dict[str, DeviceRuleSpec] = {}

    for dev_name, props in (existing_overrides or {}).items():
        if isinstance(props, Mapping):
            specs_by_name[dev_name] = DeviceRuleSpec(name=dev_name, properties=dict(props))

    for item in items:
        raw_name = item.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            errors.append("Each device rule must specify a non-empty 'name'.")
            continue
        dev_name = raw_name
        if dev_name not in by_name:
            errors.append(f"Unknown input device {dev_name!r}.")
            continue

        clean_props: dict[str, Any] = {}
        for k, v in item.items():
            if k == "name" or v is None:
                continue
            if k not in SUPPORTED_DEVICE_KEYS:
                errors.append(f"Device {dev_name!r}: unsupported hl.device property {k!r}.")
                continue
            if k in ("enabled", "natural_scroll", "left_handed", "tap_to_click", "disable_while_typing", "clickfinger_behavior", "middle_button_emulation", "numlock_by_default"):
                if not isinstance(v, bool):
                    errors.append(f"Device {dev_name!r}: {k!r} must be a boolean.")
                    continue
            elif k in ("sensitivity", "scroll_factor"):
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    errors.append(f"Device {dev_name!r}: {k!r} must be a number.")
                    continue
                v = float(v)
            elif k in ("drag_lock", "repeat_rate", "repeat_delay"):
                if isinstance(v, bool) or not isinstance(v, int):
                    errors.append(f"Device {dev_name!r}: {k!r} must be an integer.")
                    continue
            elif k in ("accel_profile", "kb_layout", "kb_variant", "kb_options"):
                if not isinstance(v, str):
                    errors.append(f"Device {dev_name!r}: {k!r} must be a string.")
                    continue
                if "\x00" in v or "\n" in v or "\r" in v:
                    errors.append(f"Device {dev_name!r}: {k!r} contains forbidden control chars.")
                    continue
            clean_props[k] = v

        if clean_props:
            specs_by_name[dev_name] = DeviceRuleSpec(name=dev_name, properties=clean_props)
        elif dev_name in specs_by_name:
            del specs_by_name[dev_name]

    if errors:
        return [], errors

    # Safety guards: refuse disabling the last enabled keyboard or last enabled pointing device.
    kbds = [d for d in current_devices if d.category == "keyboard"]
    real_kbds = [d for d in kbds if not d.is_virtual]
    kbd_pool = real_kbds if real_kbds else kbds
    if kbd_pool:
        enabled_kbds = sum(
            1
            for d in kbd_pool
            if specs_by_name.get(d.name, DeviceRuleSpec(d.name)).properties.get("enabled", True) is not False
        )
        if enabled_kbds < 1:
            errors.append(
                "Cannot disable the last enabled keyboard; at least one keyboard must remain enabled."
            )

    ptrs = [d for d in current_devices if d.category in ("mouse", "touchpad")]
    real_ptrs = [d for d in ptrs if not d.is_virtual]
    ptr_pool = real_ptrs if real_ptrs else ptrs
    if ptr_pool:
        enabled_ptrs = sum(
            1
            for d in ptr_pool
            if specs_by_name.get(d.name, DeviceRuleSpec(d.name)).properties.get("enabled", True) is not False
        )
        if enabled_ptrs < 1:
            errors.append(
                "Cannot disable the last enabled pointing device; at least one mouse or touchpad must remain enabled."
            )

    if errors:
        return [], errors

    ordered = [specs_by_name[k] for k in sorted(specs_by_name.keys()) if specs_by_name[k].properties]
    return ordered, []


def _encode_lua_val(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, str):
        return encode_lua_string(v)
    raise ValueError(f"Unsupported device property type: {type(v).__name__}")


def render_devices_section(rules: Sequence[DeviceRuleSpec]) -> str:
    """Render deterministic `hl.device({...})` calls for the 'devices' overrides section."""
    blocks: list[str] = []
    for r in sorted(rules, key=lambda spec: spec.name):
        if not r.properties:
            continue
        lines = [
            "hl.device({",
            f"    name = {encode_lua_string(r.name)},",
        ]
        for k in sorted(r.properties.keys()):
            lines.append(f"    {k} = {_encode_lua_val(r.properties[k])},")
        lines.append("})")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
