"""Detached OS-level watchdog for Hyprland recorder submap safety (Milestone 3b-8).

Runs in its own session (`setsid` / `start_new_session=True`) so it survives
crashes or `SIGKILL` of the HyprDeck UI or backend process. Resets the recorder
submap once when either the hard timeout expires or the watched parent PID
disappears, whichever comes first.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from backend.core.env import get_env
from backend.editor.recorder_submap import HYPRDECK_RECORD_SUBMAP, get_submap, leave


def _pid_alive(pid: int) -> bool:
    """Return True if `pid` currently exists."""
    if pid <= 1:
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _log_failure(msg: str) -> None:
    log_path = get_env("WATCHDOG_LOG")
    if log_path:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(msg.rstrip() + "\n")
            return
        except OSError:
            pass
    try:
        sys.stderr.write(msg.rstrip() + "\n")
        sys.stderr.flush()
    except OSError:
        pass


def run_watchdog(
    submap_name: str = HYPRDECK_RECORD_SUBMAP,
    language: str = "lua",
    timeout_seconds: float = 20.0,
    watch_pid: int = 0,
    ready_fd: int | None = None,
    poll_interval: float = 0.2,
) -> int:
    """Signal readiness, wait for timeout or parent exit, then idempotently reset submap."""
    if ready_fd is not None and ready_fd >= 0:
        try:
            os.write(ready_fd, b"READY\n")
        finally:
            try:
                os.close(ready_fd)
            except OSError:
                pass

    deadline = time.monotonic() + max(0.05, timeout_seconds)
    while True:
        if watch_pid > 1 and not _pid_alive(watch_pid):
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_interval, remaining))

    curr = get_submap()
    if curr != submap_name:
        return 0

    res = leave(language=language)
    if not res.get("ok"):
        _log_failure(f"hyprdeck watchdog: failed to reset submap '{submap_name}': {res.get('message')}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hyprdeck-recorder-watchdog")
    parser.add_argument("--submap", default=HYPRDECK_RECORD_SUBMAP)
    parser.add_argument("--language", default="lua")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--watch-pid", type=int, default=0)
    parser.add_argument("--ready-fd", type=int, default=-1)
    parser.add_argument("--poll-interval", type=float, default=0.2)
    args = parser.parse_args(argv)
    return run_watchdog(
        submap_name=args.submap,
        language=args.language,
        timeout_seconds=args.timeout,
        watch_pid=args.watch_pid,
        ready_fd=args.ready_fd if args.ready_fd >= 0 else None,
        poll_interval=args.poll_interval,
    )


if __name__ == "__main__":
    raise SystemExit(main())
