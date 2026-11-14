"""Input settings backend (XKB layouts, per-device rules, and confirm-flow commit)."""

from backend.settings.input.apply_flow import (
    InputApplyResult,
    apply_input_changes,
    confirm_input_changes,
    get_input_state,
    revert_input_changes,
)
from backend.settings.input.devices import (
    SUPPORTED_DEVICE_KEYS,
    DeviceRuleSpec,
    InputDevice,
    extract_devices_overrides,
    parse_devices_json,
    probe_devices,
    render_devices_section,
    validate_device_rules,
)
from backend.settings.input.xkb import (
    NON_LATIN_LAYOUTS,
    XkbRules,
    load_xkb_rules,
    parse_evdev_lst,
    validate_keyboard_layout,
)

__all__ = [
    "DeviceRuleSpec",
    "InputApplyResult",
    "InputDevice",
    "NON_LATIN_LAYOUTS",
    "SUPPORTED_DEVICE_KEYS",
    "XkbRules",
    "apply_input_changes",
    "confirm_input_changes",
    "extract_devices_overrides",
    "get_input_state",
    "load_xkb_rules",
    "parse_devices_json",
    "parse_evdev_lst",
    "probe_devices",
    "render_devices_section",
    "revert_input_changes",
    "validate_device_rules",
    "validate_keyboard_layout",
]
