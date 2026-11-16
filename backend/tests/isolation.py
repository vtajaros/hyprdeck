"""Test-isolation guard ensuring tests never touch real $HOME / ~/.config/hypr / ~/.config/hks / ~/.local/share/hks."""

from __future__ import annotations

import atexit
import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from typing import Mapping

from backend.core.constants import (
    ENV_BACKUP_DIR,
    ENV_HYPRIDLE_PATH,
    ENV_POWER_SYSFS_ROOT,
    ENV_SETTINGS_CONFIG_DIR,
    ENV_SETTINGS_DEBUG,
    ENV_SETTINGS_DEVICES_FIXTURE,
    ENV_SETTINGS_MONITORS_FIXTURE,
    ENV_SETTINGS_RELOAD_MODE,
    ENV_SETTINGS_XKB_PATH,
    ENV_SIDECAR_PATH,
    ENV_STATE_DIR,
    ENV_THEMES_HOME,
    ENV_WINDOW_SCRIPT,
)
from backend.core.env import get_env
from backend.core.revert_guard import resolve_state_dir
from backend.describe.sidecar import resolve_sidecar_path
from backend.editor.backups import resolve_backup_dir

REAL_HOME = os.path.realpath(os.path.expanduser("~"))
FORBIDDEN_REAL_PATHS = tuple(
    os.path.realpath(os.path.expanduser(p))
    for p in ("~/.config/hypr", "~/.config/hks", "~/.local/share/hks")
)


def is_under_path(candidate: str, root: str) -> bool:
    real_cand = os.path.realpath(os.path.abspath(os.path.expanduser(candidate)))
    real_root = os.path.realpath(os.path.abspath(os.path.expanduser(root)))
    return real_cand == real_root or real_cand.startswith(real_root + os.sep)


def assert_path_isolated(path: str, label: str = "path") -> None:
    """Fail if `path` resolves under $HOME or any of the real Hypr/HKS directories."""
    real = os.path.realpath(os.path.abspath(os.path.expanduser(path)))
    for forbidden in FORBIDDEN_REAL_PATHS:
        if is_under_path(real, forbidden):
            raise AssertionError(
                f"Test isolation violation: {label} ({real!r}) resolves inside real path {forbidden!r}"
            )
    if is_under_path(real, REAL_HOME):
        raise AssertionError(
            f"Test isolation violation: {label} ({real!r}) resolves under $HOME ({REAL_HOME!r})"
        )


def assert_env_isolated(env: Mapping[str, str] | None = None) -> None:
    """Verify resolved HKS_BACKUP_DIR, HKS_SIDECAR_PATH, HKS_STATE_DIR, and debug config dir are isolated."""
    env_dict = dict(env) if env is not None else dict(os.environ)
    bkp = resolve_backup_dir(env=env_dict)
    sc = resolve_sidecar_path(env=env_dict) or ""
    st = resolve_state_dir(env=env_dict)
    assert_path_isolated(bkp, f"{ENV_BACKUP_DIR} / HKS_BACKUP_DIR / backup_dir")
    assert_path_isolated(sc, f"{ENV_SIDECAR_PATH} / HKS_SIDECAR_PATH / sidecar_path")
    assert_path_isolated(st, f"{ENV_STATE_DIR} / HKS_STATE_DIR / state_dir")
    dbg_cfg = get_env("SETTINGS_CONFIG_DIR", environ=env_dict)
    if dbg_cfg:
        assert_path_isolated(dbg_cfg, ENV_SETTINGS_CONFIG_DIR)
    pwr_sysfs = get_env("POWER_SYSFS_ROOT", environ=env_dict)
    if pwr_sysfs:
        assert_path_isolated(pwr_sysfs, ENV_POWER_SYSFS_ROOT)
    hypridle_p = get_env("HYPRIDLE_PATH", environ=env_dict)
    if hypridle_p:
        assert_path_isolated(hypridle_p, ENV_HYPRIDLE_PATH)
    hks_win_p = get_env("WINDOW_SCRIPT", environ=env_dict)
    if hks_win_p:
        assert_path_isolated(hks_win_p, ENV_WINDOW_SCRIPT)
    repo_fixtures = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
    dev_fx = get_env("SETTINGS_DEVICES_FIXTURE", environ=env_dict)
    if dev_fx and not is_under_path(dev_fx, repo_fixtures):
        assert_path_isolated(dev_fx, ENV_SETTINGS_DEVICES_FIXTURE)
        if not is_under_path(dev_fx, tempfile.gettempdir()):
            raise AssertionError(
                f"Test isolation violation: {ENV_SETTINGS_DEVICES_FIXTURE} ({dev_fx!r}) must be under /tmp or test fixtures"
            )


