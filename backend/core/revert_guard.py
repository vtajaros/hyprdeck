"""Confirm-or-revert guard using a detached OS watchdog process.

This is the primitive the future Display settings page uses for its 15-second
confirm-or-revert safety net: after applying a display/config change, the UI
arms a revert guard and only calls `confirm(handle)` once the user clicks Keep.
If the user does not confirm before the deadline—or if the UI/backend process
crashes (`SIGKILL`)—the detached watchdog reverts the change automatically.
"""

from __future__ import annotations

import hashlib
import json
import os
import select
import signal
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from backend.core.constants import (
    ACTIVE_GUARD_FILENAME,
    ENV_SETTINGS_CONFIG_DIR,
    ENV_SETTINGS_DEBUG,
    ENV_STATE_DIR,
    REVERT_GUARD_SUBDIR,
    STATE_DIR_NAME,
    WATCHDOG_LOG_FILENAME,
)


class RevertGuardError(RuntimeError):
    """Raised when arming or managing the revert guard fails."""


@dataclass(slots=True)
class RevertGuardHandle:
    plan_path: str
    confirm_path: str
    log_path: str
    pid: int
    plan: dict[str, Any]


def resolve_debug_companion_dir(config_dir: str, leaf: str) -> str:
    """Return an isolated temp-dir companion path outside both $HOME and `config_dir`."""
    abs_cfg = os.path.abspath(os.path.expanduser(config_dir))
    digest = hashlib.sha256(abs_cfg.encode("utf-8")).hexdigest()[:12]
    return os.path.abspath(os.path.join(tempfile.gettempdir(), f"hks-debug-{digest}", leaf))


