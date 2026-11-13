"""Test-isolation guard ensuring tests never touch real $HOME / ~/.config/hypr / ~/.config/hks / ~/.local/share/hks."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from typing import Mapping

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
    """Verify resolved HKS_BACKUP_DIR and HKS_SIDECAR_PATH are outside $HOME and real HKS/Hypr paths."""
    env_dict = dict(env) if env is not None else dict(os.environ)
    bkp = resolve_backup_dir(env=env_dict)
    sc = resolve_sidecar_path(env=env_dict) or ""
    assert_path_isolated(bkp, "HKS_BACKUP_DIR / backup_dir")
    assert_path_isolated(sc, "HKS_SIDECAR_PATH / sidecar_path")


class IsolatedTestCase(unittest.TestCase):
    """Base TestCase that enforces HKS_BACKUP_DIR and HKS_SIDECAR_PATH isolation."""

    def setUp(self) -> None:
        super().setUp()
        self._isolated_root = tempfile.mkdtemp(prefix="hks_test_iso_")
        self._orig_bkp = os.environ.get("HKS_BACKUP_DIR")
        self._orig_sc = os.environ.get("HKS_SIDECAR_PATH")
        self.backup_dir = os.path.join(self._isolated_root, "backups")
        self.sidecar_path = os.path.join(self._isolated_root, "hks", "descriptions.json")
        os.makedirs(self.backup_dir, exist_ok=True)
        os.environ["HKS_BACKUP_DIR"] = self.backup_dir
        os.environ["HKS_SIDECAR_PATH"] = self.sidecar_path
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
    import backend.describe.sidecar_store as sc_mod
    import backend.editor.backups as bkp_mod

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