_CLEARED_ENV_VARS = (
    ENV_SETTINGS_DEBUG,
    "HKS_SETTINGS_DEBUG",
    ENV_SETTINGS_CONFIG_DIR,
    "HKS_SETTINGS_CONFIG_DIR",
    ENV_SETTINGS_RELOAD_MODE,
    "HKS_SETTINGS_RELOAD_MODE",
    ENV_SETTINGS_MONITORS_FIXTURE,
    "HKS_SETTINGS_MONITORS_FIXTURE",
    ENV_SETTINGS_DEVICES_FIXTURE,
    "HKS_SETTINGS_DEVICES_FIXTURE",
    ENV_SETTINGS_XKB_PATH,
    "HKS_SETTINGS_XKB_PATH",
    ENV_THEMES_HOME,
    "HKS_THEMES_HOME",
    ENV_POWER_SYSFS_ROOT,
    "HKS_POWER_SYSFS_ROOT",
    ENV_HYPRIDLE_PATH,
    "HKS_HYPRIDLE_PATH",
    ENV_WINDOW_SCRIPT,
    "HKS_WINDOW_SCRIPT",
)


_XDG_ENV_VARS = (
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_STATE_HOME",
)


class IsolatedTestCase(unittest.TestCase):
    """Base TestCase that enforces HYPRDECK_* / HKS_* and XDG_* isolation."""

    def setUp(self) -> None:
        super().setUp()
        self._isolated_root = tempfile.mkdtemp(prefix="hks_test_iso_")
        self._orig_bkp = os.environ.get("HKS_BACKUP_DIR")
        self._orig_hy_bkp = os.environ.get(ENV_BACKUP_DIR)
        self._orig_sc = os.environ.get("HKS_SIDECAR_PATH")
        self._orig_hy_sc = os.environ.get(ENV_SIDECAR_PATH)
        self._orig_st = os.environ.get("HKS_STATE_DIR")
        self._orig_hy_st = os.environ.get(ENV_STATE_DIR)
        self._orig_xdg = {k: os.environ.get(k) for k in _XDG_ENV_VARS}
        self._orig_extra = {k: os.environ.get(k) for k in _CLEARED_ENV_VARS}
        self.backup_dir = os.path.join(self._isolated_root, "backups")
        self.sidecar_path = os.path.join(self._isolated_root, "hks", "descriptions.json")
        self.state_dir = os.path.join(self._isolated_root, "state")
        self.xdg_config_home = os.path.join(self._isolated_root, "xdg_config")
        self.xdg_data_home = os.path.join(self._isolated_root, "xdg_data")
        self.xdg_state_home = os.path.join(self._isolated_root, "xdg_state")
        for d in (
            self.backup_dir,
            self.state_dir,
            self.xdg_config_home,
            self.xdg_data_home,
            self.xdg_state_home,
        ):
            os.makedirs(d, exist_ok=True)
        os.environ["HKS_BACKUP_DIR"] = self.backup_dir
        os.environ[ENV_BACKUP_DIR] = self.backup_dir
        os.environ["HKS_SIDECAR_PATH"] = self.sidecar_path
        os.environ[ENV_SIDECAR_PATH] = self.sidecar_path
        os.environ["HKS_STATE_DIR"] = self.state_dir
        os.environ[ENV_STATE_DIR] = self.state_dir
        os.environ["XDG_CONFIG_HOME"] = self.xdg_config_home
        os.environ["XDG_DATA_HOME"] = self.xdg_data_home
        os.environ["XDG_STATE_HOME"] = self.xdg_state_home
        for k in _CLEARED_ENV_VARS:
            os.environ.pop(k, None)
        self.addCleanup(self._cleanup_isolation)

    def _cleanup_isolation(self) -> None:
        for key, orig in (
            ("HKS_BACKUP_DIR", self._orig_bkp),
            (ENV_BACKUP_DIR, self._orig_hy_bkp),
            ("HKS_SIDECAR_PATH", self._orig_sc),
            (ENV_SIDECAR_PATH, self._orig_hy_sc),
            ("HKS_STATE_DIR", self._orig_st),
            (ENV_STATE_DIR, self._orig_hy_st),
        ):
            if orig is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = orig
        for k, orig in self._orig_xdg.items():
            if orig is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = orig
        for k, orig in self._orig_extra.items():
            if orig is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = orig
        shutil.rmtree(self._isolated_root, ignore_errors=True)

    def assert_isolated(self) -> None:
        assert_env_isolated(os.environ)


