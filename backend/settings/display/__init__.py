"""Display (monitors + brightness) state, validation, and safe apply flow."""

from backend.settings.display.apply_flow import (
    DisplayApplyResult,
    MonitorRuleSpec,
    apply_display_changes,
    confirm_display_changes,
    render_monitors_section,
    revert_display_changes,
    validate_display_changes,
)
from backend.settings.display.brightness import (
    MAX_BRIGHTNESS_PERCENT,
    MIN_BRIGHTNESS_PERCENT,
    BrightnessInfo,
    clamp_brightness_percent,
    read_brightness,
    set_brightness,
)
from backend.settings.display.state import (
    MonitorOutput,
    get_display_state,
    is_clean_scale,
    mode_matches_available,
    parse_monitors_json,
    probe_monitors,
)

__all__ = [
    "BrightnessInfo",
    "DisplayApplyResult",
    "MAX_BRIGHTNESS_PERCENT",
    "MIN_BRIGHTNESS_PERCENT",
    "MonitorOutput",
    "MonitorRuleSpec",
    "apply_display_changes",
    "clamp_brightness_percent",
    "confirm_display_changes",
    "get_display_state",
    "is_clean_scale",
    "mode_matches_available",
    "parse_monitors_json",
    "probe_monitors",
    "read_brightness",
    "render_monitors_section",
    "revert_display_changes",
    "set_brightness",
    "validate_display_changes",
]
