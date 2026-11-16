"""Unit tests for the HKS Phase 4a safe edit engine (temp dirs and fixtures only)."""

from __future__ import annotations

import contextlib
import hashlib
import io
import os
import stat
import subprocess
import tempfile
import unittest
from typing import Any
from unittest import mock

from backend.cli import main as cli_main, run_scan_pipeline
from backend.editor import (
    BackupConflictError,
    BackupError,
    EditConflict,
    EditOp,
    NotEditableError,
    RecorderVerificationError,
    apply_edit,
    apply_ops_to_text,
    atomic_write_bytes,
    build_op_for_bind,
    compute_file_sha256,
    create_backup,
    detect_disabled_binds,
    generate_unified_diff,
    list_backups,
    restore_backup,
    stage_candidate_config,
    verify_with_hyprland,
    verify_with_recorder,
)
from backend.models.types import BindRecord, DispatcherInfo, default_flags
from backend.validation.schema_validator import validate_scan_dict


def _make_dummy_bind(
    *,
    bind_id: str = "b_123456789abc",
    language: str = "lua",
    source_file: str = "/tmp/fake/hyprland.lua",
    source_line: int = 10,
    original_line: str = 'hl.bind("SUPER + Return", hl.dsp.exec_cmd("kitty"))',
    generated: bool = False,
    occurrences_at_site: int = 1,
) -> BindRecord:
    return BindRecord(
        id=bind_id,
        language=language,
        bind_type="bind",
        declared_via="bind",
        modifiers=["SUPER"],
        modifiers_raw="SUPER",
        modmask=64,
        key="Return",
        key_kind="keysym",
        keys_raw="SUPER + Return",
        flags=default_flags(),
        flags_extra={},
        description=None,
        dispatcher=DispatcherInfo(path="exec_cmd", args=["kitty"], arg_summary="kitty"),
        submap="",
        source_file=source_file,
        source_line=source_line,
        original_line=original_line,
        original_line_number=source_line,
        generated=generated,
        occurrence=0,
        occurrences_at_site=occurrences_at_site,
        trace=[],
        parse_status="ok",
    )


