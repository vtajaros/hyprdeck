"""Hyprland submap coordinator for interactive keybind recording (Phase 3b)."""

from __future__ import annotations

import json
import logging
import os
import select
import signal
import subprocess
import sys
import threading
from typing import Any, Callable

_logger = logging.getLogger("hks.recorder")
DEFAULT_WATCHDOG_TIMEOUT = 20.0
MAX_LEAVE_RETRIES = 3

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


def spawn_detached_watchdog(
    submap_name: str = HKS_RECORD_SUBMAP,
    language: str = "lua",
    timeout_seconds: float = DEFAULT_WATCHDOG_TIMEOUT,
    watch_pid: int | None = None,
) -> tuple[bool, int | None, str]:
    """Spawn an independent setsid watchdog and wait for its READY signal."""
    read_fd, write_fd = os.pipe()
    target_pid = watch_pid if watch_pid is not None else os.getppid()
    cmd = [
        sys.executable,
        "-m",
        "backend.editor.recorder_watchdog",
        "--submap",
        submap_name,
        "--language",
        language,
        "--timeout",
        str(timeout_seconds),
        "--watch-pid",
        str(target_pid),
        "--ready-fd",
        str(write_fd),
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
            pass_fds=(write_fd,),
        )
    except OSError as exc:
        try:
            os.close(read_fd)
        except OSError:
            pass
        try:
            os.close(write_fd)
        except OSError:
            pass
        return False, None, f"Failed to spawn detached watchdog: {exc}"

    try:
        os.close(write_fd)
    except OSError:
        pass

    ready_data = b""
    try:
        rlist, _, _ = select.select([read_fd], [], [], 2.0)
        if rlist:
            ready_data = os.read(read_fd, 16)
    except OSError:
        ready_data = b""
    finally:
        try:
            os.close(read_fd)
        except OSError:
            pass

    if not ready_data.startswith(b"READY") or proc.poll() is not None:
        return False, None, "Detached watchdog did not confirm readiness"
    return True, proc.pid, ""


def enter(
    language: str = "lua",
    submap_name: str = HKS_RECORD_SUBMAP,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    dummy_key: str | None = None,
    watch_pid: int | None = None,
    watchdog_timeout: float = DEFAULT_WATCHDOG_TIMEOUT,
    watchdog_spawner: Callable[..., tuple[bool, int | None, str]] | None = None,
) -> dict[str, Any]:
    """Enter the recorder submap after confirming a detached watchdog is running."""
    run_fn = runner if runner is not None else subprocess.run

    if watchdog_spawner is not None:
        wd_ok, wd_pid, wd_err = watchdog_spawner(
            submap_name=submap_name,
            language=language,
            timeout_seconds=watchdog_timeout,
            watch_pid=watch_pid,
        )
    elif runner is None:
        wd_ok, wd_pid, wd_err = spawn_detached_watchdog(
            submap_name=submap_name,
            language=language,
            timeout_seconds=watchdog_timeout,
            watch_pid=watch_pid,
        )
    else:
        # Unit tests passing a mocked runner without a custom spawner must not spawn a real OS watchdog.
        wd_ok, wd_pid, wd_err = True, None, ""

    if not wd_ok:
        _logger.error("Refusing to enter recorder submap '%s': %s", submap_name, wd_err)
        return {
            "ok": False,
            "strategy": "limited",
            "reason": f"Watchdog failed to start ({wd_err}); refusing to enter submap",
            "submap": "",
        }

    entered_submap = False
    interrupted_sig: list[int] = []
    old_handlers: dict[int, Any] = {}
    is_main_thread = threading.current_thread() is threading.main_thread()

    def _on_signal(signum: int, _frame: Any) -> None:
        interrupted_sig.append(signum)
        raise InterruptedError(f"Interrupted by signal {signum}")

    if is_main_thread:
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                old_handlers[sig] = signal.getsignal(sig)
                signal.signal(sig, _on_signal)
            except (OSError, ValueError):
                pass

    try:
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
                "watchdog_pid": wd_pid,
            }

        if proc.returncode == 0:
            entered_submap = True
            return {
                "ok": True,
                "strategy": "passthrough",
                "reason": "submap active",
                "submap": submap_name,
                "watchdog_pid": wd_pid,
            }

        err = (proc.stderr or proc.stdout or "").strip()
        return {
            "ok": True,
            "strategy": "limited",
            "reason": err or f"hyprctl dispatch returned {proc.returncode}",
            "submap": "",
            "watchdog_pid": wd_pid,
        }
    except BaseException:
        if entered_submap or get_submap(runner=run_fn) == submap_name:
            leave(language=language, runner=run_fn)
        raise
    finally:
        if interrupted_sig and (entered_submap or get_submap(runner=run_fn) == submap_name):
            leave(language=language, runner=run_fn)
        if is_main_thread:
            for sig, handler in old_handlers.items():
                try:
                    signal.signal(sig, handler)
                except (OSError, ValueError):
                    pass


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

    last_exc: Exception | None = None
    for attempt in range(1, MAX_LEAVE_RETRIES + 1):
        try:
            run_fn(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
                timeout=5.0,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            last_exc = exc
            _logger.warning("Attempt %d/%d to leave submap failed: %s", attempt, MAX_LEAVE_RETRIES, exc)
            continue

        after = get_submap(runner=run_fn)
        if after in ("", "default"):
            break
        _logger.warning("Attempt %d/%d to leave submap: still in '%s'", attempt, MAX_LEAVE_RETRIES, after)
    else:
        if last_exc is not None:
            return {
                "ok": False,
                "action": "leave",
                "message": f"Failed to execute hyprctl after {MAX_LEAVE_RETRIES} attempts: {last_exc}",
            }
        after = get_submap(runner=run_fn)
        return {
            "ok": False,
            "action": "leave",
            "message": f"Failed to return to default submap after {MAX_LEAVE_RETRIES} attempts; still in '{after}'",
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
