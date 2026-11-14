"""Test-isolation guard ensuring tests never touch real $HOME / ~/.config/hypr / ~/.config/hks / ~/.local/share/hks."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from typing import Mapping

from backend.core.constants import ENV_STATE_DIR
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
    """Verify resolved HKS_BACKUP_DIR, HKS_SIDECAR_PATH, and HKS_STATE_DIR are outside $HOME and real paths."""
    env_dict = dict(env) if env is not None else dict(os.environ)
    bkp = resolve_backup_dir(env=env_dict)
    sc = resolve_sidecar_path(env=env_dict) or ""
    st = resolve_state_dir(env=env_dict)
    assert_path_isolated(bkp, "HKS_BACKUP_DIR / backup_dir")
    assert_path_isolated(sc, "HKS_SIDECAR_PATH / sidecar_path")
    assert_path_isolated(st, f"{ENV_STATE_DIR} / state_dir")


class IsolatedTestCase(unittest.TestCase):
    """Base TestCase that enforces HKS_BACKUP_DIR, HKS_SIDECAR_PATH, and HKS_STATE_DIR isolation."""

    def setUp(self) -> None:
        super().setUp()
        self._isolated_root = tempfile.mkdtemp(prefix="hks_test_iso_")
        self._orig_bkp = os.environ.get("HKS_BACKUP_DIR")
        self._orig_sc = os.environ.get("HKS_SIDECAR_PATH")
        self._orig_st = os.environ.get(ENV_STATE_DIR)
        self.backup_dir = os.path.join(self._isolated_root, "backups")
        self.sidecar_path = os.path.join(self._isolated_root, "hks", "descriptions.json")
        self.state_dir = os.path.join(self._isolated_root, "state")
        os.makedirs(self.backup_dir, exist_ok=True)
        os.makedirs(self.state_dir, exist_ok=True)
        os.environ["HKS_BACKUP_DIR"] = self.backup_dir
        os.environ["HKS_SIDECAR_PATH"] = self.sidecar_path
        os.environ[ENV_STATE_DIR] = self.state_dir
        self.addCleanup(self._cleanup_isolation)

    def _cleanup_isolation(self) -> None:
        if self._orig_bkp is None:
            os.environ.pop("HKS_BACKUP_DIR", None)
        else:
            os.environ["HKS_BACKUP_DIR"] = self._orig_bkp
        if self._orig_sc is None:
            os.environ.pop("HKS_SIDECAR_PATH", None)
        else:
            os.environ["HKS_SIDECAR_PATH"] = self._orig_sc
        if self._orig_st is None:
            os.environ.pop(ENV_STATE_DIR, None)
        else:
            os.environ[ENV_STATE_DIR] = self._orig_st
        shutil.rmtree(self._isolated_root, ignore_errors=True)

    def assert_isolated(self) -> None:
        assert_env_isolated(os.environ)


_GUARD_INSTALLED = False


def install_suite_isolation_guard() -> None:
    """Install a package-wide monkeypatch guard on backup/sidecar/file write paths."""
    global _GUARD_INSTALLED
    if _GUARD_INSTALLED:
        return
    _GUARD_INSTALLED = True

    import functools
    import backend.core.revert_guard as rg_mod
    import backend.core.transaction as tx_mod
    import backend.describe.sidecar_store as sc_mod
    import backend.editor.backups as bkp_mod
    import backend.settings.commit as st_commit_mod

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
