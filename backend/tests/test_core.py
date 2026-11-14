"""Unit and integration tests for backend/core (Milestone S1)."""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import shutil
import stat
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

from backend.core import constants
from backend.core.include_block import (
    IncludeBlockError,
    has_include,
    insert_include,
    remove_include,
    render_include_block,
)
from backend.core.overrides import (
    OverridesError,
    create_overrides_text,
    parse_sections,
    remove_section,
    render_config_call,
    replace_section,
    serialize_lua_value,
)
from backend.core.revert_guard import arm, cancel, confirm
from backend.core.revert_watchdog import run_revert_watchdog
from backend.core.transaction import (
    apply_managed_change,
    install_include,
    uninstall_include,
    undo_managed_change,
)
from backend.tests.isolation import IsolatedTestCase, FORBIDDEN_REAL_PATHS


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class TestIncludeBlock(unittest.TestCase):
    def test_render_include_block_uses_constants_and_pcall_dofile(self) -> None:
        block = render_include_block()
        self.assertIn(constants.INCLUDE_BEGIN_MARKER, block)
        self.assertIn(constants.INCLUDE_END_MARKER, block)
        self.assertIn("pcall(dofile", block)
        self.assertIn('os.getenv("HOME")', block)
        self.assertIn(constants.OVERRIDES_FILENAME, block)

    def test_round_trip_byte_for_byte_and_idempotent(self) -> None:
        samples = [
            "",
            "\n",
            "local a = 1",
            "local a = 1\n",
            "local a = 1\n\n-- trailing comment\n",
            "-- header\nhl.bind(\"SUPER + Return\", hl.dsp.exec_cmd(\"kitty\"))\n",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertFalse(has_include(sample))
                inserted = insert_include(sample)
                self.assertTrue(has_include(inserted))
                self.assertTrue(inserted.startswith(sample))
                # Idempotent
                self.assertEqual(insert_include(inserted), inserted)
                # Byte-for-byte round trip
                removed = remove_include(inserted)
                self.assertEqual(removed, sample)
                # Idempotent remove
                self.assertEqual(remove_include(removed), removed)

    def test_malformed_markers_raise(self) -> None:
        b = constants.INCLUDE_BEGIN_MARKER
        e = constants.INCLUDE_END_MARKER
        malformed = [
            f"{b}\nlocal x = 1\n",
            f"local x = 1\n{e}\n",
            f"{b}\n{b}\n{e}\n",
            f"{b}\n{e}\n{e}\n",
            f"{e}\n{b}\n",
        ]
        for text in malformed:
            with self.subTest(text=text):
                with self.assertRaises(IncludeBlockError):
                    has_include(text)
                with self.assertRaises(IncludeBlockError):
                    insert_include(text)
                with self.assertRaises(IncludeBlockError):
                    remove_include(text)


class TestOverrides(unittest.TestCase):
    def test_serialize_lua_value_golden_and_deterministic(self) -> None:
        self.assertEqual(serialize_lua_value(True), "true")
        self.assertEqual(serialize_lua_value(False), "false")
        self.assertEqual(serialize_lua_value(42), "42")
        self.assertEqual(serialize_lua_value(-7), "-7")
        self.assertEqual(serialize_lua_value(1.25), "1.25")
        self.assertEqual(serialize_lua_value([1, "two", False]), '{ 1, "two", false }')
        self.assertEqual(
            serialize_lua_value({"z": 1, "a": 2}),
            "{ a = 2, z = 1 }",
        )
        self.assertEqual(
            render_config_call({"general": {"gaps_in": 9, "border_size": 2}}),
            "hl.config({ general = { border_size = 2, gaps_in = 9 } })",
        )

    def test_serialize_rejects_invalid_values_and_keys(self) -> None:
        for bad in (None, float("nan"), float("inf"), float("-inf"), object()):
            with self.subTest(bad=bad):
                with self.assertRaises((TypeError, ValueError)):
                    serialize_lua_value(bad)

        for bad_key in ("a-b", "1abc", "", "local", "end", "true", "a b", 123):
            with self.subTest(bad_key=bad_key):
                with self.assertRaises((TypeError, ValueError)):
                    serialize_lua_value({bad_key: 1})

    def test_string_injection_cases(self) -> None:
        cases = {
            'a"b': '"a\\"b"',
            "a\\b": '"a\\\\b"',
            "a\nb\rc": '"a\\nb\\rc"',
            "foo]]bar": '"foo]]bar"',
            "café 🚀": '"café 🚀"',
            "$HOME/.config": '"$HOME/.config"',
            '"leading': '"\\"leading"',
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(serialize_lua_value(raw), expected)

    def test_section_replace_remove_and_preserve_outside(self) -> None:
        doc = create_overrides_text()
        self.assertTrue(doc.startswith(constants.OVERRIDES_HEADER))

        # Existing file with custom content outside markers should be preserved verbatim
        custom = "-- user custom comment\nlocal my_var = 123\n"
        updated = replace_section(custom, "display", 'hl.monitor({ output = "eDP-1" })')
        self.assertIn(custom, updated)
        self.assertNotIn(constants.OVERRIDES_HEADER, updated)
        self.assertEqual(
            parse_sections(updated),
            {"display": 'hl.monitor({ output = "eDP-1" })'},
        )

        # Add a second section, then update the first
        updated2 = replace_section(updated, "general", "hl.config({ general = { gaps_in = 9 } })")
        updated3 = replace_section(updated2, "display", 'hl.monitor({ output = "HDMI-A-1" })')
        sections = parse_sections(updated3)
        self.assertEqual(
            sections,
            {
                "display": 'hl.monitor({ output = "HDMI-A-1" })',
                "general": "hl.config({ general = { gaps_in = 9 } })",
            },
        )
        self.assertIn(custom, updated3)

        # Remove section
        removed = remove_section(updated3, "display")
        self.assertEqual(
            parse_sections(removed),
            {"general": "hl.config({ general = { gaps_in = 9 } })"},
        )
        self.assertIn(custom, removed)
        # Idempotent remove
        self.assertEqual(remove_section(removed, "nonexistent"), removed)

    def test_malformed_section_markers_raise(self) -> None:
        bad_text = constants.section_begin_marker("foo") + "\nlocal x = 1\n"
        with self.assertRaises(OverridesError):
            parse_sections(bad_text)


class TestTransaction(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.cfg_dir = os.path.join(self._isolated_root, "hypr")
        os.makedirs(self.cfg_dir, exist_ok=True)
        self.entry = os.path.join(self.cfg_dir, "hyprland.lua")
        self.base_lua = (
            'hl.bind("SUPER + Return", hl.dsp.exec_cmd("kitty"))\n'
        )
        with open(self.entry, "wb") as f:
            f.write(self.base_lua.encode("utf-8"))
        self.base_sha = _sha256_bytes(self.base_lua.encode("utf-8"))

    def _ok_hyprland_runner(self, argv, **kwargs):
        return subprocess.CompletedProcess(
            argv, 0, stdout="Config parsing result:\nconfig ok\n", stderr=""
        )

    def _recording_reload_runner(self, calls: list[list[str]], fail_on: str | None = None, configerrors_out: str = ""):
        def runner(argv, **kwargs):
            calls.append(list(argv))
            if fail_on and fail_on in " ".join(argv):
                return subprocess.CompletedProcess(argv, 1, stdout="", stderr="reload failed")
            if argv == ["hyprctl", "configerrors"]:
                return subprocess.CompletedProcess(argv, 0, stdout=configerrors_out, stderr="")
            return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")
        return runner

    def test_dry_run_default_writes_nothing(self) -> None:
        new_bytes = (self.base_lua + "-- comment\n").encode("utf-8")
        res = apply_managed_change(
            self.entry,
            new_bytes,
            expected_sha256=self.base_sha,
            config_dir=self.cfg_dir,
            entrypoint=self.entry,
            reload_mode="config-only",
            backup_dir=self.backup_dir,
            hyprland_runner=self._ok_hyprland_runner,
            sleep_fn=lambda _: None,
        )
        self.assertFalse(res.applied)
        self.assertEqual(res.errors, [])
        self.assertIn("+-- comment", res.diff)
        with open(self.entry, "rb") as f:
            self.assertEqual(f.read(), self.base_lua.encode("utf-8"))

    def test_sha_mismatch_refuses(self) -> None:
        res = apply_managed_change(
            self.entry,
            (self.base_lua + "-- comment\n").encode("utf-8"),
            expected_sha256="0" * 64,
            config_dir=self.cfg_dir,
            entrypoint=self.entry,
            reload_mode="none",
            backup_dir=self.backup_dir,
            hyprland_runner=self._ok_hyprland_runner,
            dry_run=False,
        )
        self.assertFalse(res.applied)
        self.assertTrue(res.errors)
        with open(self.entry, "rb") as f:
            self.assertEqual(f.read(), self.base_lua.encode("utf-8"))

    def test_verify_failure_writes_nothing(self) -> None:
        def bad_hyprland(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 1, stdout="syntax error", stderr="err")

        res = apply_managed_change(
            self.entry,
            (self.base_lua + "-- added\n").encode("utf-8"),
            expected_sha256=self.base_sha,
            config_dir=self.cfg_dir,
            entrypoint=self.entry,
            reload_mode="none",
            backup_dir=self.backup_dir,
            hyprland_runner=bad_hyprland,
            dry_run=False,
        )
        self.assertFalse(res.applied)
        self.assertTrue(res.errors)
        with open(self.entry, "rb") as f:
            self.assertEqual(f.read(), self.base_lua.encode("utf-8"))

    def test_bind_set_difference_refuses(self) -> None:
        new_lua = self.base_lua + 'hl.bind("SUPER + X", hl.dsp.exec_cmd("foot"))\n'
        res = apply_managed_change(
            self.entry,
            new_lua.encode("utf-8"),
            expected_sha256=self.base_sha,
            config_dir=self.cfg_dir,
            entrypoint=self.entry,
            reload_mode="none",
            require_binds_unchanged=True,
            backup_dir=self.backup_dir,
            hyprland_runner=self._ok_hyprland_runner,
            dry_run=False,
        )
        self.assertFalse(res.applied)
        self.assertTrue(any("bind" in e.lower() for e in res.errors))
        with open(self.entry, "rb") as f:
            self.assertEqual(f.read(), self.base_lua.encode("utf-8"))

    def test_toctou_change_refuses(self) -> None:
        new_bytes = (self.base_lua + "-- safe\n").encode("utf-8")

        def mutating_hyprland(argv, **kwargs):
            # Simulate concurrent external edit during verify stage
            with open(self.entry, "ab") as f:
                f.write(b"-- external\n")
            return subprocess.CompletedProcess(
                argv, 0, stdout="Config parsing result:\nconfig ok\n", stderr=""
            )

        res = apply_managed_change(
            self.entry,
            new_bytes,
            expected_sha256=self.base_sha,
            config_dir=self.cfg_dir,
            entrypoint=self.entry,
            reload_mode="none",
            backup_dir=self.backup_dir,
            hyprland_runner=mutating_hyprland,
            dry_run=False,
        )
        self.assertFalse(res.applied)
        self.assertTrue(any("concurrent" in e.lower() or "toctou" in e.lower() or "sha" in e.lower() for e in res.errors))

    def test_post_write_mismatch_restores(self) -> None:
        new_bytes = (self.base_lua + "-- safe\n").encode("utf-8")
        with mock.patch("backend.core.transaction.compute_file_sha256", side_effect=[self.base_sha, "f" * 64]):
            res = apply_managed_change(
                self.entry,
                new_bytes,
                expected_sha256=self.base_sha,
                config_dir=self.cfg_dir,
                entrypoint=self.entry,
                reload_mode="none",
                backup_dir=self.backup_dir,
                hyprland_runner=self._ok_hyprland_runner,
                dry_run=False,
            )
        self.assertFalse(res.applied)
        self.assertTrue(res.rolled_back)
        with open(self.entry, "rb") as f:
            self.assertEqual(f.read(), self.base_lua.encode("utf-8"))

    def test_reload_failure_restores_and_re_reloads(self) -> None:
        calls: list[list[str]] = []
        new_bytes = (self.base_lua + "-- safe\n").encode("utf-8")
        res = apply_managed_change(
            self.entry,
            new_bytes,
            expected_sha256=self.base_sha,
            config_dir=self.cfg_dir,
            entrypoint=self.entry,
            reload_mode="config-only",
            backup_dir=self.backup_dir,
            hyprland_runner=self._ok_hyprland_runner,
            reload_runner=self._recording_reload_runner(calls, configerrors_out="invalid option"),
            sleep_fn=lambda _: None,
            dry_run=False,
        )
        self.assertFalse(res.applied)
        self.assertTrue(res.rolled_back)
        # File restored
        with open(self.entry, "rb") as f:
            self.assertEqual(f.read(), self.base_lua.encode("utf-8"))
        # Reload called for apply AND again after rollback
        reload_calls = [c for c in calls if c[:2] == ["hyprctl", "reload"]]
        self.assertEqual(len(reload_calls), 2)
        self.assertEqual(reload_calls[0], ["hyprctl", "reload", "config-only"])
        self.assertEqual(reload_calls[1], ["hyprctl", "reload", "config-only"])

    def test_reload_modes_exact_argv_and_created_file_undo(self) -> None:
        for mode, expected_argv in [
            ("none", None),
            ("config-only", ["hyprctl", "reload", "config-only"]),
            ("full", ["hyprctl", "reload"]),
        ]:
            with self.subTest(mode=mode):
                calls: list[list[str]] = []
                target = os.path.join(self.cfg_dir, f"extra_{mode.replace('-', '_')}.lua")
                res = apply_managed_change(
                    target,
                    b"-- created\n",
                    expected_sha256=constants.SHA256_ABSENT,
                    config_dir=self.cfg_dir,
                    entrypoint=self.entry,
                    reload_mode=mode,
                    backup_dir=self.backup_dir,
                    hyprland_runner=self._ok_hyprland_runner,
                    reload_runner=self._recording_reload_runner(calls),
                    sleep_fn=lambda _: None,
                    dry_run=False,
                )
                self.assertTrue(res.applied)
                self.assertTrue(res.created)
                self.assertTrue(os.path.isfile(target))
                if expected_argv is None:
                    self.assertEqual(calls, [])
                else:
                    self.assertEqual(calls[0], expected_argv)
                    self.assertEqual(calls[1], ["hyprctl", "configerrors"])

                # Undo deletes created file
                undo_res = undo_managed_change(
                    res,
                    backup_dir=self.backup_dir,
                    reload_runner=self._recording_reload_runner(calls),
                    sleep_fn=lambda _: None,
                )
                self.assertTrue(undo_res.applied)
                self.assertFalse(os.path.exists(target))

    def test_install_and_uninstall_include_and_refuse_hyprlang(self) -> None:
        conf_entry = os.path.join(self.cfg_dir, "hyprland.conf")
        with open(conf_entry, "w", encoding="utf-8") as f:
            f.write("bind = SUPER, Return, exec, kitty\n")
        conf_res = install_include(
            self.cfg_dir,
            conf_entry,
            backup_dir=self.backup_dir,
            dry_run=False,
        )
        self.assertFalse(conf_res.applied)
        self.assertTrue(any("lua" in e.lower() for e in conf_res.errors))

        calls: list[list[str]] = []
        res = install_include(
            self.cfg_dir,
            self.entry,
            expected_sha256=self.base_sha,
            backup_dir=self.backup_dir,
            hyprland_runner=self._ok_hyprland_runner,
            reload_runner=self._recording_reload_runner(calls),
            sleep_fn=lambda _: None,
            dry_run=False,
        )
        self.assertTrue(res.applied)
        self.assertEqual(res.reload_mode, "config-only")
        self.assertTrue(os.path.isfile(os.path.join(self.cfg_dir, constants.OVERRIDES_FILENAME)))
        with open(self.entry, "r", encoding="utf-8") as f:
            self.assertTrue(has_include(f.read()))

        un_res = uninstall_include(
            self.cfg_dir,
            self.entry,
            expected_sha256=res.sha_after,
            backup_dir=self.backup_dir,
            hyprland_runner=self._ok_hyprland_runner,
            reload_runner=self._recording_reload_runner(calls),
            sleep_fn=lambda _: None,
            dry_run=False,
        )
        self.assertTrue(un_res.applied)
        with open(self.entry, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), self.base_lua)


class TestRevertWatchdog(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.state_dir = os.path.join(self._isolated_root, "state")
        os.makedirs(self.state_dir, exist_ok=True)
        self._orig_state_env = os.environ.get(constants.ENV_STATE_DIR)
        os.environ[constants.ENV_STATE_DIR] = self.state_dir
        self.addCleanup(self._restore_state_env)

        self.cfg_dir = os.path.join(self._isolated_root, "hypr")
        os.makedirs(self.cfg_dir, exist_ok=True)
        self.target = os.path.join(self.cfg_dir, "hks-overrides.lua")
        self.orig_bytes = b"-- original\n"
        self.new_bytes = b"-- changed\n"
        with open(self.target, "wb") as f:
            f.write(self.orig_bytes)

        from backend.editor.backups import create_backup, atomic_write_bytes
        self.bkp = create_backup(self.target, backup_dir=self.backup_dir, config_dir=self.cfg_dir)
        atomic_write_bytes(self.target, self.new_bytes)
        self.new_sha = _sha256_bytes(self.new_bytes)

    def _restore_state_env(self) -> None:
        if self._orig_state_env is None:
            os.environ.pop(constants.ENV_STATE_DIR, None)
        else:
            os.environ[constants.ENV_STATE_DIR] = self._orig_state_env

    def test_plan_mode_is_0600_and_timeout_reverts(self) -> None:
        handle = arm(
            {
                "backup_id": self.bkp.id,
                "backup_dir": self.backup_dir,
                "target_path": self.target,
                "expected_current_sha256": self.new_sha,
                "created": False,
                "reload_mode": "none",
            },
            timeout_seconds=0.4,
            watch_pid=os.getpid(),
            state_dir=self.state_dir,
        )
        try:
            mode = stat.S_IMODE(os.stat(handle.plan_path).st_mode)
            self.assertEqual(mode, 0o600)
            deadline = time.monotonic() + 4.0
            while time.monotonic() < deadline:
                with open(self.target, "rb") as f:
                    if f.read() == self.orig_bytes:
                        break
                time.sleep(0.05)
            with open(self.target, "rb") as f:
                self.assertEqual(f.read(), self.orig_bytes)
        finally:
            cancel(handle)

    def test_confirm_first_prevents_revert(self) -> None:
        handle = arm(
            {
                "backup_id": self.bkp.id,
                "backup_dir": self.backup_dir,
                "target_path": self.target,
                "expected_current_sha256": self.new_sha,
                "created": False,
                "reload_mode": "none",
            },
            timeout_seconds=0.6,
            watch_pid=os.getpid(),
            state_dir=self.state_dir,
        )
        try:
            confirm(handle)
            time.sleep(0.9)
            with open(self.target, "rb") as f:
                self.assertEqual(f.read(), self.new_bytes)
        finally:
            cancel(handle)

    def test_parent_pid_dies_reverts_early(self) -> None:
        # Spawn a short-lived dummy parent process and watch its PID
        dummy = subprocess.Popen(["sleep", "30"])
        try:
            handle = arm(
                {
                    "backup_id": self.bkp.id,
                    "backup_dir": self.backup_dir,
                    "target_path": self.target,
                    "expected_current_sha256": self.new_sha,
                    "created": False,
                    "reload_mode": "none",
                },
                timeout_seconds=30.0,
                watch_pid=dummy.pid,
                state_dir=self.state_dir,
            )
            dummy.kill()
            dummy.wait(timeout=5.0)
            deadline = time.monotonic() + 4.0
            while time.monotonic() < deadline:
                with open(self.target, "rb") as f:
                    if f.read() == self.orig_bytes:
                        break
                time.sleep(0.05)
            with open(self.target, "rb") as f:
                self.assertEqual(f.read(), self.orig_bytes)
        finally:
            if dummy.poll() is None:
                dummy.kill()
                dummy.wait()

    def test_target_changed_by_someone_else_skips_revert_and_idempotent(self) -> None:
        external = b"-- someone else edited\n"
        with open(self.target, "wb") as f:
            f.write(external)

        plan_path = os.path.join(self.state_dir, "plan.json")
        confirm_path = os.path.join(self.state_dir, "confirm")
        log_path = os.path.join(self.state_dir, "wd.log")
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "backup_id": self.bkp.id,
                    "backup_dir": self.backup_dir,
                    "target_path": self.target,
                    "expected_current_sha256": self.new_sha,
                    "created": False,
                    "reload_mode": "none",
                    "confirm_path": confirm_path,
                    "log_path": log_path,
                },
                f,
            )
        rc1 = run_revert_watchdog(plan_path=plan_path, timeout_seconds=0.05, watch_pid=0)
        self.assertEqual(rc1, 0)
        with open(self.target, "rb") as f:
            self.assertEqual(f.read(), external)
        with open(log_path, "r", encoding="utf-8") as f:
            self.assertIn("concurrent", f.read().lower())

        # Restore to new_bytes, run once (reverts), then run second time (no-op)
        with open(self.target, "wb") as f:
            f.write(self.new_bytes)
        rc2 = run_revert_watchdog(plan_path=plan_path, timeout_seconds=0.05, watch_pid=0)
        self.assertEqual(rc2, 0)
        with open(self.target, "rb") as f:
            self.assertEqual(f.read(), self.orig_bytes)

        rc3 = run_revert_watchdog(plan_path=plan_path, timeout_seconds=0.05, watch_pid=0)
        self.assertEqual(rc3, 0)
        with open(self.target, "rb") as f:
            self.assertEqual(f.read(), self.orig_bytes)


class TestCoreIsolation(IsolatedTestCase):
    def test_refuses_real_paths(self) -> None:
        real_hypr = FORBIDDEN_REAL_PATHS[0]
        real_hks_share = FORBIDDEN_REAL_PATHS[2]
        with self.assertRaises(AssertionError):
            apply_managed_change(
                os.path.join(real_hypr, "hyprland.lua"),
                b"x",
                expected_sha256="a" * 64,
                config_dir=real_hypr,
                entrypoint=os.path.join(real_hypr, "hyprland.lua"),
                reload_mode="none",
            )
        with self.assertRaises(AssertionError):
            arm(
                {
                    "backup_id": "x",
                    "backup_dir": real_hks_share,
                    "target_path": os.path.join(real_hypr, "hks-overrides.lua"),
                    "expected_current_sha256": "a" * 64,
                    "created": False,
                    "reload_mode": "none",
                },
                timeout_seconds=1.0,
                state_dir=real_hks_share,
            )


class TestCoreCLI(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.cfg_dir = os.path.join(self._isolated_root, "hypr")
        os.makedirs(self.cfg_dir, exist_ok=True)
        self.entry = os.path.join(self.cfg_dir, "hyprland.lua")
        self.base_lua = 'hl.bind("SUPER + Return", hl.dsp.exec_cmd("kitty"))\n'
        with open(self.entry, "w", encoding="utf-8") as f:
            f.write(self.base_lua)
        self.base_sha = _sha256_bytes(self.base_lua.encode("utf-8"))

    def test_overrides_status_and_install_include_cli(self) -> None:
        from backend.cli import main as cli_main

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_main([
                "overrides", "status",
                "--config-dir", self.cfg_dir,
                "--entrypoint", self.entry,
                "--no-live",
                "--json",
            ])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertFalse(data["include_installed"])
        self.assertFalse(data["overrides_present"])
        self.assertEqual(data["language"], "lua")

        # --apply without --scan-sha256 refuses
        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = cli_main([
                "overrides", "install-include",
                "--config-dir", self.cfg_dir,
                "--entrypoint", self.entry,
                "--no-live",
                "--apply",
                "--json",
            ])
        self.assertNotEqual(rc2, 0)

        # dry-run succeeds without writing
        buf3 = io.StringIO()
        with redirect_stdout(buf3):
            with mock.patch("backend.core.transaction.verify_with_hyprland") as m_ver:
                m_ver.return_value = mock.Mock(ok=True, to_dict=lambda: {"ok": True})
                rc3 = cli_main([
                    "overrides", "install-include",
                    "--config-dir", self.cfg_dir,
                    "--entrypoint", self.entry,
                    "--no-live",
                    "--json",
                ])
        self.assertEqual(rc3, 0)
        self.assertFalse(json.loads(buf3.getvalue())["applied"])
        with open(self.entry, "r", encoding="utf-8") as f:
            self.assertFalse(has_include(f.read()))

        # --apply with --scan-sha256 writes
        buf4 = io.StringIO()
        with redirect_stdout(buf4):
            with mock.patch("backend.core.transaction.verify_with_hyprland") as m_ver:
                m_ver.return_value = mock.Mock(ok=True, to_dict=lambda: {"ok": True})
                rc4 = cli_main([
                    "overrides", "install-include",
                    "--config-dir", self.cfg_dir,
                    "--entrypoint", self.entry,
                    "--no-live",
                    "--apply",
                    "--scan-sha256", self.base_sha,
                    "--json",
                ])
        self.assertEqual(rc4, 0)
        self.assertTrue(json.loads(buf4.getvalue())["applied"])
        with open(self.entry, "r", encoding="utf-8") as f:
            self.assertTrue(has_include(f.read()))


if __name__ == "__main__":
    unittest.main()