class TestEditPlan(unittest.TestCase):
    def test_lua_and_hyprlang_comment_uncomment_round_trip_byte_identical(self) -> None:
        lua_text = (
            "-- Header comment\n"
            'local mainMod = "SUPER"\n'
            '    hl.bind(mainMod .. " + Return", hl.dsp.exec_cmd("kitty")) -- inline\n'
            'hl.bind(mainMod .. " + Q", hl.dsp.window.close())\n'
        )
        op_comment = EditOp(
            kind="comment_out",
            file="/tmp/hyprland.lua",
            line_number=3,
            expected_text='    hl.bind(mainMod .. " + Return", hl.dsp.exec_cmd("kitty")) -- inline',
            language="lua",
        )
        commented = apply_ops_to_text(lua_text, [op_comment])
        self.assertIn(
            '-- HKS-disabled:     hl.bind(mainMod .. " + Return", hl.dsp.exec_cmd("kitty")) -- inline\n',
            commented,
        )

        op_uncomment = EditOp(
            kind="uncomment",
            file="/tmp/hyprland.lua",
            line_number=3,
            expected_text='-- HKS-disabled:     hl.bind(mainMod .. " + Return", hl.dsp.exec_cmd("kitty")) -- inline',
            language="lua",
        )
        restored = apply_ops_to_text(commented, [op_uncomment])
        self.assertEqual(lua_text.encode("utf-8"), restored.encode("utf-8"))

        # Hyprlang (.conf)
        conf_text = (
            "$mainMod = SUPER\n"
            "bind = $mainMod, Return, exec, kitty\n"
            "bind = $mainMod, X, killactive,\n"
        )
        conf_comment = EditOp(
            kind="comment_out",
            file="/tmp/hyprland.conf",
            line_number=2,
            expected_text="bind = $mainMod, Return, exec, kitty",
        )
        conf_commented = apply_ops_to_text(conf_text, [conf_comment])
        self.assertIn("# HKS-disabled: bind = $mainMod, Return, exec, kitty\n", conf_commented)

        conf_uncomment = EditOp(
            kind="uncomment",
            file="/tmp/hyprland.conf",
            line_number=2,
            expected_text="# HKS-disabled: bind = $mainMod, Return, exec, kitty",
        )
        conf_restored = apply_ops_to_text(conf_commented, [conf_uncomment])
        self.assertEqual(conf_text.encode("utf-8"), conf_restored.encode("utf-8"))

    def test_expected_text_mismatch_raises_edit_conflict(self) -> None:
        text = "line 1\nline 2\nline 3\n"
        ops = [
            EditOp(
                kind="comment_out",
                file="test.conf",
                line_number=2,
                expected_text="wrong line 2",
            ),
            EditOp(
                kind="replace_line",
                file="test.conf",
                line_number=3,
                expected_text="wrong line 3",
                new_text="new line 3",
            ),
        ]
        with self.assertRaises(EditConflict) as ctx:
            apply_ops_to_text(text, ops)
        self.assertEqual(len(ctx.exception.mismatches), 2)
        self.assertIn("test.conf:2", str(ctx.exception))
        self.assertIn("test.conf:3", str(ctx.exception))

    def test_crlf_and_missing_trailing_newline_preserved(self) -> None:
        raw = "first = 1\r\nsecond = 2\r\nthird = 3"
        op1 = EditOp(
            kind="comment_out",
            file="hyprland.conf",
            line_number=1,
            expected_text="first = 1",
        )
        op3 = EditOp(
            kind="comment_out",
            file="hyprland.conf",
            line_number=3,
            expected_text="third = 3",
        )
        modified = apply_ops_to_text(raw, [op1, op3])
        self.assertEqual(
            modified,
            "# HKS-disabled: first = 1\r\nsecond = 2\r\n# HKS-disabled: third = 3",
        )
        self.assertFalse(modified.endswith("\n"))
        self.assertFalse(modified.endswith("\r"))

        # Round-trip uncomment preserves CRLF and missing trailing newline
        un1 = EditOp(
            kind="uncomment",
            file="hyprland.conf",
            line_number=1,
            expected_text="# HKS-disabled: first = 1",
        )
        un3 = EditOp(
            kind="uncomment",
            file="hyprland.conf",
            line_number=3,
            expected_text="# HKS-disabled: third = 3",
        )
        restored = apply_ops_to_text(modified, [un1, un3])
        self.assertEqual(restored, raw)

    def test_multiple_ops_on_different_lines_apply_in_reverse_order(self) -> None:
        text = "L1\nL2\nL3\nL4\nL5\n"
        ops = [
            EditOp(kind="comment_out", file="a.lua", line_number=1, expected_text="L1"),
            EditOp(kind="delete_line", file="a.lua", line_number=2, expected_text="L2"),
            EditOp(
                kind="insert_after",
                file="a.lua",
                line_number=3,
                expected_text="L3",
                new_text="L3_inserted",
            ),
            EditOp(
                kind="replace_line",
                file="a.lua",
                line_number=5,
                expected_text="L5",
                new_text="L5_replaced",
            ),
        ]
        res = apply_ops_to_text(text, ops)
        self.assertEqual(
            res,
            "-- HKS-disabled: L1\nL3\nL3_inserted\nL4\nL5_replaced\n",
        )
        diff = generate_unified_diff(text, res, file_path="a.lua")
        self.assertIn("--- a/a.lua", diff)
        self.assertIn("+++ b/a.lua", diff)
        self.assertIn("+-- HKS-disabled: L1", diff)

    def test_generated_bind_raises_not_editable_error(self) -> None:
        gen_bind = _make_dummy_bind(
            source_file="/tmp/fake/hyprland.lua",
            source_line=310,
            generated=True,
            occurrences_at_site=10,
        )
        with self.assertRaises(NotEditableError) as ctx:
            build_op_for_bind(gen_bind, "comment_out")
        self.assertIn("/tmp/fake/hyprland.lua:310", str(ctx.exception))
        self.assertEqual(ctx.exception.line, 310)

        # Direct EditOp with generated=True also refused by apply_ops_to_text
        op = EditOp(
            kind="comment_out",
            file="/tmp/fake/hyprland.lua",
            line_number=1,
            expected_text="foo",
            generated=True,
        )
        with self.assertRaises(NotEditableError) as ctx2:
            apply_ops_to_text("foo\n", [op])
        self.assertIn("/tmp/fake/hyprland.lua:1", str(ctx2.exception))


from backend.tests.isolation import IsolatedTestCase


