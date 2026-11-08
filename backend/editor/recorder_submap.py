"""Hyprland submap coordinator for interactive keybind recording (Phase 3b)."""

from __future__ import annotations

import json
import subprocess
from typing import Any, Callable

HKS_RECORD_SUBMAP = "hks_record"

DUMMY_KEY_CANDIDATES = [
    "XF86Tools",
    "XF86Launch5",
    "XF86Launch6",
    "XF86Launch7",
    "XF86Launch8",
    "XF86Launch9",
    "XF86Explorer",
    "XF86Shop",
]


def get_submap(
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> str:
    """Query the active Hyprland submap name via `hyprctl submap`."""
    run_fn = runner if runner is not None else subprocess.run
    try:
        proc = run_fn(
            ["hyprctl", "submap"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
    except (OSError, subprocess.SubprocessError):
        return ""

    if proc.returncode != 0:
        return ""

    out = (proc.stdout or "").strip()
    return out


def get_free_dummy_key(
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> str:
    """Find a candidate key not bound in any non-recorder submap."""
    run_fn = runner if runner is not None else subprocess.run
    bound_keys: set[str] = set()
    try:
        proc = run_fn(
            ["hyprctl", "binds", "-j"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
        if proc.returncode == 0 and proc.stdout:
            data = json.loads(proc.stdout)
            if isinstance(data, list):
                for b in data:
                    if isinstance(b, dict) and b.get("submap") != HKS_RECORD_SUBMAP:
                        k = b.get("key")
                        if isinstance(k, str):
                            bound_keys.add(k.lower())
    except (OSError, subprocess.SubprocessError, ValueError):
        pass

    for cand in DUMMY_KEY_CANDIDATES:
        if cand.lower() not in bound_keys:
            return cand
    return "XF86Launch9"


def _ensure_lua_submap_registered(
    submap_name: str,
    runner: Callable[..., subprocess.CompletedProcess[str]],
    dummy_key: str | None = None,
) -> bool:
    """Strategy A: Dynamically register submap with a dummy safe reset bind via hyprctl eval."""
    key = dummy_key or get_free_dummy_key(runner)
    script = (
        f'hl.define_submap("{submap_name}", function() '
        f'hl.bind("", "{key}", hl.dsp.submap("reset")) '
        f'end)'
    )
    try:
        proc = runner(
            ["hyprctl", "eval", script],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def enter(
    language: str = "lua",
    submap_name: str = HKS_RECORD_SUBMAP,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    dummy_key: str | None = None,
) -> dict[str, Any]:
    """Enter the recorder submap using Strategy A (runtime registration) with limited mode fallback."""
    run_fn = runner if runner is not None else subprocess.run

    # If Lua, ensure submap is registered at runtime (Strategy A)
    if language == "lua":
        _ensure_lua_submap_registered(submap_name, run_fn, dummy_key=dummy_key)
        cmd = ["hyprctl", "dispatch", f'hl.dsp.submap("{submap_name}")']
    else:
        cmd = ["hyprctl", "dispatch", "submap", submap_name]

    try:
        proc = run_fn(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "ok": True,
            "strategy": "limited",
            "reason": f"Failed to execute hyprctl: {exc}",
            "submap": "",
        }

    if proc.returncode == 0:
        return {
            "ok": True,
            "strategy": "passthrough",
            "reason": "submap active",
            "submap": submap_name,
        }

    err = (proc.stderr or proc.stdout or "").strip()
    return {
        "ok": True,
        "strategy": "limited",
        "reason": err or f"hyprctl dispatch returned {proc.returncode}",
        "submap": "",
    }


def leave(
    language: str = "lua",
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    """Leave the recorder submap and return to default (idempotent with verification)."""
    run_fn = runner if runner is not None else subprocess.run
    curr = get_submap(runner=run_fn)
    if curr in ("", "default"):
        return {"ok": True, "action": "leave", "message": "already in default submap"}

    if language == "lua":
        cmd = ["hyprctl", "dispatch", 'hl.dsp.submap("reset")']
    else:
        cmd = ["hyprctl", "dispatch", "submap", "reset"]

    try:
        proc = run_fn(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "action": "leave", "message": f"Failed to execute hyprctl: {exc}"}

    # Verify status returned to default; retry once if needed
    after = get_submap(runner=run_fn)
    if after not in ("", "default"):
        run_fn(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False, timeout=3.0)
        after = get_submap(runner=run_fn)
        if after not in ("", "default"):
            return {
                "ok": False,
                "action": "leave",
                "message": f"Failed to return to default submap; still in '{after}'",
            }

    # Clean up dummy bind if Lua by finding which keys belong to hks_record
    if language == "lua":
        try:
            binds_proc = run_fn(
                ["hyprctl", "binds", "-j"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
                timeout=3.0,
            )
            keys_to_unbind = set()
            if binds_proc.returncode == 0 and binds_proc.stdout:
                data = json.loads(binds_proc.stdout)
                if isinstance(data, list):
                    for b in data:
                        if isinstance(b, dict) and b.get("submap") == HKS_RECORD_SUBMAP:
                            k = b.get("key")
                            if isinstance(k, str) and k:
                                keys_to_unbind.add(k)

            for key in keys_to_unbind:
                run_fn(
                    ["hyprctl", "repl", f'hl.unbind("{key}")'],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=3.0,
                )
        except (OSError, subprocess.SubprocessError, ValueError):
            pass

    return {"ok": True, "action": "leave", "message": "ok"}


def status(
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    """Return the current active Hyprland submap."""
    curr = get_submap(runner=runner)
    return {"ok": True, "action": "status", "submap": curr if curr else "default"}


def heal(
    language: str = "lua",
    submap_name: str = HKS_RECORD_SUBMAP,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    """Reset to default submap if and only if the current submap is `submap_name`."""
    run_fn = runner if runner is not None else subprocess.run
    curr = get_submap(runner=run_fn)
    if curr == submap_name:
        return leave(language=language, runner=run_fn)
    return {
        "ok": True,
        "action": "heal",
        "submap": curr if curr else "default",
        "message": f"no healing needed (current submap is {curr!r})",
    }
