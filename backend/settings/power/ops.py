"""Power operations: pkexec EPP/turbo writes + backup-protected hypridle timeouts."""

from __future__ import annotations

import os
import re
import subprocess
from typing import Any, Callable, Mapping, Sequence

from backend.core.live_cmd import DEFAULT_LIVE_CMD_TIMEOUT_SECONDS, LiveRunner, run_live_cmd
from backend.editor.backups import (
    BackupError,
    atomic_write_bytes,
    create_backup,
    restore_backup,
)
from backend.settings.power.state import (
    parse_hypridle_conf,
    probe_cpu,
    probe_lid_sleep,
    read_per_cpu_epp,
    read_turbo_enabled,
    resolve_power_paths,
)

MIN_IDLE_TIMEOUT = 30
MAX_IDLE_TIMEOUT = 86400
_ORDERED_ROLES = ("dim", "lock", "dpms")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
HELPER_PATH = os.path.join(_REPO_ROOT, "scripts", "hks-power-helper")


def _fail(error: str, before: Any = None, after: Any = None, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "before": before, "after": after, "error": error}
    out.update(extra)
    return out


def set_epp(
    value: Any,
    *,
    runner: LiveRunner | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Set energy_performance_preference across all CPUs via pkexec + helper."""
    if not isinstance(value, str) or not value.strip():
        return _fail("EPP preference must be a non-empty string.")
    clean = value.strip()

    paths = resolve_power_paths(env)
    sysfs_root = paths["sysfs_root"]
    cpu_before = probe_cpu(sysfs_root)
    if not cpu_before.get("available"):
        return _fail("CPU cpufreq / EPP is unavailable on this system.")

    avail = cpu_before.get("epp_available") or []
    if clean not in avail:
        return _fail(f"EPP preference {clean!r} not in available list {avail!r}.", before=cpu_before)

    before_per_cpu = read_per_cpu_epp(sysfs_root)
    res = run_live_cmd(
        ["pkexec", HELPER_PATH, "epp", clean],
        timeout=timeout,
        runner=runner,
    )
    if res.rc in (126, 127):
        return _fail("Authorization cancelled (pkexec dismissed or unauthorized).", before=cpu_before, cancelled=True)
    if not res.ok:
        return _fail(res.err.strip() or f"pkexec helper failed (rc={res.rc})", before=cpu_before, cancelled=False)

    after_per_cpu = read_per_cpu_epp(sysfs_root)
    cpu_after = probe_cpu(sysfs_root)
    if not after_per_cpu or any(v != clean for v in after_per_cpu.values()):
        return _fail(
            f"EPP readback mismatch across CPUs: expected all {clean!r}, got {after_per_cpu!r}.",
            before={"cpu": cpu_before, "per_cpu": before_per_cpu},
            after={"cpu": cpu_after, "per_cpu": after_per_cpu},
        )

    return {
        "ok": True,
        "before": cpu_before,
        "after": cpu_after,
        "message": f"EPP set to {clean} (session-only; resets on reboot).",
        "error": None,
    }


def set_turbo(
    enabled: Any,
    *,
    runner: LiveRunner | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Enable or disable Intel Turbo Boost via pkexec + helper."""
    if not isinstance(enabled, bool):
        return _fail(f"turbo enabled must be bool, got {enabled!r}.")

    paths = resolve_power_paths(env)
    sysfs_root = paths["sysfs_root"]
    cpu_before = probe_cpu(sysfs_root)
    if not cpu_before.get("available") or cpu_before.get("turbo_enabled") is None:
        return _fail("intel_pstate/no_turbo is unavailable on this system.")

    mode_str = "on" if enabled else "off"
    res = run_live_cmd(
        ["pkexec", HELPER_PATH, "turbo", mode_str],
        timeout=timeout,
        runner=runner,
    )
    if res.rc in (126, 127):
        return _fail("Authorization cancelled (pkexec dismissed or unauthorized).", before=cpu_before, cancelled=True)
    if not res.ok:
        return _fail(res.err.strip() or f"pkexec helper failed (rc={res.rc})", before=cpu_before, cancelled=False)

    actual = read_turbo_enabled(sysfs_root)
    cpu_after = probe_cpu(sysfs_root)
    if actual is not enabled:
        return _fail(
            f"Turbo readback mismatch: expected {enabled}, got {actual}.",
            before=cpu_before,
            after=cpu_after,
        )

    return {
        "ok": True,
        "before": cpu_before,
        "after": cpu_after,
        "message": f"Turbo boost {'enabled' if enabled else 'disabled'} (session-only; resets on reboot).",
        "error": None,
    }


def set_lid_action(
    mode: Any,
    *,
    runner: LiveRunner | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Set systemd-logind lid switch action (suspend, lock, ignore) via pkexec + helper."""
    if not isinstance(mode, str) or mode.strip() not in ("suspend", "lock", "ignore"):
        return _fail(f"Lid action must be one of suspend, lock, ignore; got {mode!r}.")
    clean = mode.strip()

    paths = resolve_power_paths(env)
    sysfs_root = paths["sysfs_root"]
    before = probe_lid_sleep(sysfs_root, runner=runner, timeout=timeout)

    res = run_live_cmd(
        ["pkexec", HELPER_PATH, "lid", clean],
        timeout=timeout,
        runner=runner,
    )
    if res.rc in (126, 127):
        return _fail("Authorization cancelled (pkexec dismissed or unauthorized).", before=before, cancelled=True)
    if not res.ok:
        return _fail(res.err.strip() or f"pkexec helper failed (rc={res.rc})", before=before, cancelled=False)

    after = probe_lid_sleep(sysfs_root, runner=runner, timeout=timeout)
    label_map = {"suspend": "Sleep", "lock": "Lock", "ignore": "Do Nothing"}
    return {
        "ok": True,
        "before": before,
        "after": after,
        "message": f"Lid close action set to {label_map[clean]}.",
        "error": None,
    }


def _validate_timeout_int(val: Any, label: str) -> int:
    if isinstance(val, bool) or val is None:
        raise ValueError(f"Timeout for {label!r} must be an integer between {MIN_IDLE_TIMEOUT} and {MAX_IDLE_TIMEOUT}.")
    if isinstance(val, float) and not val.is_integer():
        raise ValueError(f"Timeout for {label!r} must be an integer, got {val!r}.")
    if isinstance(val, str):
        if not val.strip().isdigit():
            raise ValueError(f"Timeout for {label!r} must be an integer, got {val!r}.")
        n = int(val.strip())
    elif isinstance(val, (int, float)):
        n = int(val)
    else:
        raise ValueError(f"Timeout for {label!r} must be an integer, got {val!r}.")
    if n < MIN_IDLE_TIMEOUT or n > MAX_IDLE_TIMEOUT:
        raise ValueError(f"Timeout for {label!r} must be between {MIN_IDLE_TIMEOUT} and {MAX_IDLE_TIMEOUT}s, got {n}.")
    return n


def rewrite_hypridle_timeouts(raw: str, changes: Mapping[str, Any]) -> str:
    """Edit ONLY `timeout =` lines of recognized listeners, preserving comments/order/other keys."""
    if not changes:
        return raw

    listeners = parse_hypridle_conf(raw)
    if not listeners:
        raise ValueError("No listener blocks found in hypridle.conf.")

    by_role: dict[str, dict[str, Any]] = {}
    by_idx: dict[int, dict[str, Any]] = {}
    for l in listeners:
        by_idx[l["index"]] = l
        if l["role"] in _ORDERED_ROLES and l["role"] not in by_role:
            by_role[l["role"]] = l

    new_timeouts: dict[int, int] = {l["index"]: l["timeout"] for l in listeners}
    for k, v in changes.items():
        if v is None:
            continue
        sec = _validate_timeout_int(v, str(k))
        if isinstance(k, int) or (isinstance(k, str) and k.isdigit()):
            idx = int(k)
            if idx not in by_idx:
                raise ValueError(f"Unknown listener index: {idx}")
            new_timeouts[idx] = sec
        else:
            role = str(k).strip().lower()
            if role not in by_role:
                raise ValueError(f"No recognized {role!r} listener found in hypridle.conf.")
            new_timeouts[by_role[role]["index"]] = sec

    # Strictly increasing order in file order for dim < lock < dpms
    ordered_present = [
        (l["role"], new_timeouts[l["index"]])
        for l in listeners
        if l["role"] in _ORDERED_ROLES
    ]
    for i in range(len(ordered_present) - 1):
        r1, t1 = ordered_present[i]
        r2, t2 = ordered_present[i + 1]
        if t1 >= t2:
            raise ValueError(
                f"Idle timeouts must be strictly increasing ({r1}={t1}s must be < {r2}={t2}s)."
            )

    had_trailing_nl = raw.endswith("\n")
    lines = raw.splitlines()
    changed_any = False
    for l in listeners:
        idx = l["index"]
        target_t = new_timeouts[idx]
        if target_t == l["timeout"]:
            continue
        line_idx = l["timeout_line_index"]
        if line_idx is None:
            continue
        old_line = lines[line_idx]
        new_line = re.sub(r"(\btimeout\s*=\s*)\d+", rf"\g<1>{target_t}", old_line, count=1)
        if new_line != old_line:
            lines[line_idx] = new_line
            changed_any = True

    if not changed_any:
        return raw

    out = "\n".join(lines)
    if had_trailing_nl:
        out += "\n"
    return out


def default_detached_spawner(argv: Sequence[str]) -> subprocess.Popen[Any]:
    """Spawn a detached background process with argv list (never shell=True)."""
    return subprocess.Popen(
        list(argv),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        shell=False,
    )


def set_idle_timeouts(
    changes: Mapping[str, Any],
    *,
    runner: LiveRunner | None = None,
    spawner: Callable[..., Any] | None = None,
    env: Mapping[str, str] | None = None,
    backup_dir: str | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Validate, backup, atomically write hypridle.conf, verify readback, and restart hypridle."""
    environ = env if env is not None else os.environ
    paths = resolve_power_paths(environ)
    conf_path = paths["hypridle_conf"]

    if not os.path.isfile(conf_path):
        return _fail(f"hypridle config not found: {conf_path}")

    with open(conf_path, "r", encoding="utf-8", errors="replace") as f:
        before_raw = f.read()

    before_listeners = parse_hypridle_conf(before_raw)
    try:
        after_raw = rewrite_hypridle_timeouts(before_raw, changes)
    except ValueError as exc:
        return _fail(str(exc), before=before_listeners)

    if after_raw == before_raw:
        return {
            "ok": True,
            "changed": False,
            "before": before_listeners,
            "after": before_listeners,
            "backup_path": None,
            "rolled_back": False,
            "error": None,
        }

    env_dict = dict(environ)
    try:
        record = create_backup(conf_path, backup_dir=backup_dir, env=env_dict)
    except BackupError as exc:
        return _fail(f"Backup failed: {exc}", before=before_listeners)

    try:
        atomic_write_bytes(conf_path, after_raw.encode("utf-8"), mode_source=conf_path)
    except OSError as exc:
        try:
            restore_backup(record, backup_dir=backup_dir, force=True, env=env_dict)
        except BackupError:
            pass
        return _fail(f"Write failed: {exc}", before=before_listeners, backup_path=record.backup_path, rolled_back=True)

    # Readback re-parse verify
    with open(conf_path, "r", encoding="utf-8", errors="replace") as f:
        verify_raw = f.read()
    after_listeners = parse_hypridle_conf(verify_raw)
    if verify_raw != after_raw or not after_listeners:
        try:
            restore_backup(record, backup_dir=backup_dir, force=True, env=env_dict)
        except BackupError:
            pass
        return _fail(
            "hypridle.conf readback verification failed; backup restored.",
            before=before_listeners,
            backup_path=record.backup_path,
            rolled_back=True,
        )

    # Restart hypridle detached and verify running via pgrep
    run_live_cmd(["pkill", "-x", "hypridle"], timeout=timeout, runner=runner)
    spawn_ok = True
    spawn_err = ""
    active_spawner = spawner if spawner is not None else default_detached_spawner
    try:
        active_spawner(["hypridle"])
    except OSError as exc:
        spawn_ok = False
        spawn_err = str(exc)

    pg_res = run_live_cmd(["pgrep", "-x", "hypridle"], timeout=timeout, runner=runner) if spawn_ok else None
    if not spawn_ok or pg_res is None or not pg_res.ok:
        try:
            restore_backup(record, backup_dir=backup_dir, force=True, env=env_dict)
        except BackupError:
            pass
        return _fail(
            f"hypridle restart verification failed ({spawn_err or 'not running'}); backup restored.",
            before=before_listeners,
            backup_path=record.backup_path,
            rolled_back=True,
        )

    return {
        "ok": True,
        "changed": True,
        "before": before_listeners,
        "after": after_listeners,
        "backup_path": record.backup_path,
        "rolled_back": False,
        "error": None,
    }