class TestBackups(unittest.TestCase):
    def test_create_list_restore_and_hash_mismatch_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_root:
            cfg_dir = os.path.join(tmp_root, "config")
            bkp_dir = os.path.join(tmp_root, "backups")
            os.makedirs(cfg_dir)
            env = {"HKS_BACKUP_DIR": bkp_dir}

            cfg_file = os.path.join(cfg_dir, "hyprland.lua")
            original_bytes = b'-- initial config\nhl.bind("SUPER + Return", hl.dsp.exec_cmd("kitty"))\n'
            with open(cfg_file, "wb") as f:
                f.write(original_bytes)
            os.chmod(cfg_file, 0o640)

            original_sha = hashlib.sha256(original_bytes).hexdigest()

            rec = create_backup(cfg_file, env=env)
            self.assertEqual(rec.sha256, original_sha)
            self.assertTrue(os.path.isfile(rec.backup_path))
            self.assertTrue(rec.id.startswith("hyprland.lua."))
            self.assertTrue(rec.id.endswith(original_sha[:8]))
            # Mode preserved
            self.assertEqual(
                stat.S_IMODE(os.stat(rec.backup_path).st_mode),
                0o640,
            )

            listed = list_backups(cfg_file, env=env)
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0].id, rec.id)

            # Modify file
            modified_bytes = b"-- modified config\n"
            modified_sha = hashlib.sha256(modified_bytes).hexdigest()
            atomic_write_bytes(cfg_file, modified_bytes)

            # Refuse restore when expected_current_sha256 mismatches
            with self.assertRaises(BackupConflictError):
                restore_backup(rec, expected_current_sha256=original_sha, env=env)

            # File remains modified
            with open(cfg_file, "rb") as f:
                self.assertEqual(f.read(), modified_bytes)

            # Restore succeeds when expected_current_sha256 matches current modified file
            restore_backup(rec.id, expected_current_sha256=modified_sha, env=env)
            with open(cfg_file, "rb") as f:
                self.assertEqual(f.read(), original_bytes)

            # Modify again and force restore
            atomic_write_bytes(cfg_file, b"-- concurrent edit\n")
            restore_backup(rec, expected_current_sha256="bogus_sha", force=True, env=env)
            with open(cfg_file, "rb") as f:
                self.assertEqual(f.read(), original_bytes)

            # Verify no temp files left behind in cfg_dir or bkp_dir
            cfg_entries = os.listdir(cfg_dir)
            self.assertEqual(cfg_entries, ["hyprland.lua"])
            bkp_entries = os.listdir(bkp_dir)
            for entry in bkp_entries:
                self.assertFalse(entry.startswith("."), f"Leftover temp file: {entry}")

    def test_refuses_backup_dir_inside_config_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_root:
            cfg_dir = os.path.join(tmp_root, "hypr")
            os.makedirs(cfg_dir)
            cfg_file = os.path.join(cfg_dir, "hyprland.conf")
            with open(cfg_file, "w") as f:
                f.write("bind = SUPER, Q, killactive,\n")

            bad_bkp_dir = os.path.join(cfg_dir, "backups")
            with self.assertRaises(BackupError):
                create_backup(cfg_file, backup_dir=bad_bkp_dir)


