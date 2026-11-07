"""Unit tests for the HKS Phase 4a safe edit engine (temp dirs and fixtures only)."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import unittest

from backend.editor import (
    BackupConflictError,
    BackupError,
    EditConflict,
    EditOp,
    NotEditableError,
    apply_ops_to_text,
    atomic_write_bytes,
    build_op_for_bind,
    create_backup,
    generate_unified_diff,
    list_backups,
    restore_backup,
)
from backend.models.types import BindRecord, DispatcherInfo, default_flags


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


if __name__ == "__main__":
    unittest.main()