_GUARD_INSTALLED = False
_REAL_SNAPSHOT_DIRS = (
    os.path.realpath(os.path.join(REAL_HOME, ".config", "hks")),
    os.path.realpath(os.path.join(REAL_HOME, ".config", "hypr")),
)


def _snapshot_real_dir(root_dir: str) -> dict[str, object]:
    """Read-only stat + sha256 snapshot of a directory (if present)."""
    if not os.path.exists(root_dir):
        return {"exists": False, "entries": {}}
    entries: dict[str, tuple[int, int, str]] = {}
    try:
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames.sort()
            for fname in sorted(filenames):
                full = os.path.join(dirpath, fname)
                rel = os.path.relpath(full, root_dir)
                try:
                    st = os.stat(full, follow_symlinks=False)
                    digest = ""
                    if os.path.isfile(full) and not os.path.islink(full):
                        with open(full, "rb") as f:
                            digest = hashlib.sha256(f.read()).hexdigest()
                    entries[rel] = (int(st.st_mtime_ns), int(st.st_size), digest)
                except OSError:
                    entries[rel] = (-1, -1, "unreadable")
    except OSError:
        return {"exists": True, "entries": {"<unreadable>": (-1, -1, "")}}
    return {"exists": True, "entries": entries}


def _verify_real_snapshots(baseline: dict[str, dict[str, object]]) -> None:
    """Suite-exit guard: fail loudly if real ~/.config/hks or ~/.config/hypr changed."""
    diffs: list[str] = []
    for d, before in baseline.items():
        after = _snapshot_real_dir(d)
        if before != after:
            diffs.append(f"{d}: before={before} after={after}")
    if diffs:
        sys.stderr.write(
            "\nFATAL: Test suite modified real user configuration/state!\n"
            + "\n".join(diffs)
            + "\n"
        )
        sys.stderr.flush()
        sys.exit(1)