class TestValidator(unittest.TestCase):
    def test_verify_with_hyprland_ok_error_timeout_unavailable(self) -> None:
        # 1. OK with IPC/Socket noise ignored
        def fake_ok(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            stdout = (
                "DEBUG ]: [main] User-specified config location: '/tmp/hyprland.lua'\n"
                "ERR ]: [IPC::Socket2::CUnixImpl::CUnixImpl] [Socket2::UnixImpl] Couldn't bind the Hyprland Socket 2.\n"
                "\n======== Config parsing result:\n\nconfig ok\n"
            )
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        res_ok = verify_with_hyprland("/tmp/hyprland.lua", runner=fake_ok)
        self.assertIs(res_ok.ok, True)
        self.assertEqual(res_ok.exit_code, 0)
        self.assertEqual(res_ok.message, "config ok")

        # 2. Error output with line number extraction
        def fake_err(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            stdout = (
                "ERR ]: [Socket2::UnixImpl] Couldn't bind the Hyprland Socket 2.\n"
                "======== Config parsing result:\n\n"
                "=[C]:-1: hl.window.move: invalid direction \"bogus\"\n"
                "/tmp/hyprland.lua:42: hl.bind: expected a dispatcher\n"
            )
            return subprocess.CompletedProcess(cmd, 1, stdout=stdout, stderr="")

        res_err = verify_with_hyprland("/tmp/hyprland.lua", runner=fake_err)
        self.assertIs(res_err.ok, False)
        self.assertEqual(res_err.line, 42)
        self.assertIn("/tmp/hyprland.lua:42:", res_err.message)
        self.assertIn("invalid direction", res_err.message)

        # 3. Timeout
        def fake_timeout(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=20.0)

        res_to = verify_with_hyprland("/tmp/hyprland.lua", runner=fake_timeout)
        self.assertIs(res_to.ok, False)
        self.assertEqual(res_to.reason, "timeout")
        self.assertIn("timed out", res_to.message)

        # 4. Unavailable (FileNotFoundError)
        def fake_missing(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError("No such file or directory: 'Hyprland'")

        res_unavail = verify_with_hyprland("/tmp/hyprland.lua", runner=fake_missing)
        self.assertIsNone(res_unavail.ok)
        self.assertEqual(res_unavail.reason, "hyprland_unavailable")
        self.assertEqual(res_unavail.message, "hyprland_unavailable")

    def test_stage_candidate_skips_bak_files_and_verifies_with_recorder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_root:
            cfg_dir = os.path.join(tmp_root, "hypr")
            os.makedirs(cfg_dir)
            entry = os.path.join(cfg_dir, "hyprland.lua")
            helper = os.path.join(cfg_dir, "extra.lua")
            bak_file = os.path.join(cfg_dir, "hyprland.lua.bak.1")

            with open(helper, "w") as f:
                f.write('return "SUPER"\n')
            with open(bak_file, "w") as f:
                f.write("-- old backup\n")
            with open(entry, "w") as f:
                f.write(
                    'local mod = dofile("extra.lua")\n'
                    'hl.bind(mod .. " + Return", hl.dsp.exec_cmd("kitty"))\n'
                )

            new_bytes = (
                b'local mod = dofile("extra.lua")\n'
                b'hl.bind(mod .. " + Return", hl.dsp.exec_cmd("kitty"))\n'
                b'hl.bind(mod .. " + Q", hl.dsp.window.close())\n'
            )

            with stage_candidate_config(cfg_dir, entry, entry, new_bytes) as (
                staged_dir,
                staged_entry,
                _,
            ):
                self.assertTrue(os.path.isfile(os.path.join(staged_dir, "extra.lua")))
                self.assertFalse(os.path.exists(os.path.join(staged_dir, "hyprland.lua.bak.1")))
                binds = verify_with_recorder(staged_entry, staged_dir)
                self.assertEqual(len(binds), 2)

            # Broken Lua syntax raises RecorderVerificationError
            with stage_candidate_config(cfg_dir, entry, entry, b"invalid lua !!!\n") as (
                staged_dir,
                staged_entry,
                _,
            ):
                with self.assertRaises(RecorderVerificationError):
                    verify_with_recorder(staged_entry, staged_dir)


class TestApplyPipeline(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.cfg_dir = os.path.join(self.root, "hypr")
        self.bkp_dir = os.path.join(self.root, "backups")
        os.makedirs(self.cfg_dir)
        self.env = {"HKS_BACKUP_DIR": self.bkp_dir}

        self.lua_path = os.path.join(self.cfg_dir, "hyprland.lua")
        self.conf_path = os.path.join(self.cfg_dir, "hyprland.conf")

        self.initial_lua = (
            'local mainMod = "SUPER"\n'
            'hl.bind(mainMod .. " + Return", hl.dsp.exec_cmd("kitty"))\n'
            'hl.bind("ALT + Tab", hl.dsp.window.cyclenext())\n'
            'hl.bind("ALT + Tab", hl.dsp.window.bringactivetotop())\n'
            'hl.bind(mainMod .. " + X", hl.dsp.window.close())\n'
        )
        with open(self.lua_path, "w", encoding="utf-8") as f:
            f.write(self.initial_lua)

        self.initial_conf = (
            "$mainMod = SUPER\n"
            "bind = $mainMod, Return, exec, kitty\n"
            "bind = ALT, Tab, cyclenext,\n"
            "bind = ALT, Tab, bringactivetotop,\n"
            "bind = $mainMod, X, killactive,\n"
        )
        with open(self.conf_path, "w", encoding="utf-8") as f:
            f.write(self.initial_conf)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    @staticmethod
    def _hyprland_ok_runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout="======== Config parsing result:\n\nconfig ok\n",
            stderr="",
        )

    @staticmethod
    def _hyprland_fail_runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            cmd,
            1,
            stdout="======== Config parsing result:\n\n/tmp/hyprland.lua:2: syntax error\n",
            stderr="",
        )

    def test_dry_run_writes_nothing_and_checks_stacked_bind_removal(self) -> None:
        orig_sha = compute_file_sha256(self.lua_path)
        op = EditOp(
            kind="comment_out",
            file=self.lua_path,
            line_number=4,
            expected_text='hl.bind("ALT + Tab", hl.dsp.window.bringactivetotop())',
            language="lua",
        )
        res = apply_edit(
            [op],
            config_dir=self.cfg_dir,
            entrypoint=self.lua_path,
            dry_run=True,
            scan_sha256=orig_sha,
            hyprland_runner=self._hyprland_ok_runner,
            env=self.env,
        )
        self.assertFalse(res.applied)
        self.assertFalse(res.rolled_back)
        self.assertIsNone(res.backup)
        self.assertEqual(res.errors, [])
        self.assertIsNotNone(res.verify)
        assert res.verify is not None
        self.assertTrue(res.verify.ok)
        self.assertIsNotNone(res.bind_comparison)
        assert res.bind_comparison is not None
        # Stacked bind: commenting out 1 of the 2 ALT+Tab binds reduces count from 4 to 3 (-1)
        self.assertTrue(res.bind_comparison.ok)
        self.assertEqual(res.bind_comparison.before_count, 4)
        self.assertEqual(res.bind_comparison.after_count, 3)
        self.assertEqual(res.bind_comparison.removed_count, 1)
        self.assertEqual(res.bind_comparison.added_count, 0)
        # Companion .conf warning is populated, .conf is untouched
        self.assertIsNotNone(res.companion_warning)
        assert res.companion_warning is not None
        self.assertIn("hyprland.conf", res.companion_warning)

        # Verify nothing written and no backup created
        self.assertEqual(compute_file_sha256(self.lua_path), orig_sha)
        self.assertEqual(list_backups(env=self.env), [])

    def test_apply_writes_and_creates_backup(self) -> None:
        orig_sha = compute_file_sha256(self.lua_path)
        op = EditOp(
            kind="comment_out",
            file=self.lua_path,
            line_number=2,
            expected_text='hl.bind(mainMod .. " + Return", hl.dsp.exec_cmd("kitty"))',
            language="lua",
        )
        res = apply_edit(
            [op],
            config_dir=self.cfg_dir,
            entrypoint=self.lua_path,
            dry_run=False,
            scan_sha256=orig_sha,
            hyprland_runner=self._hyprland_ok_runner,
            env=self.env,
        )
        self.assertTrue(res.applied)
        self.assertFalse(res.rolled_back)
        self.assertEqual(res.errors, [])
        self.assertIsNotNone(res.backup)
        assert res.backup is not None
        self.assertEqual(res.backup.sha256, orig_sha)

        with open(self.lua_path, "r", encoding="utf-8") as f:
            updated = f.read()
        self.assertIn(
            '-- HKS-disabled: hl.bind(mainMod .. " + Return", hl.dsp.exec_cmd("kitty"))',
            updated,
        )
        # Companion .conf was NOT modified
        with open(self.conf_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), self.initial_conf)

    def test_verification_failure_writes_nothing(self) -> None:
        orig_sha = compute_file_sha256(self.lua_path)
        op = EditOp(
            kind="comment_out",
            file=self.lua_path,
            line_number=2,
            expected_text='hl.bind(mainMod .. " + Return", hl.dsp.exec_cmd("kitty"))',
            language="lua",
        )
        res = apply_edit(
            [op],
            config_dir=self.cfg_dir,
            entrypoint=self.lua_path,
            dry_run=False,
            hyprland_runner=self._hyprland_fail_runner,
            env=self.env,
        )
        self.assertFalse(res.applied)
        self.assertFalse(res.rolled_back)
        self.assertIsNone(res.backup)
        self.assertTrue(len(res.errors) > 0)
        self.assertEqual(compute_file_sha256(self.lua_path), orig_sha)
        self.assertEqual(list_backups(env=self.env), [])

    def test_reload_failure_triggers_automatic_rollback(self) -> None:
        with open(self.lua_path, "rb") as f:
            orig_bytes = f.read()
        orig_sha = hashlib.sha256(orig_bytes).hexdigest()

        def fake_reload_runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if cmd[:2] == ["hyprctl", "reload"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")
            if cmd[:2] == ["hyprctl", "configerrors"]:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    stdout="Config error at line 2: runtime reload rejected bind\n",
                    stderr="",
                )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        sleep_calls: list[float] = []
        op = EditOp(
            kind="comment_out",
            file=self.lua_path,
            line_number=2,
            expected_text='hl.bind(mainMod .. " + Return", hl.dsp.exec_cmd("kitty"))',
            language="lua",
        )
        res = apply_edit(
            [op],
            config_dir=self.cfg_dir,
            entrypoint=self.lua_path,
            dry_run=False,
            reload=True,
            hyprland_runner=self._hyprland_ok_runner,
            reload_runner=fake_reload_runner,
            sleep_fn=lambda s: sleep_calls.append(s),
            env=self.env,
        )
        self.assertFalse(res.applied)
        self.assertTrue(res.rolled_back)
        self.assertIsNotNone(res.backup)
        self.assertEqual(sleep_calls, [1.0])
        self.assertTrue(any("rolled back" in e for e in res.errors))

        # Bytes on disk restored 100% identically
        with open(self.lua_path, "rb") as f:
            self.assertEqual(f.read(), orig_bytes)
        self.assertEqual(compute_file_sha256(self.lua_path), orig_sha)

    def test_scan_sha256_mismatch_refuses(self) -> None:
        orig_sha = compute_file_sha256(self.lua_path)
        op = EditOp(
            kind="comment_out",
            file=self.lua_path,
            line_number=2,
            expected_text='hl.bind(mainMod .. " + Return", hl.dsp.exec_cmd("kitty"))',
            language="lua",
        )
        res = apply_edit(
            [op],
            config_dir=self.cfg_dir,
            entrypoint=self.lua_path,
            dry_run=False,
            scan_sha256="0" * 64,
            hyprland_runner=self._hyprland_ok_runner,
            env=self.env,
        )
        self.assertFalse(res.applied)
        self.assertFalse(res.rolled_back)
        self.assertIsNone(res.backup)
        self.assertTrue(any("Concurrent edit detected" in e for e in res.errors))
        self.assertEqual(compute_file_sha256(self.lua_path), orig_sha)


class TestEditorCLI(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = self._isolated_root
        self.cfg_dir = os.path.join(self.root, "hypr")
        self.bak_dir = self.backup_dir
        os.makedirs(self.cfg_dir, exist_ok=True)

        self.lua_path = os.path.join(self.cfg_dir, "hyprland.lua")
        self.initial_lua = (
            'local mainMod = "SUPER"\n'
            'hl.bind(mainMod .. " + Return", hl.dsp.exec_cmd("kitty"))\n'
            'for i = 1, 2 do\n'
            '    hl.bind(mainMod .. " + " .. tostring(i), hl.dsp.focus({ workspace = i }))\n'
            'end\n'
        )
        with open(self.lua_path, "w", encoding="utf-8") as f:
            f.write(self.initial_lua)

    def tearDown(self) -> None:
        super().tearDown()

    def _run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            code = cli_main(argv)
        return code, out_buf.getvalue(), err_buf.getvalue()

    def test_cli_edit_dry_run_apply_uncomment_backups_restore(self) -> None:
        doc, _ = run_scan_pipeline(config_dir=self.cfg_dir, no_live=True, no_sidecar=True)
        kitty_bind = next(b for b in doc.binds if b.key == "Return")
        loop_bind = next(b for b in doc.binds if b.generated)

        orig_sha = compute_file_sha256(self.lua_path)

        # 1. Dry-run is default: prints diff + verification, modifies nothing, creates no backup
        code, stdout, stderr = self._run_cli(
            ["edit", "--config-dir", self.cfg_dir, "--no-live", "--comment-out", kitty_bind.id]
        )
        self.assertEqual(code, 0, f"stderr={stderr}\nstdout={stdout}")
        self.assertIn("DRY-RUN", stdout)
        self.assertIn("-- HKS-disabled:", stdout)
        self.assertIn("Result: VERIFIED", stdout)
        self.assertEqual(compute_file_sha256(self.lua_path), orig_sha)
        self.assertEqual(list_backups(), [])

        # 2. Generated loop bind is refused with exit code 1
        code_loop, _, stderr_loop = self._run_cli(
            ["edit", "--config-dir", self.cfg_dir, "--no-live", "--comment-out", loop_bind.id]
        )
        self.assertEqual(code_loop, 1)
        self.assertIn("not editable", stderr_loop)
        self.assertIn(f"{self.lua_path}:4", stderr_loop)

        # 3. Apply comment-out: writes file and creates backup
        code_apply, stdout_apply, stderr_apply = self._run_cli(
            [
                "edit",
                "--config-dir",
                self.cfg_dir,
                "--no-live",
                "--apply",
                "--comment-out",
                kitty_bind.id,
            ]
        )
        self.assertEqual(code_apply, 0, f"stderr={stderr_apply}\nstdout={stdout_apply}")
        self.assertIn("Result: APPLIED", stdout_apply)
        self.assertNotEqual(compute_file_sha256(self.lua_path), orig_sha)
        self.assertEqual(len(list_backups()), 1)

        # 4. Uncomment with --apply: restores the commented-out line
        code_unc, stdout_unc, stderr_unc = self._run_cli(
            [
                "edit",
                "--config-dir",
                self.cfg_dir,
                "--no-live",
                "--apply",
                "--uncomment",
                kitty_bind.id,
            ]
        )
        self.assertEqual(code_unc, 0, f"stderr={stderr_unc}\nstdout={stdout_unc}")
        self.assertIn("Result: APPLIED", stdout_unc)
        self.assertEqual(compute_file_sha256(self.lua_path), orig_sha)
        self.assertEqual(len(list_backups()), 2)

        # 5. Backups list subcommand
        code_bak, stdout_bak, _ = self._run_cli(["backups"])
        self.assertEqual(code_bak, 0)
        baks = list_backups()
        self.assertIn(baks[0].id, stdout_bak)
        self.assertIn(baks[1].id, stdout_bak)

        # 6. Restore requires --apply (exit 2 without --apply)
        code_res_no_apply, _, stderr_res_no_apply = self._run_cli(["restore", baks[0].id])
        self.assertEqual(code_res_no_apply, 2)
        self.assertIn("--apply", stderr_res_no_apply)

        # 7. Restore with --apply restores backup
        code_res, stdout_res, stderr_res = self._run_cli(["restore", baks[1].id, "--apply"])
        self.assertEqual(code_res, 0, f"stderr={stderr_res}")
        self.assertIn("Restored", stdout_res)

    def test_cli_edit_usage_and_lookup_errors(self) -> None:
        # Missing --comment-out / --uncomment -> exit 2
        code, _, stderr = self._run_cli(["edit", "--config-dir", self.cfg_dir, "--no-live"])
        self.assertEqual(code, 2)
        self.assertIn("requires at least one", stderr)

        # --reload without --apply -> exit 2
        code, _, stderr = self._run_cli(
            ["edit", "--config-dir", self.cfg_dir, "--no-live", "--reload", "--comment-out", "b_000"]
        )
        self.assertEqual(code, 2)
        self.assertIn("--reload requires --apply", stderr)

        # Unknown bind ID -> exit 1
        code, _, stderr = self._run_cli(
            ["edit", "--config-dir", self.cfg_dir, "--no-live", "--comment-out", "b_nonexistent"]
        )
        self.assertEqual(code, 1)
        self.assertIn("not found", stderr)

    def test_round_trip_disable_scan_enable_byte_identical(self) -> None:
        doc0, _ = run_scan_pipeline(config_dir=self.cfg_dir, no_live=True, no_sidecar=True)
        kitty_bind = next(b for b in doc0.binds if b.key == "Return")
        orig_sha = compute_file_sha256(self.lua_path)

        # 1. Disable via CLI
        code1, _, _ = self._run_cli(
            ["edit", "--config-dir", self.cfg_dir, "--no-live", "--apply", "--comment-out", kitty_bind.id]
        )
        self.assertEqual(code1, 0)

        # 2. Rescan: shows in disabled_binds and validates schema
        doc1, _ = run_scan_pipeline(config_dir=self.cfg_dir, no_live=True, no_sidecar=True)
        self.assertEqual(doc1.stats.disabled_binds, 1)
        self.assertEqual(len(doc1.disabled_binds), 1)
        dis = doc1.disabled_binds[0]
        self.assertEqual(dis.id, kitty_bind.id)
        self.assertIn("Return", str(dis.key_hint))
        self.assertEqual(dis.description_hint, "Launch kitty")

        schema_errors = validate_scan_dict(doc1.to_dict())
        self.assertEqual(schema_errors, [])

        # 3. Enable (uncomment) via CLI
        code2, _, _ = self._run_cli(
            ["edit", "--config-dir", self.cfg_dir, "--no-live", "--apply", "--uncomment", kitty_bind.id]
        )
        self.assertEqual(code2, 0)

        # 4. Byte-identical restoration
        self.assertEqual(compute_file_sha256(self.lua_path), orig_sha)
        doc2, _ = run_scan_pipeline(config_dir=self.cfg_dir, no_live=True, no_sidecar=True)
        self.assertEqual(doc2.stats.disabled_binds, 0)
        self.assertEqual(len(doc2.disabled_binds), 0)

    def test_delete_round_trip_via_restore_latest(self) -> None:
        doc0, _ = run_scan_pipeline(config_dir=self.cfg_dir, no_live=True, no_sidecar=True)
        kitty_bind = next(b for b in doc0.binds if b.key == "Return")
        orig_sha = compute_file_sha256(self.lua_path)

        # 1. Delete bind
        code_del, stdout_del, _ = self._run_cli(
            ["edit", "--config-dir", self.cfg_dir, "--no-live", "--apply", "--delete", kitty_bind.id]
        )
        self.assertEqual(code_del, 0)
        self.assertIn("Result: APPLIED", stdout_del)

        # Confirm line deleted and removed from parsed binds
        doc_after_del, _ = run_scan_pipeline(config_dir=self.cfg_dir, no_live=True, no_sidecar=True)
        self.assertFalse(any(b.id == kitty_bind.id for b in doc_after_del.binds))

        # 2. Restore using --latest convenience
        code_res, stdout_res, _ = self._run_cli(["restore", "--latest", "--apply"])
        self.assertEqual(code_res, 0)
        self.assertIn("Restored", stdout_res)

        # Confirm file is byte-identical
        self.assertEqual(compute_file_sha256(self.lua_path), orig_sha)

    def test_cli_json_output_mode(self) -> None:
        import json

        doc, _ = run_scan_pipeline(config_dir=self.cfg_dir, no_live=True, no_sidecar=True)
        kitty_bind = next(b for b in doc.binds if b.key == "Return")
        loop_bind = next(b for b in doc.binds if b.generated)

        # 1. Edit dry-run with --json
        code_dry, stdout_dry, _ = self._run_cli(
            ["edit", "--config-dir", self.cfg_dir, "--no-live", "--json", "--comment-out", kitty_bind.id]
        )
        self.assertEqual(code_dry, 0)
        data_dry = json.loads(stdout_dry)
        self.assertEqual(data_dry["mode"], "dry-run")
        self.assertFalse(data_dry["applied"])
        self.assertFalse(data_dry["rolled_back"])
        self.assertTrue(len(data_dry["diff"]) > 0)
        self.assertEqual(data_dry["errors"], [])
        self.assertIsNone(data_dry["backup"])

        # 2. Loop bind refusal with --json
        code_loop, stdout_loop, _ = self._run_cli(
            ["edit", "--config-dir", self.cfg_dir, "--no-live", "--json", "--comment-out", loop_bind.id]
        )
        self.assertEqual(code_loop, 1)
        data_loop = json.loads(stdout_loop)
        self.assertEqual(data_loop["mode"], "dry-run")
        self.assertFalse(data_loop["applied"])
        self.assertTrue(any("not editable" in e for e in data_loop["errors"]))

        # 3. Apply with --json
        code_app, stdout_app, _ = self._run_cli(
            [
                "edit",
                "--config-dir",
                self.cfg_dir,
                "--no-live",
                "--json",
                "--apply",
                "--comment-out",
                kitty_bind.id,
            ]
        )
        self.assertEqual(code_app, 0)
        data_app = json.loads(stdout_app)
        self.assertEqual(data_app["mode"], "apply")
        self.assertTrue(data_app["applied"])
        self.assertIsNotNone(data_app["backup"])
        self.assertTrue(len(data_app["backup"]["id"]) > 0)

        # 4. Backups listing with --json
        code_bak, stdout_bak, _ = self._run_cli(["backups", "--json"])
        self.assertEqual(code_bak, 0)
        data_bak = json.loads(stdout_bak)
        self.assertEqual(data_bak["mode"], "backups")
        self.assertTrue(len(data_bak["backups"]) >= 1)

        # 5. Restore --latest preview (dry-run) with --json
        code_res_dry, stdout_res_dry, _ = self._run_cli(["restore", "--latest", "--dry-run", "--json"])
        self.assertEqual(code_res_dry, 0)
        data_res_dry = json.loads(stdout_res_dry)
        self.assertEqual(data_res_dry["mode"], "restore (dry-run)")
        self.assertFalse(data_res_dry["applied"])
        self.assertTrue(len(data_res_dry["diff"]) > 0)

        # 6. Restore --latest apply with --json
        code_res_app, stdout_res_app, _ = self._run_cli(["restore", "--latest", "--apply", "--json"])
        self.assertEqual(code_res_app, 0)
        data_res_app = json.loads(stdout_res_app)
        self.assertEqual(data_res_app["mode"], "restore")
        self.assertTrue(data_res_app["applied"])


if __name__ == "__main__":
    unittest.main()
