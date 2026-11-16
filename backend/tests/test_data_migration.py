"""Isolated unit tests for Phase D data dir resolution and `migrate-data` CLI."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from backend.cli import main as cli_main
from backend.core.data_migration import migrate_data, resolve_config_app_dir, resolve_data_app_dir
from backend.core.revert_guard import resolve_state_dir
from backend.describe.sidecar import resolve_sidecar_path
from backend.editor.backups import resolve_backup_dir
from backend.tests.isolation import IsolatedTestCase


class TestDataDirResolutionAndMigration(IsolatedTestCase):
    def _make_fake_home(self) -> tuple[str, dict[str, str]]:
        home = tempfile.mkdtemp(prefix="hyprdeck_mig_home_", dir=self._isolated_root)
        env = {"HOME": home}
        return home, env

    def test_resolution_prefers_new_falls_back_to_legacy_and_defaults_to_new(self) -> None:
        home, env = self._make_fake_home()
        # Neither exists -> new default
        self.assertEqual(resolve_config_app_dir(env), os.path.join(home, ".config", "hyprdeck"))
        self.assertEqual(resolve_data_app_dir(env), os.path.join(home, ".local", "share", "hyprdeck"))
        self.assertEqual(resolve_sidecar_path(env=env), os.path.join(home, ".config", "hyprdeck", "descriptions.json"))
        self.assertEqual(resolve_backup_dir(env=env), os.path.join(home, ".local", "share", "hyprdeck", "backups"))
        self.assertEqual(resolve_state_dir(env=env), os.path.join(home, ".local", "share", "hyprdeck", "revert-guard"))

        # Legacy exists -> falls back to legacy
        os.makedirs(os.path.join(home, ".config", "hks"), exist_ok=True)
        os.makedirs(os.path.join(home, ".local", "share", "hks"), exist_ok=True)
        self.assertEqual(resolve_sidecar_path(env=env), os.path.join(home, ".config", "hks", "descriptions.json"))
        self.assertEqual(resolve_backup_dir(env=env), os.path.join(home, ".local", "share", "hks", "backups"))
        self.assertEqual(resolve_state_dir(env=env), os.path.join(home, ".local", "share", "hks", "revert-guard"))

        # Both exist -> new wins
        os.makedirs(os.path.join(home, ".config", "hyprdeck"), exist_ok=True)
        os.makedirs(os.path.join(home, ".local", "share", "hyprdeck"), exist_ok=True)
        self.assertEqual(resolve_sidecar_path(env=env), os.path.join(home, ".config", "hyprdeck", "descriptions.json"))
        self.assertEqual(resolve_backup_dir(env=env), os.path.join(home, ".local", "share", "hyprdeck", "backups"))
        self.assertEqual(resolve_state_dir(env=env), os.path.join(home, ".local", "share", "hyprdeck", "revert-guard"))

    def test_migrate_data_dry_run_apply_symlink_verify_and_idempotent(self) -> None:
        home, env = self._make_fake_home()
        old_cfg = os.path.join(home, ".config", "hks")
        old_data = os.path.join(home, ".local", "share", "hks")
        new_cfg = os.path.join(home, ".config", "hyprdeck")
        new_data = os.path.join(home, ".local", "share", "hyprdeck")
        os.makedirs(old_cfg, exist_ok=True)
        os.makedirs(os.path.join(old_data, "backups"), exist_ok=True)

        sc_file = os.path.join(old_cfg, "descriptions.json")
        bkp_file = os.path.join(old_data, "backups", "snap.lua")
        with open(sc_file, "wb") as f:
            f.write(b'{"version":1,"overrides":[]}\n')
        with open(bkp_file, "wb") as f:
            f.write(b"-- backup\n")
        sc_sha = hashlib.sha256(b'{"version":1,"overrides":[]}\n').hexdigest()

        dry = migrate_data(apply=False, env=env)
        self.assertTrue(dry["ok"])
        self.assertFalse(dry["applied"])
        self.assertFalse(os.path.exists(new_cfg))
        self.assertFalse(os.path.islink(old_cfg))

        app = migrate_data(apply=True, env=env)
        self.assertTrue(app["ok"])
        self.assertTrue(app["applied"])
        self.assertTrue(os.path.islink(old_cfg))
        self.assertTrue(os.path.islink(old_data))
        self.assertEqual(os.path.realpath(old_cfg), os.path.realpath(new_cfg))
        self.assertEqual(os.path.realpath(old_data), os.path.realpath(new_data))
        with open(os.path.join(new_cfg, "descriptions.json"), "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), sc_sha)
        self.assertTrue(os.path.isfile(os.path.join(new_data, "backups", "snap.lua")))
        self.assertTrue(app["undo_commands"])

        # Idempotent second run
        idem = migrate_data(apply=True, env=env)
        self.assertTrue(idem["ok"])
        self.assertTrue(idem["already_migrated"])

    def test_migrate_data_refuses_when_missing_old_nonempty_new_or_pending_guard(self) -> None:
        home, env = self._make_fake_home()
        # Missing old dirs -> refuse
        miss = migrate_data(apply=True, env=env)
        self.assertFalse(miss["ok"])

        # Non-empty new dir -> refuse
        old_cfg = os.path.join(home, ".config", "hks")
        new_cfg = os.path.join(home, ".config", "hyprdeck")
        os.makedirs(old_cfg, exist_ok=True)
        os.makedirs(new_cfg, exist_ok=True)
        with open(os.path.join(new_cfg, "existing.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        nonempty = migrate_data(apply=True, env=env)
        self.assertFalse(nonempty["ok"])
        self.assertFalse(os.path.islink(old_cfg))

        # Pending revert-guard -> refuse
        home2, env2 = self._make_fake_home()
        guard_dir = os.path.join(home2, ".local", "share", "hks", "revert-guard")
        os.makedirs(guard_dir, exist_ok=True)
        with open(os.path.join(guard_dir, "active-guard.json"), "w", encoding="utf-8") as f:
            f.write('{"pending":true}')
        guarded = migrate_data(apply=True, env=env2)
        self.assertFalse(guarded["ok"])

    def test_cli_migrate_data_dry_run_and_apply_json(self) -> None:
        home, env = self._make_fake_home()
        old_cfg = os.path.join(home, ".config", "hks")
        os.makedirs(old_cfg, exist_ok=True)
        with open(os.path.join(old_cfg, "descriptions.json"), "w", encoding="utf-8") as f:
            f.write("{}\n")

        with mock.patch.dict(os.environ, env, clear=True):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli_main(["migrate-data", "--dry-run", "--json"])
            self.assertEqual(rc, 0)
            data = json.loads(buf.getvalue())
            self.assertTrue(data["ok"])
            self.assertFalse(data["applied"])

            buf2 = io.StringIO()
            err2 = io.StringIO()
            with redirect_stdout(buf2), redirect_stderr(err2):
                rc2 = cli_main(["migrate-data", "--apply", "--json"])
            self.assertEqual(rc2, 0)
            data2 = json.loads(buf2.getvalue())
            self.assertTrue(data2["ok"])
            self.assertTrue(data2["applied"])


if __name__ == "__main__":
    unittest.main()
