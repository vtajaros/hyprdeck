"""Single source of truth for HKS app-owned names, markers, and state paths."""

from __future__ import annotations

OVERRIDES_FILENAME = "hks-overrides.lua"

INCLUDE_BEGIN_MARKER = "-- HKS-OVERRIDES-BEGIN"
INCLUDE_END_MARKER = "-- HKS-OVERRIDES-END"

SECTION_BEGIN_PREFIX = "-- HKS-SECTION-BEGIN: "
SECTION_END_PREFIX = "-- HKS-SECTION-END: "

OVERRIDES_HEADER = (
    "-- Managed by Hyprland Keybind Studio. "
    "Content inside HKS-SECTION markers may be updated automatically.\n"
)

STATE_DIR_NAME = "hks"
REVERT_GUARD_SUBDIR = "revert-guard"
ENV_STATE_DIR = "HKS_STATE_DIR"
WATCHDOG_LOG_FILENAME = "revert-watchdog.log"

SHA256_ABSENT = "absent"


def section_begin_marker(name: str) -> str:
    """Return the BEGIN marker line for a named overrides section."""
    return f"{SECTION_BEGIN_PREFIX}{name}"


def section_end_marker(name: str) -> str:
    """Return the END marker line for a named overrides section."""
    return f"{SECTION_END_PREFIX}{name}"
