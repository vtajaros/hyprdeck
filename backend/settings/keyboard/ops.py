"""Operations for launching/focusing the separate Hyprland Keybind Studio window."""

from __future__ import annotations

from typing import Any, Mapping

from backend.core.live_cmd import LiveRunner, run_live_cmd
from backend.settings.keyboard.state import (
    check_script_available,
    resolve_keyboard_paths,
)

OPEN_HKS_TIMEOUT_SECONDS = 8.0


def open_hks(
    *,
    script_path: str | None = None,
    runner: LiveRunner | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = OPEN_HKS_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Launch or focus Keybind Studio via ``hks-window --open`` (never toggle)."""
    paths = resolve_keyboard_paths(script_path=script_path, env=env)
    target_script = paths["script_path"]
    if not check_script_available(target_script):
        return {
            "ok": False,
            "error": f"Launcher script missing or not executable: {target_script}",
            "window_open_after": None,
        }

    res = run_live_cmd([target_script, "--open"], timeout=timeout, runner=runner)
    if res.timed_out:
        return {
            "ok": False,
            "error": "HKS window did not appear",
            "window_open_after": False,
        }
    if not res.ok:
        detail = (res.err or res.out or f"Command exited with status {res.rc}").strip()
        return {
            "ok": False,
            "error": detail,
            "window_open_after": False,
        }
    return {
        "ok": True,
        "error": None,
        "window_open_after": True,
    }
