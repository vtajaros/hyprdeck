"""Detached OS-level confirm-or-revert watchdog for HyprDeck managed changes.

This is the primitive the future Display page uses for its 15-second
confirm-or-revert safety net. Runs in its own session (`start_new_session=True`)
so it survives UI/backend crashes and safely reverts unless confirmed.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
from typing import Any

from backend.core.transaction import run_reload_and_check
from backend.editor.backups import (
    BackupConflictError,
    BackupError,
    compute_file_sha256,
    restore_backup,
)


def _pid_alive(pid: int) -> bool:
    if pid <= 1:
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _append_log(log_path: str | None, msg: str) -> None:
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg.rstrip()}\n"
    if log_path:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line)
            return
        except OSError:
            pass
    try:
        sys.stderr.write(line)
        sys.stderr.flush()
    except OSError:
        pass


def run_revert_watchdog(
    plan_path: str,
    timeout_seconds: float = 15.0,
    watch_pid: int = 0,
    ready_fd: int | None = None,
    poll_interval: float = 0.05,
) -> int:
    """Signal readiness, wait for confirm/deadline/parent-exit, and idempotently revert if unconfirmed."""
    if ready_fd is not None and ready_fd >= 0:
        try:
            os.write(ready_fd, b"READY\n")
        finally:
            try:
                os.close(ready_fd)
            except OSError:
                pass

    with open(plan_path, "r", encoding="utf-8") as f:
        plan: dict[str, Any] = json.load(f)

    confirm_path = str(plan["confirm_path"])
    log_path = plan.get("log_path")
    target_path = str(plan["target_path"])
    expected_sha = str(plan["expected_current_sha256"])
    created = bool(plan.get("created", False))
    reload_mode = str(plan.get("reload_mode", "config-only"))
    backup_id = plan.get("backup_id")
    backup_dir = plan.get("backup_dir")

    deadline = time.monotonic() + max(0.01, timeout_seconds)
    confirmed = False
    while True:
        if os.path.exists(confirm_path):
            confirmed = True
            break
        if watch_pid > 1 and not _pid_alive(watch_pid):
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_interval, remaining))

    if confirmed or os.path.exists(confirm_path):
        _append_log(log_path, f"Confirmed: keeping change on {target_path}")
        return 0

    if created:
        if not os.path.exists(target_path):
            _append_log(log_path, f"Target already absent ({target_path}); revert is a no-op.")
            return 0
        cur_sha = compute_file_sha256(target_path)
        if cur_sha != expected_sha:
            _append_log(
                log_path,
                f"Concurrent modification on {target_path} (sha {cur_sha} != {expected_sha}); skipping revert.",
            )
            return 0
        os.unlink(target_path)
        _append_log(log_path, f"Reverted created file {target_path} (deleted).")
    else:
        if not backup_id:
            _append_log(log_path, f"Missing backup_id for {target_path}; cannot revert.")
            return 1
        try:
            restore_backup(
                str(backup_id),
                expected_current_sha256=expected_sha,
                backup_dir=str(backup_dir) if backup_dir else None,
            )
        except BackupConflictError as exc:
            _append_log(
                log_path,
                f"Concurrent modification or already reverted on {target_path}: {exc}",
            )
            return 0
        except BackupError as exc:
            _append_log(log_path, f"Revert failed for {target_path}: {exc}")
            return 1
        _append_log(log_path, f"Reverted {target_path} to backup {backup_id}.")

    if reload_mode != "none":
        ok, err = run_reload_and_check(reload_mode)
        if not ok:
            _append_log(log_path, f"Post-revert reload ({reload_mode}) failed: {err}")
            return 1
        _append_log(log_path, f"Post-revert reload ({reload_mode}) succeeded.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hyprdeck-revert-watchdog")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--watch-pid", type=int, default=0)
    parser.add_argument("--ready-fd", type=int, default=-1)
    parser.add_argument("--poll-interval", type=float, default=0.05)
    args = parser.parse_args(argv)
    return run_revert_watchdog(
        plan_path=args.plan,
        timeout_seconds=args.timeout,
        watch_pid=args.watch_pid,
        ready_fd=args.ready_fd if args.ready_fd >= 0 else None,
        poll_interval=args.poll_interval,
    )


if __name__ == "__main__":
    raise SystemExit(main())
