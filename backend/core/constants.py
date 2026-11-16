"""Single source of truth for HKS app-owned names, markers, and state paths."""

from __future__ import annotations

OVERRIDES_FILENAME = "hks-overrides.lua"

APP_DISPLAY_NAME = "HyprDeck Settings"
SETTINGS_WINDOW_TITLE = "HyprDeck Settings"
SETTINGS_QUICKSHELL_DIR = "settings"

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
ACTIVE_GUARD_FILENAME = "active-guard.json"

MONITORS_SECTION_NAME = "monitors"
INPUT_SECTION_NAME = "input"
DEVICES_SECTION_NAME = "devices"

ENV_SETTINGS_DEBUG = "HKS_SETTINGS_DEBUG"
ENV_SETTINGS_CONFIG_DIR = "HKS_SETTINGS_CONFIG_DIR"
ENV_SETTINGS_RELOAD_MODE = "HKS_SETTINGS_RELOAD_MODE"
ENV_SETTINGS_MONITORS_FIXTURE = "HKS_SETTINGS_MONITORS_FIXTURE"
ENV_SETTINGS_DEVICES_FIXTURE = "HKS_SETTINGS_DEVICES_FIXTURE"
ENV_SETTINGS_XKB_PATH = "HKS_SETTINGS_XKB_PATH"
ENV_THEMES_HOME = "HKS_THEMES_HOME"
ENV_POWER_SYSFS_ROOT = "HKS_POWER_SYSFS_ROOT"
ENV_HYPRIDLE_PATH = "HKS_HYPRIDLE_PATH"
ENV_HKS_WINDOW_SCRIPT = "HKS_WINDOW_SCRIPT"

SHA256_ABSENT = "absent"


def section_begin_marker(name: str) -> str:
    """Return the BEGIN marker line for a named overrides section."""
    return f"{SECTION_BEGIN_PREFIX}{name}"


def section_end_marker(name: str) -> str:
    """Return the END marker line for a named overrides section."""
    return f"{SECTION_END_PREFIX}{name}"
