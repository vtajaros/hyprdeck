"""Unit and integration tests for generic confirm-or-revert flow (backend/core/confirm_flow.py)."""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
import warnings
from unittest import mock

from backend.core import confirm_flow as cf_mod
from backend.core import revert_guard
from backend.core.confirm_flow import (
    DEFAULT_CONFIRM_TIMEOUT_SECONDS,
    ConfirmDomainValidation,
    apply_with_confirm_flow,
    confirm_flow_changes,
    revert_flow_changes,
)
from backend.core.constants import OVERRIDES_FILENAME, SHA256_ABSENT
from backend.core.include_block import insert_include
from backend.core.overrides import replace_section
from backend.editor.backups import compute_file_sha256
from backend.tests.isolation import IsolatedTestCase


def _ok_proc(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _ok_reload(argv, *a, **k) -> subprocess.CompletedProcess[str]:
    if "configerrors" in argv:
        return _ok_proc("")
    return _ok_proc("ok\n")


class TestConfirmFlow(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._rw = warnings.catch_warnings()
        self._rw.__enter__()
        warnings.simplefilter("ignore", ResourceWarning)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_root = self._tmp.name
        self.cfg_dir = os.path.join(self.tmp_root, "cfg")
        self.backup_dir = os.path.join(self.tmp_root, "backups")
        self.state_dir = os.path.join(self.tmp_root, "state")
        os.makedirs(self.cfg_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
        os.makedirs(self.state_dir, exist_ok=True)
        self.entry = os.path.join(self.cfg_dir, "hyprland.lua")
        with open(self.entry, "w", encoding="utf-8") as f:
            f.write(insert_include("-- base config\n"))
        self.ov_path = os.path.join(self.cfg_dir, OVERRIDES_FILENAME)
        with open(self.ov_path, "w", encoding="utf-8") as f:
            f.write(replace_section("", "demo", "hl.config({ demo = { val = 1 } })"))
        self.base_sha = compute_file_sha256(self.ov_path)

    def tearDown(self) -> None:
        try:
            self._rw.__exit__(None, None, None)
        finally:
            super().tearDown()

    def test_timeout_constant_is_15s_and_dry_run_writes_nothing(self) -> None:
        self.assertEqual(DEFAULT_CONFIRM_TIMEOUT_SECONDS, 15.0)

        def validator(existing_text: str | None) -> ConfirmDomainValidation:
            body = "hl.config({ demo = { val = 2 } })"
            return ConfirmDomainValidation(
                section_body=body,
                warnings=["non-blocking warning"],
            )

        res = apply_with_confirm_flow(
            section_name="demo",
            domain_validator=validator,
            config_dir=self.cfg_dir,
            entrypoint=self.entry,
            expected_sha256=self.base_sha,
            reload_mode="config-only",
            backup_dir=self.backup_dir,
            state_dir=self.state_dir,
            hyprland_runner=lambda *a, **k: _ok_proc("config ok\n"),
            reload_runner=lambda *a, **k: _ok_proc("ok\n"),
            sleep_fn=lambda _: None,
            dry_run=True,
        )
        self.assertFalse(res.applied)
        self.assertEqual(res.errors, [])
        self.assertEqual(res.warnings, ["non-blocking warning"])
        self.assertIn("val = 2", res.diff)
        self.assertEqual(compute_file_sha256(self.ov_path), self.base_sha)

    def test_arm_called_strictly_before_apply_and_fail_closed_if_arm_fails(self) -> None:
        events: list[str] = []
        orig_arm = revert_guard.arm
        orig_apply = cf_mod.apply_managed_change

        def spy_arm(*args, **kwargs):
            events.append("arm")
            return orig_arm(*args, **kwargs)

        def spy_apply(*args, **kwargs):
            events.append("apply")
            return orig_apply(*args, **kwargs)

        def validator(_: str | None) -> ConfirmDomainValidation:
            return ConfirmDomainValidation(section_body="hl.config({ demo = { val = 2 } })")

        with mock.patch.object(cf_mod.revert_guard, "arm", side_effect=spy_arm), mock.patch.object(
            cf_mod, "apply_managed_change", side_effect=spy_apply
        ):
            res = apply_with_confirm_flow(
                section_name="demo",
                domain_validator=validator,
                config_dir=self.cfg_dir,
                entrypoint=self.entry,
                expected_sha256=self.base_sha,
                reload_mode="config-only",
                timeout_seconds=1.0,
                backup_dir=self.backup_dir,
                state_dir=self.state_dir,
                hyprland_runner=lambda *a, **k: _ok_proc("config ok\n"),
                reload_runner=_ok_reload,
                sleep_fn=lambda _: None,
                dry_run=False,
            )
            self.assertTrue(res.applied, res.errors)
            self.assertEqual(events, ["arm", "apply"])
            confirm_flow_changes(handle=res.handle, state_dir=self.state_dir)

        # Fail closed if arm fails: apply_managed_change must never be called
        with mock.patch.object(
            cf_mod.revert_guard, "arm", side_effect=revert_guard.RevertGuardError("boom")
        ), mock.patch.object(cf_mod, "apply_managed_change") as mock_apply:
            res_fail = apply_with_confirm_flow(
                section_name="demo",
                domain_validator=validator,
                config_dir=self.cfg_dir,
                entrypoint=self.entry,
                expected_sha256=compute_file_sha256(self.ov_path),
                reload_mode="config-only",
                backup_dir=self.backup_dir,
                state_dir=self.state_dir,
                hyprland_runner=lambda *a, **k: _ok_proc("config ok\n"),
                reload_runner=_ok_reload,
                sleep_fn=lambda _: None,
                dry_run=False,
            )
            self.assertFalse(res_fail.applied)
            mock_apply.assert_not_called()

    def test_confirm_revert_and_timeout_auto_revert(self) -> None:
        def validator_to(val: int):
            def _fn(_: str | None) -> ConfirmDomainValidation:
                return ConfirmDomainValidation(section_body=f"hl.config({{ demo = {{ val = {val} }} }})")
            return _fn

        # 1. Confirm cancels watchdog
        res1 = apply_with_confirm_flow(
            section_name="demo",
            domain_validator=validator_to(2),
            config_dir=self.cfg_dir,
            entrypoint=self.entry,
            expected_sha256=self.base_sha,
            reload_mode="none",
            timeout_seconds=0.4,
            backup_dir=self.backup_dir,
            state_dir=self.state_dir,
            hyprland_runner=lambda *a, **k: _ok_proc("config ok\n"),
            sleep_fn=lambda _: None,
            dry_run=False,
        )
        self.assertTrue(res1.applied)
        conf = confirm_flow_changes(handle=res1.handle, state_dir=self.state_dir)
        self.assertTrue(conf["confirmed"])
        time.sleep(0.6)
        with open(self.ov_path, "r", encoding="utf-8") as f:
            self.assertIn("val = 2", f.read())

        # 2. Explicit revert
        res2 = apply_with_confirm_flow(
            section_name="demo",
            domain_validator=validator_to(3),
            config_dir=self.cfg_dir,
            entrypoint=self.entry,
            expected_sha256=compute_file_sha256(self.ov_path),
            reload_mode="none",
            timeout_seconds=5.0,
            backup_dir=self.backup_dir,
            state_dir=self.state_dir,
            hyprland_runner=lambda *a, **k: _ok_proc("config ok\n"),
            sleep_fn=lambda _: None,
            dry_run=False,
        )
        self.assertTrue(res2.applied)
        rev = revert_flow_changes(handle=res2.handle, state_dir=self.state_dir)
        self.assertTrue(rev["reverted"])
        with open(self.ov_path, "r", encoding="utf-8") as f:
            self.assertIn("val = 2", f.read())

        # 3. No confirm -> timeout reverts
        res3 = apply_with_confirm_flow(
            section_name="demo",
            domain_validator=validator_to(4),
            config_dir=self.cfg_dir,
            entrypoint=self.entry,
            expected_sha256=compute_file_sha256(self.ov_path),
            reload_mode="none",
            timeout_seconds=0.35,
            backup_dir=self.backup_dir,
            state_dir=self.state_dir,
            hyprland_runner=lambda *a, **k: _ok_proc("config ok\n"),
            sleep_fn=lambda _: None,
            dry_run=False,
        )
        self.assertTrue(res3.applied)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            with open(self.ov_path, "r", encoding="utf-8") as f:
                if "val = 2" in f.read():
                    break
            time.sleep(0.05)
        with open(self.ov_path, "r", encoding="utf-8") as f:
            self.assertIn("val = 2", f.read())
