"""Read-only state inspection for the Keyboard Shortcuts launcher page."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from backend.core.constants import ENV_HKS_WINDOW_SCRIPT
from backend.core.live_cmd import (
    DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
    LiveRunner,
    run_live_cmd,
)

HKS_WINDOW_TITLE = "HyprDeck Keybind Studio"
HKS_WINDOW_CLASS = "org.quickshell"


def resolve_keyboard_paths(
    script_path: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Resolve repo root, frontend dir, and hks-window launcher script path."""
    repo_root = str(Path(__file__).resolve().parents[3])
    frontend_dir = str(Path(repo_root) / "frontend")
    if script_path is not None:
        raw_script = script_path.strip()
    else:
        env_map = os.environ if env is None else env
        raw_script = env_map.get(ENV_HKS_WINDOW_SCRIPT, "").strip()
        if not raw_script:
            raw_script = str(Path(repo_root) / "scripts" / "hks-window")

    resolved_script = os.path.abspath(raw_script) if raw_script else ""
    return {
        "repo_root": repo_root,
        "frontend_dir": frontend_dir,
        "script_path": resolved_script,
    }


def check_script_available(script_path: str) -> bool:
    """Return True if *script_path* exists as a regular file and is executable."""
    if not script_path:
        return False
    path = Path(script_path)
    return path.is_file() and os.access(path, os.X_OK)


def parse_hyprctl_clients_for_hks(raw: str) -> bool | None:
    """Parse ``hyprctl clients -j`` output and report whether HKS window is mapped.

    Returns ``True`` if mapped, ``False`` if JSON parsed cleanly without a mapped
    HKS window, or ``None`` if *raw* cannot be parsed as a JSON client list.
    """
    if not raw or not raw.strip():
        return None
    try:
        clients = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(clients, list):
        return None

    for client in clients:
        if not isinstance(client, dict):
            continue
        if (
            client.get("title") == HKS_WINDOW_TITLE
            and client.get("class") == HKS_WINDOW_CLASS
            and bool(client.get("mapped", True))
        ):
            return True
    return False


def probe_hks_window_open(
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> bool | None:
    """Query Hyprland clients to check whether the HKS window is currently mapped."""
    res = run_live_cmd(["hyprctl", "clients", "-j"], timeout=timeout, runner=runner)
    if not res.ok:
        return None
    return parse_hyprctl_clients_for_hks(res.out)


def probe_hks_running(
    frontend_dir: str,
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> bool:
    """Return True if the crash-isolated HKS Quickshell process is running."""
    res = run_live_cmd(
        ["pgrep", "-f", f"[q]uickshell -p {frontend_dir}"],
        timeout=timeout,
        runner=runner,
    )
    return bool(res.ok)


def get_keyboard_state(
    *,
    script_path: str | None = None,
    runner: LiveRunner | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Collect availability and live window/daemon state for Keybind Studio."""
    paths = resolve_keyboard_paths(script_path=script_path, env=env)
    target_script = paths["script_path"]
    available = check_script_available(target_script)
    hks_window_open = probe_hks_window_open(runner=runner, timeout=timeout)
    hks_running = probe_hks_running(
        paths["frontend_dir"],
        runner=runner,
        timeout=timeout,
    )
    error: str | None = None
    if not available:
        error = f"Launcher script not available: {target_script}"
    return {
        "available": available,
        "script_path": target_script,
        "hks_window_open": hks_window_open,
        "hks_running": hks_running,
        "repo_root": paths["repo_root"],
        "error": error,
    }