def install_suite_isolation_guard() -> None:
    """Install a package-wide monkeypatch guard on backup/sidecar/file write paths."""
    global _GUARD_INSTALLED
    if _GUARD_INSTALLED:
        return
    _GUARD_INSTALLED = True

    baseline = {d: _snapshot_real_dir(d) for d in _REAL_SNAPSHOT_DIRS}
    atexit.register(_verify_real_snapshots, baseline)

    import functools
    import backend.core.live_cmd as live_cmd_mod
    import backend.core.revert_guard as rg_mod
    import backend.settings.power.ops as pwr_ops_mod
    import backend.core.transaction as tx_mod
    import backend.describe.sidecar_store as sc_mod
    import backend.editor.backups as bkp_mod
    import backend.settings.commit as st_commit_mod
    import backend.settings.display.apply_flow as disp_apply_mod
    import backend.settings.display.brightness as disp_bri_mod
    import backend.settings.input.apply_flow as inp_apply_mod

    orig_atomic_write = bkp_mod.atomic_write_bytes
    orig_create_backup = bkp_mod.create_backup
    orig_restore_backup = bkp_mod.restore_backup
    orig_write_sc = sc_mod._write_sidecar_atomic
    orig_backup_sc = sc_mod.backup_sidecar_file

    @functools.wraps(orig_atomic_write)
    def guarded_atomic_write(target_path: str, data: bytes, mode_source: str | None = None) -> None:
        assert_path_isolated(target_path, "atomic_write_bytes(target_path)")
        return orig_atomic_write(target_path, data, mode_source=mode_source)

    @functools.wraps(orig_create_backup)
    def guarded_create_backup(path: str, *, backup_dir: str | None = None, config_dir: str | None = None, env=None, sidecar_path: str | None = None):
        resolved_bdir = bkp_mod.resolve_backup_dir(backup_dir=backup_dir, env=env)
        assert_path_isolated(resolved_bdir, "create_backup(backup_dir)")
        if sidecar_path is not None:
            assert_path_isolated(sidecar_path, "create_backup(sidecar_path)")
        return orig_create_backup(path, backup_dir=backup_dir, config_dir=config_dir, env=env, sidecar_path=sidecar_path)

    @functools.wraps(orig_restore_backup)
    def guarded_restore_backup(record, expected_current_sha256: str | None = None, *, backup_dir: str | None = None, force: bool = False, env=None):
        resolved_bdir = bkp_mod.resolve_backup_dir(backup_dir=backup_dir, env=env)
        assert_path_isolated(resolved_bdir, "restore_backup(backup_dir)")
        return orig_restore_backup(record, expected_current_sha256=expected_current_sha256, backup_dir=backup_dir, force=force, env=env)

    @functools.wraps(orig_write_sc)
    def guarded_write_sc(sidecar_path: str, data: dict) -> None:
        assert_path_isolated(sidecar_path, "_write_sidecar_atomic(sidecar_path)")
        return orig_write_sc(sidecar_path, data)

    @functools.wraps(orig_backup_sc)
    def guarded_backup_sc(sidecar_path: str, backup_dir: str | None = None, env=None) -> str:
        resolved_bdir = bkp_mod.resolve_backup_dir(backup_dir=backup_dir, env=env)
        assert_path_isolated(resolved_bdir, "backup_sidecar_file(backup_dir)")
        assert_path_isolated(sidecar_path, "backup_sidecar_file(sidecar_path)")
        return orig_backup_sc(sidecar_path, backup_dir=backup_dir, env=env)

    bkp_mod.atomic_write_bytes = guarded_atomic_write
    bkp_mod.create_backup = guarded_create_backup
    bkp_mod.restore_backup = guarded_restore_backup
    sc_mod._write_sidecar_atomic = guarded_write_sc
    sc_mod.backup_sidecar_file = guarded_backup_sc

    orig_apply_managed = tx_mod.apply_managed_change
    orig_undo_managed = tx_mod.undo_managed_change
    orig_arm = rg_mod.arm
    orig_confirm = rg_mod.confirm

    @functools.wraps(orig_apply_managed)
    def guarded_apply_managed(target_path: str, new_bytes: bytes, **kwargs):
        assert_path_isolated(target_path, "apply_managed_change(target_path)")
        if kwargs.get("config_dir"):
            assert_path_isolated(kwargs["config_dir"], "apply_managed_change(config_dir)")
        if kwargs.get("entrypoint"):
            assert_path_isolated(kwargs["entrypoint"], "apply_managed_change(entrypoint)")
        resolved_bdir = bkp_mod.resolve_backup_dir(
            backup_dir=kwargs.get("backup_dir"), env=kwargs.get("env")
        )
        assert_path_isolated(resolved_bdir, "apply_managed_change(backup_dir)")
        return orig_apply_managed(target_path, new_bytes, **kwargs)

    @functools.wraps(orig_undo_managed)
    def guarded_undo_managed(result, **kwargs):
        if getattr(result, "target_path", ""):
            assert_path_isolated(result.target_path, "undo_managed_change(target_path)")
        resolved_bdir = bkp_mod.resolve_backup_dir(
            backup_dir=kwargs.get("backup_dir"), env=kwargs.get("env")
        )
        assert_path_isolated(resolved_bdir, "undo_managed_change(backup_dir)")
        return orig_undo_managed(result, **kwargs)

    @functools.wraps(orig_arm)
    def guarded_arm(plan, timeout_seconds: float = 15.0, watch_pid: int | None = None, *, state_dir=None, env=None):
        resolved_st = rg_mod.resolve_state_dir(state_dir=state_dir, env=env)
        assert_path_isolated(resolved_st, "revert_guard.arm(state_dir)")
        if plan.get("target_path"):
            assert_path_isolated(str(plan["target_path"]), "revert_guard.arm(target_path)")
        if plan.get("backup_dir"):
            assert_path_isolated(str(plan["backup_dir"]), "revert_guard.arm(backup_dir)")
        if plan.get("confirm_path"):
            assert_path_isolated(str(plan["confirm_path"]), "revert_guard.arm(confirm_path)")
        if plan.get("log_path"):
            assert_path_isolated(str(plan["log_path"]), "revert_guard.arm(log_path)")
        return orig_arm(plan, timeout_seconds=timeout_seconds, watch_pid=watch_pid, state_dir=state_dir, env=env)

    @functools.wraps(orig_confirm)
    def guarded_confirm(handle):
        assert_path_isolated(handle.confirm_path, "revert_guard.confirm(confirm_path)")
        return orig_confirm(handle)

    tx_mod.apply_managed_change = guarded_apply_managed
    tx_mod.undo_managed_change = guarded_undo_managed
    rg_mod.arm = guarded_arm
    rg_mod.confirm = guarded_confirm

    orig_commit_settings = st_commit_mod.commit_settings
    orig_reset_settings = st_commit_mod.reset_settings

    @functools.wraps(orig_commit_settings)
    def guarded_commit_settings(changes, *, config_dir: str, entrypoint: str, **kwargs):
        assert_path_isolated(config_dir, "commit_settings(config_dir)")
        assert_path_isolated(entrypoint, "commit_settings(entrypoint)")
        return orig_commit_settings(changes, config_dir=config_dir, entrypoint=entrypoint, **kwargs)

    @functools.wraps(orig_reset_settings)
    def guarded_reset_settings(*, config_dir: str, entrypoint: str, **kwargs):
        assert_path_isolated(config_dir, "reset_settings(config_dir)")
        assert_path_isolated(entrypoint, "reset_settings(entrypoint)")
        return orig_reset_settings(config_dir=config_dir, entrypoint=entrypoint, **kwargs)

    st_commit_mod.commit_settings = guarded_commit_settings
    st_commit_mod.reset_settings = guarded_reset_settings

    orig_apply_disp = disp_apply_mod.apply_display_changes
    orig_confirm_disp = disp_apply_mod.confirm_display_changes
    orig_revert_disp = disp_apply_mod.revert_display_changes
    orig_set_bri = disp_bri_mod.set_brightness

    @functools.wraps(orig_apply_disp)
    def guarded_apply_disp(changes, *, current_outputs, config_dir: str, entrypoint: str, **kwargs):
        assert_path_isolated(config_dir, "apply_display_changes(config_dir)")
        assert_path_isolated(entrypoint, "apply_display_changes(entrypoint)")
        resolved_bdir = bkp_mod.resolve_backup_dir(
            backup_dir=kwargs.get("backup_dir"), env=kwargs.get("env")
        )
        assert_path_isolated(resolved_bdir, "apply_display_changes(backup_dir)")
        resolved_sdir = rg_mod.resolve_state_dir(
            state_dir=kwargs.get("state_dir"), env=kwargs.get("env")
        )
        assert_path_isolated(resolved_sdir, "apply_display_changes(state_dir)")
        return orig_apply_disp(
            changes,
            current_outputs=current_outputs,
            config_dir=config_dir,
            entrypoint=entrypoint,
            **kwargs,
        )

    @functools.wraps(orig_confirm_disp)
    def guarded_confirm_disp(*, handle=None, state_dir=None, env=None):
        if handle is not None:
            assert_path_isolated(handle.confirm_path, "confirm_display_changes(confirm_path)")
        else:
            assert_path_isolated(
                rg_mod.resolve_state_dir(state_dir=state_dir, env=env),
                "confirm_display_changes(state_dir)",
            )
        return orig_confirm_disp(handle=handle, state_dir=state_dir, env=env)

    @functools.wraps(orig_revert_disp)
    def guarded_revert_disp(*, handle=None, state_dir=None, env=None, **kwargs):
        if handle is not None and handle.plan.get("target_path"):
            assert_path_isolated(
                str(handle.plan["target_path"]), "revert_display_changes(target_path)"
            )
        else:
            assert_path_isolated(
                rg_mod.resolve_state_dir(state_dir=state_dir, env=env),
                "revert_display_changes(state_dir)",
            )
        return orig_revert_disp(handle=handle, state_dir=state_dir, env=env, **kwargs)

    @functools.wraps(orig_set_bri)
    def guarded_set_bri(percent, *, device=None, use_ddc=False, runner=None, timeout=3.0):
        if runner is None:
            raise AssertionError(
                "Test isolation violation: set_brightness called in tests without mock runner"
            )
        return orig_set_bri(percent, device=device, use_ddc=use_ddc, runner=runner, timeout=timeout)

    disp_apply_mod.apply_display_changes = guarded_apply_disp
    disp_apply_mod.confirm_display_changes = guarded_confirm_disp
    disp_apply_mod.revert_display_changes = guarded_revert_disp
    disp_bri_mod.set_brightness = guarded_set_bri

    orig_apply_inp = inp_apply_mod.apply_input_changes
    orig_confirm_inp = inp_apply_mod.confirm_input_changes
    orig_revert_inp = inp_apply_mod.revert_input_changes

    @functools.wraps(orig_apply_inp)
    def guarded_apply_inp(option_changes=None, *, config_dir: str, entrypoint: str, **kwargs):
        assert_path_isolated(config_dir, "apply_input_changes(config_dir)")
        assert_path_isolated(entrypoint, "apply_input_changes(entrypoint)")
        resolved_bdir = bkp_mod.resolve_backup_dir(
            backup_dir=kwargs.get("backup_dir"), env=kwargs.get("env")
        )
        assert_path_isolated(resolved_bdir, "apply_input_changes(backup_dir)")
        resolved_sdir = rg_mod.resolve_state_dir(
            state_dir=kwargs.get("state_dir"), env=kwargs.get("env")
        )
        assert_path_isolated(resolved_sdir, "apply_input_changes(state_dir)")
        return orig_apply_inp(
            option_changes,
            config_dir=config_dir,
            entrypoint=entrypoint,
            **kwargs,
        )

    @functools.wraps(orig_confirm_inp)
    def guarded_confirm_inp(*, handle=None, state_dir=None, env=None):
        if handle is not None:
            assert_path_isolated(handle.confirm_path, "confirm_input_changes(confirm_path)")
        else:
            assert_path_isolated(
                rg_mod.resolve_state_dir(state_dir=state_dir, env=env),
                "confirm_input_changes(state_dir)",
            )
        return orig_confirm_inp(handle=handle, state_dir=state_dir, env=env)

    @functools.wraps(orig_revert_inp)
    def guarded_revert_inp(*, handle=None, state_dir=None, env=None, **kwargs):
        if handle is not None and handle.plan.get("target_path"):
            assert_path_isolated(
                str(handle.plan["target_path"]), "revert_input_changes(target_path)"
            )
        else:
            assert_path_isolated(
                rg_mod.resolve_state_dir(state_dir=state_dir, env=env),
                "revert_input_changes(state_dir)",
            )
        return orig_revert_inp(handle=handle, state_dir=state_dir, env=env, **kwargs)

    inp_apply_mod.apply_input_changes = guarded_apply_inp
    inp_apply_mod.confirm_input_changes = guarded_confirm_inp
    inp_apply_mod.revert_input_changes = guarded_revert_inp

    orig_run_live_cmd = live_cmd_mod.run_live_cmd

    @functools.wraps(orig_run_live_cmd)
    def guarded_run_live_cmd(argv, *, timeout=live_cmd_mod.DEFAULT_LIVE_CMD_TIMEOUT_SECONDS, runner=None, env=None):
        if runner is None and not isinstance(argv, (str, bytes)):
            items = list(argv)
            if items and (
                items[0] in (
                    "pactl", "wpctl", "busctl", "bluetoothctl", "rfkill", "nmcli",
                    "gsettings", "hyprctl", "awww", "xfconf-query",
                    "upower", "pkexec", "pgrep", "pkill", "hypridle", "systemd-analyze",
                    "hostnamectl", "uname", "lscpu", "free", "df", "lspci", "uptime", "quickshell",
                    "hks-window", "hks-settings", "hyprdeck-window", "hyprdeck-settings",
                )
                or os.path.basename(items[0]) in ("hks-window", "hks-settings", "hyprdeck-window", "hyprdeck-settings")
            ):
                raise AssertionError(
                    f"Test isolation violation: real {items[0]!r} called in tests without mock runner"
                )
        return orig_run_live_cmd(argv, timeout=timeout, runner=runner, env=env)

    live_cmd_mod.run_live_cmd = guarded_run_live_cmd

    orig_default_spawner = pwr_ops_mod.default_detached_spawner

    @functools.wraps(orig_default_spawner)
    def guarded_default_spawner(argv):
        raise AssertionError(
            f"Test isolation violation: real default_detached_spawner (Popen) called in tests for {list(argv)!r}"
        )

    pwr_ops_mod.default_detached_spawner = guarded_default_spawner
