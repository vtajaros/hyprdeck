"""Power (battery, CPU EPP/turbo, hypridle, lid/sleep) and System Info."""

from backend.settings.power.ops import (
    HELPER_PATH,
    MAX_IDLE_TIMEOUT,
    MIN_IDLE_TIMEOUT,
    rewrite_hypridle_timeouts,
    set_epp,
    set_idle_timeouts,
    set_lid_action,
    set_turbo,
)
from backend.settings.power.state import (
    classify_listener_role,
    get_power_state,
    get_system_info,
    parse_hypridle_conf,
    probe_battery,
    probe_cpu,
    probe_hypridle,
    probe_lid_sleep,
    read_per_cpu_epp,
    read_turbo_enabled,
    resolve_power_paths,
)

__all__ = [
    "HELPER_PATH",
    "MAX_IDLE_TIMEOUT",
    "MIN_IDLE_TIMEOUT",
    "classify_listener_role",
    "get_power_state",
    "get_system_info",
    "parse_hypridle_conf",
    "probe_battery",
    "probe_cpu",
    "probe_hypridle",
    "probe_lid_sleep",
    "read_per_cpu_epp",
    "read_turbo_enabled",
    "resolve_power_paths",
    "rewrite_hypridle_timeouts",
    "set_epp",
    "set_idle_timeouts",
    "set_lid_action",
    "set_turbo",
]