def resolve_state_dir(
    state_dir: str | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    """Resolve the revert-guard state directory ($HYPRDECK_STATE_DIR > $HKS_STATE_DIR > data_dir/revert-guard)."""
    from backend.core.data_migration import resolve_data_app_dir
    from backend.core.env import get_env, get_env_flag

    if state_dir:
        return os.path.abspath(os.path.expanduser(state_dir))
    environ = env if env is not None else os.environ
    override = get_env("STATE_DIR", environ=environ)
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if get_env_flag("SETTINGS_DEBUG", environ=environ):
        dbg_cfg = get_env("SETTINGS_CONFIG_DIR", environ=environ)
        if dbg_cfg:
            return resolve_debug_companion_dir(dbg_cfg, REVERT_GUARD_SUBDIR)
    return os.path.abspath(os.path.join(resolve_data_app_dir(environ), REVERT_GUARD_SUBDIR))


def _write_private_bytes(path: str, data: bytes) -> None:
    """Atomically write `data` to `path` with mode 0600 from creation."""
    abs_path = os.path.abspath(os.path.expanduser(path))
    parent = os.path.dirname(abs_path)
    os.makedirs(parent, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".hks-guard-", dir=parent)
    try:
        os.chmod(tmp_path, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, abs_path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


def arm(
    plan: Mapping[str, Any],
    timeout_seconds: float = 15.0,
    watch_pid: int | None = None,
    *,
    state_dir: str | None = None,
    env: Mapping[str, str] | None = None,
) -> RevertGuardHandle:
    """Write a private (0600) revert-plan JSON and spawn the detached revert watchdog."""
    resolved_state = resolve_state_dir(state_dir=state_dir, env=env)
    os.makedirs(resolved_state, exist_ok=True)

    guard_id = uuid.uuid4().hex[:12]
    plan_path = os.path.join(resolved_state, f"plan-{guard_id}.json")
    confirm_path = str(
        plan.get("confirm_path") or os.path.join(resolved_state, f"confirm-{guard_id}")
    )
    log_path = str(
        plan.get("log_path") or os.path.join(resolved_state, WATCHDOG_LOG_FILENAME)
    )

    plan_payload: dict[str, Any] = {
        "backup_id": plan.get("backup_id"),
        "backup_dir": plan.get("backup_dir"),
        "target_path": os.path.abspath(os.path.expanduser(str(plan["target_path"]))),
        "expected_current_sha256": str(plan["expected_current_sha256"]),
        "created": bool(plan.get("created", False)),
        "reload_mode": str(plan.get("reload_mode", "config-only")),
        "confirm_path": os.path.abspath(os.path.expanduser(confirm_path)),
        "log_path": os.path.abspath(os.path.expanduser(log_path)),
    }

    _write_private_bytes(
        plan_path,
        (json.dumps(plan_payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )

    target_pid = os.getpid() if watch_pid is None else int(watch_pid)
    read_fd, write_fd = os.pipe()
    cmd = [
        sys.executable,
        "-m",
        "backend.core.revert_watchdog",
        "--plan",
        plan_path,
        "--timeout",
        str(timeout_seconds),
        "--watch-pid",
        str(target_pid),
        "--ready-fd",
        str(write_fd),
    ]

    sub_env = dict(os.environ)
    if env is not None:
        sub_env.update(env)

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=sub_env,
            start_new_session=True,
            close_fds=True,
            pass_fds=(write_fd,),
        )
    except OSError as exc:
        for fd in (read_fd, write_fd):
            try:
                os.close(fd)
            except OSError:
                pass
        raise RevertGuardError(f"Failed to spawn detached revert watchdog: {exc}") from exc

    try:
        os.close(write_fd)
    except OSError:
        pass

    ready_data = b""
    try:
        rlist, _, _ = select.select([read_fd], [], [], 3.0)
        if rlist:
            ready_data = os.read(read_fd, 64)
    finally:
        try:
            os.close(read_fd)
        except OSError:
            pass

    if not ready_data.startswith(b"READY"):
        raise RevertGuardError("Detached revert watchdog failed READY handshake")

    return RevertGuardHandle(
        plan_path=plan_path,
        confirm_path=plan_payload["confirm_path"],
        log_path=plan_payload["log_path"],
        pid=proc.pid,
        plan=plan_payload,
    )


def confirm(handle: RevertGuardHandle) -> None:
    """Atomically create `handle.confirm_path` so the watchdog exits without reverting."""
    _write_private_bytes(handle.confirm_path, b"CONFIRMED\n")


def cancel(handle: RevertGuardHandle) -> None:
    """Terminate the watchdog process if still running."""
    if handle.pid > 1:
        try:
            os.kill(handle.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def save_active_handle(
    handle: RevertGuardHandle,
    *,
    deadline_epoch: float,
    timeout_seconds: float,
    state_dir: str | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    """Persist the active RevertGuardHandle so CLI confirm/revert calls can locate it."""
    resolved_state = resolve_state_dir(state_dir=state_dir, env=env)
    os.makedirs(resolved_state, exist_ok=True)
    active_path = os.path.join(resolved_state, ACTIVE_GUARD_FILENAME)
    payload = {
        "plan_path": handle.plan_path,
        "confirm_path": handle.confirm_path,
        "log_path": handle.log_path,
        "pid": handle.pid,
        "plan": handle.plan,
        "deadline_epoch": float(deadline_epoch),
        "timeout_seconds": float(timeout_seconds),
    }
    _write_private_bytes(
        active_path,
        (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return active_path


def load_active_handle(
    *,
    state_dir: str | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[RevertGuardHandle, float, float] | None:
    """Load the persisted active RevertGuardHandle, or None if not present."""
    resolved_state = resolve_state_dir(state_dir=state_dir, env=env)
    active_path = os.path.join(resolved_state, ACTIVE_GUARD_FILENAME)
    if not os.path.isfile(active_path):
        return None
    try:
        with open(active_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not data.get("plan_path") or not data.get("confirm_path"):
        return None
    handle = RevertGuardHandle(
        plan_path=str(data["plan_path"]),
        confirm_path=str(data["confirm_path"]),
        log_path=str(data.get("log_path") or ""),
        pid=int(data.get("pid") or 0),
        plan=dict(data.get("plan") or {}),
    )
    return handle, float(data.get("deadline_epoch") or 0.0), float(data.get("timeout_seconds") or 15.0)


def clear_active_handle(
    *,
    state_dir: str | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    """Remove the persisted active-guard file if present."""
    resolved_state = resolve_state_dir(state_dir=state_dir, env=env)
    active_path = os.path.join(resolved_state, ACTIVE_GUARD_FILENAME)
    if os.path.exists(active_path):
        try:
            os.unlink(active_path)
        except OSError:
            pass
