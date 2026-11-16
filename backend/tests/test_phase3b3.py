"""Unit tests for Phase 3b-3 (Keybind Add Workflow Backend)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from backend.cli import main
from backend.editor.apply import resolve_insert_op
from backend.editor.codegen import (
    escape_lua_string,
    generate_hyprlang_bind,
    generate_lua_bind,
    validate_code_tokens,
)
from backend.editor.edit_plan import NotEditableError
from backend.editor.insert_policy import plan_insert_bind


class TestPhase3b3Part1StringSafety(unittest.TestCase):
    def test_escape_lua_string(self) -> None:
        self.assertEqual(escape_lua_string("kitty"), '"kitty"')
        self.assertEqual(escape_lua_string('echo "hi"'), '"echo \\"hi\\""')
        self.assertEqual(escape_lua_string("path\\to\\dir"), '"path\\\\to\\\\dir"')
        self.assertEqual(
            escape_lua_string('firefox --new-window "a b"'),
            '"firefox --new-window \\"a b\\""',
        )
        self.assertEqual(escape_lua_string("sh -c 'echo \"hi\"'"), '"sh -c \'echo \\"hi\\"\'"')
        self.assertEqual(escape_lua_string('test ]] and -- comment'), '"test ]] and -- comment"')
        self.assertEqual(escape_lua_string('notify-send "こんにちは"'), '"notify-send \\"こんにちは\\""')

    def test_escape_lua_string_rejects_newlines(self) -> None:
        with self.assertRaises(ValueError):
            escape_lua_string("line1\nline2")
        with self.assertRaises(ValueError):
            escape_lua_string("line1\rline2")

    def test_generate_lua_bind_with_tricky_strings(self) -> None:
        # Quotes and shell arguments
        res = generate_lua_bind(["SUPER"], "Return", "exec_cmd", 'firefox --new-window "a b"')
        self.assertEqual(
            res,
            'hl.bind("SUPER + Return", hl.dsp.exec_cmd("firefox --new-window \\"a b\\""))',
        )

        res2 = generate_lua_bind(["SUPER"], "T", "exec_cmd", "sh -c 'echo \"hi\"'")
        self.assertEqual(
            res2,
            'hl.bind("SUPER + T", hl.dsp.exec_cmd("sh -c \'echo \\"hi\\"\'"))',
        )

        res3 = generate_lua_bind(["SUPER"], "P", "exec_cmd", 'path with spaces/run.sh "arg"')
        self.assertEqual(
            res3,
            'hl.bind("SUPER + P", hl.dsp.exec_cmd("path with spaces/run.sh \\"arg\\""))',
        )

        res4 = generate_lua_bind(["SUPER"], "U", "exec_cmd", 'notify-send "こんにちは"')
        self.assertEqual(
            res4,
            'hl.bind("SUPER + U", hl.dsp.exec_cmd("notify-send \\"こんにちは\\""))',
        )

        # Newlines rejected
        with self.assertRaises(ValueError):
            generate_lua_bind(["SUPER"], "Return", "exec_cmd", "echo hi\nrm -rf /")

    def test_generate_hyprlang_bind_with_commas_and_quotes(self) -> None:
        # Hyprlang exec permits commas and quotes in args
        res = generate_hyprlang_bind(["SUPER"], "Return", "exec", 'firefox --new-window "a b"')
        self.assertEqual(res, 'bind = SUPER, Return, exec, firefox --new-window "a b"')

        res2 = generate_hyprlang_bind(["SUPER"], "C", "exec", "notify-send a, b, c")
        self.assertEqual(res2, "bind = SUPER, C, exec, notify-send a, b, c")

        # Newlines rejected
        with self.assertRaises(ValueError):
            generate_hyprlang_bind(["SUPER"], "Return", "exec", "echo hi\nexit")


class TestPhase3b3Part1BindFlags(unittest.TestCase):
    def test_lua_bind_flags(self) -> None:
        res_locked = generate_lua_bind(
            ["SUPER"], "L", "exec_cmd", "hyprlock", flags={"locked": True}
        )
        self.assertEqual(
            res_locked,
            'hl.bind("SUPER + L", hl.dsp.exec_cmd("hyprlock"), { locked = true })',
        )

        res_multi = generate_lua_bind(
            None,
            "XF86AudioRaiseVolume",
            "exec_cmd",
            "volume_up",
            flags={"locked": True, "repeating": True},
        )
        self.assertEqual(
            res_multi,
            'hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("volume_up"), { locked = true, repeating = true })',
        )

        res_mouse = generate_lua_bind(
            ["SUPER"], "mouse:272", "window.drag", None, flags={"mouse": True}
        )
        self.assertEqual(
            res_mouse,
            'hl.bind("SUPER + mouse:272", hl.dsp.window.drag(), { mouse = true })',
        )

    def test_hyprlang_bind_flags(self) -> None:
        res_l = generate_hyprlang_bind(["SUPER"], "L", "exec", "hyprlock", flags={"locked": True})
        self.assertEqual(res_l, "bindl = SUPER, L, exec, hyprlock")

        res_e = generate_hyprlang_bind(
            None, "XF86AudioRaiseVolume", "exec", "vol_up", flags={"repeating": True}
        )
        self.assertEqual(res_e, "binde = , XF86AudioRaiseVolume, exec, vol_up")

        res_el = generate_hyprlang_bind(
            None,
            "XF86AudioRaiseVolume",
            "exec",
            "vol_up",
            flags={"locked": True, "repeating": True},
        )
        self.assertEqual(res_el, "bindel = , XF86AudioRaiseVolume, exec, vol_up")

        res_m = generate_hyprlang_bind(
            ["SUPER"], "mouse:272", "movewindow", None, flags={"mouse": True}
        )
        self.assertEqual(res_m, "bindm = SUPER, mouse:272, movewindow")


class TestPhase3b3Part1InsertionEdgeCases(unittest.TestCase):
    def test_file_with_no_trailing_newline_preserved(self) -> None:
        content = 'hl.bind("SUPER + Q", hl.dsp.window.close())'
        with tempfile.NamedTemporaryFile("w+", suffix=".lua", delete=False) as f:
            f.write(content)
            path = f.name

        try:
            op, plan = plan_insert_bind(
                path, "lua", ["SUPER"], "Return", "exec_cmd", "kitty"
            )
            self.assertTrue(plan.anchor_created)
            self.assertIn("-- HKS: custom binds", op.new_text)
            self.assertIn('hl.bind("SUPER + Return", hl.dsp.exec_cmd("kitty"))', op.new_text)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_crlf_line_endings_preserved(self) -> None:
        content = "local hl = require('hyprland')\r\nhl.bind(\"SUPER + Q\", hl.dsp.window.close())\r\n"
        with tempfile.NamedTemporaryFile("wb+", suffix=".lua", delete=False) as f:
            f.write(content.encode("utf-8"))
            path = f.name

        try:
            op, plan = plan_insert_bind(
                path, "lua", ["SUPER"], "Return", "exec_cmd", "kitty"
            )
            self.assertTrue(plan.anchor_created)
            self.assertIn("\r\n-- HKS: custom binds\r\n", op.new_text)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_anchor_exists_with_multiple_binds_appends_after_last(self) -> None:
        content = (
            "local hl = require('hyprland')\n"
            'hl.bind("SUPER + Q", hl.dsp.window.close())\n\n'
            "-- HKS: custom binds\n"
            'hl.bind("SUPER + 1", hl.dsp.workspace("1"))\n'
            'hl.bind("SUPER + 2", hl.dsp.workspace("2"))\n'
            "-- HKS-disabled: hl.bind(\"SUPER + 3\", hl.dsp.workspace(\"3\"))\n\n"
            "-- Other section\n"
            "hl.config({})\n"
        )
        with tempfile.NamedTemporaryFile("w+", suffix=".lua", delete=False) as f:
            f.write(content)
            path = f.name

        try:
            op, plan = plan_insert_bind(
                path, "lua", ["SUPER"], "Return", "exec_cmd", "kitty"
            )
            self.assertFalse(plan.anchor_created)
            # Must target the last line of the HKS block (line 7: -- HKS-disabled: ...)
            self.assertEqual(plan.line_number, 7)
            self.assertEqual(
                op.new_text,
                'hl.bind("SUPER + Return", hl.dsp.exec_cmd("kitty"))',
            )
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_no_top_level_binds_falls_back_to_depth_0_eof(self) -> None:
        content = (
            "local hl = require('hyprland')\n"
            "hl.config({\n"
            "    general = { border_size = 2 }\n"
            "})\n"
        )
        with tempfile.NamedTemporaryFile("w+", suffix=".lua", delete=False) as f:
            f.write(content)
            path = f.name

        try:
            op, plan = plan_insert_bind(
                path, "lua", ["SUPER"], "Return", "exec_cmd", "kitty"
            )
            self.assertTrue(plan.anchor_created)
            # Inserts at EOF (line 4)
            self.assertEqual(plan.line_number, 4)
            self.assertIn("-- HKS: custom binds", op.new_text)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_hyprlang_sourced_files_anchor_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            main_conf = os.path.join(td, "hyprland.conf")
            extra_conf = os.path.join(td, "extra.conf")

            # main_conf has no anchor
            with open(main_conf, "w", encoding="utf-8") as f:
                f.write("source = ./extra.conf\nbind = SUPER, Q, killactive\n")

            # extra_conf has the anchor
            with open(extra_conf, "w", encoding="utf-8") as f:
                f.write("# HKS: custom binds\nbind = SUPER, 1, workspace, 1\n")

            op, plan, exp = resolve_insert_op(
                file_path=main_conf,
                language="hyprlang",
                mods=["SUPER"],
                key="Return",
                dispatcher="exec",
                args="kitty",
                all_files=[main_conf, extra_conf],
            )

            # Targets extra_conf because anchor is there!
            self.assertEqual(plan.file, extra_conf)
            self.assertFalse(plan.anchor_created)
            self.assertEqual(plan.line_number, 2)


class TestPhase3b3Part1Submaps(unittest.TestCase):
    def test_lua_submap_refusal_when_absent(self) -> None:
        content = 'hl.bind("SUPER + Q", hl.dsp.window.close())\n'
        with tempfile.NamedTemporaryFile("w+", suffix=".lua", delete=False) as f:
            f.write(content)
            path = f.name

        try:
            with self.assertRaises(NotEditableError) as ctx:
                plan_insert_bind(
                    path,
                    "lua",
                    ["SUPER"],
                    "R",
                    "exec_cmd",
                    "resize",
                    submap="nonexistent_submap",
                )
            self.assertIn("does not exist", str(ctx.exception))
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_hyprlang_submap_refusal_when_absent(self) -> None:
        content = "bind = SUPER, Q, killactive\n"
        with tempfile.NamedTemporaryFile("w+", suffix=".conf", delete=False) as f:
            f.write(content)
            path = f.name

        try:
            with self.assertRaises(NotEditableError) as ctx:
                plan_insert_bind(
                    path,
                    "hyprlang",
                    ["SUPER"],
                    "R",
                    "exec",
                    "resize",
                    submap="nonexistent_submap",
                )
            self.assertIn("does not exist", str(ctx.exception))
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_hyprlang_submap_insertion_success(self) -> None:
        content = (
            "bind = SUPER, Q, killactive\n\n"
            "submap = resize\n"
            "binde = , right, resizeactive, 10 0\n"
            "bind = , escape, submap, reset\n"
            "submap = reset\n"
        )
        with tempfile.NamedTemporaryFile("w+", suffix=".conf", delete=False) as f:
            f.write(content)
            path = f.name

        try:
            op, plan = plan_insert_bind(
                path,
                "hyprlang",
                None,
                "left",
                "resizeactive",
                "-10 0",
                submap="resize",
            )
            self.assertFalse(plan.anchor_created)
            # Inserts after line 4 (the last bind inside submap before reset)
            self.assertEqual(plan.line_number, 5)
            self.assertEqual(op.new_text, "bind = , left, resizeactive, -10 0")
        finally:
            if os.path.exists(path):
                os.unlink(path)


from backend.tests.isolation import IsolatedTestCase


class TestPhase3b3Part2CLIAndDryRun(IsolatedTestCase):
    def test_cli_add_preview_json_structure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            conf_path = os.path.join(td, "hyprland.lua")
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write('hl.bind("SUPER + Q", hl.dsp.window.close())\n')

            os.environ["HKS_BACKUP_DIR"] = self.backup_dir
            os.environ["HKS_SIDECAR_PATH"] = self.sidecar_path

            try:
                import io
                from contextlib import redirect_stdout

                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = main([
                        "edit", "add",
                        "--mods", "SUPER",
                        "--key", "Return",
                        "--dispatcher", "exec_cmd",
                        "--args", "kitty",
                        "--entrypoint", conf_path,
                        "--dry-run",
                        "--json",
                        "--no-live",
                    ])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertFalse(out["applied"])
                self.assertTrue(out["anchor_created"])
                self.assertIn("file_to_modify", out)
                self.assertEqual(out["file_to_modify"], os.path.abspath(conf_path))
                self.assertEqual(out["insert_line"], 1)
                self.assertIn("expected_new_bind", out)
                self.assertEqual(out["expected_new_bind"]["key"], "Return")
                self.assertEqual(out["has_conflicts"], False)
                self.assertEqual(out["conflicts"], [])
            finally:
                os.environ["HKS_BACKUP_DIR"] = self.backup_dir
                os.environ["HKS_SIDECAR_PATH"] = self.sidecar_path

    def test_cli_add_conflict_duplicate_guard(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            conf_path = os.path.join(td, "hyprland.lua")
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write('hl.bind("SUPER + Q", hl.dsp.window.close())\n')

            os.environ["HKS_BACKUP_DIR"] = self.backup_dir
            os.environ["HKS_SIDECAR_PATH"] = self.sidecar_path

            try:
                import io
                from contextlib import redirect_stdout

                buf = io.StringIO()
                with redirect_stdout(buf):
                    # Try to add SUPER + Q which already exists
                    rc = main([
                        "edit", "add",
                        "--mods", "SUPER",
                        "--key", "Q",
                        "--dispatcher", "exec_cmd",
                        "--args", "kitty",
                        "--entrypoint", conf_path,
                        "--dry-run",
                        "--json",
                        "--no-live",
                    ])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                # Conflict detected in preview!
                self.assertTrue(out["has_conflicts"])
                self.assertEqual(len(out["conflicts"]), 1)
                self.assertEqual(out["conflicts"][0]["shortcut"], "SUPER + Q")

                # In apply mode without --force, it should fail
                buf2 = io.StringIO()
                with redirect_stdout(buf2):
                    rc2 = main([
                        "edit", "add",
                        "--mods", "SUPER",
                        "--key", "Q",
                        "--dispatcher", "exec_cmd",
                        "--args", "kitty",
                        "--entrypoint", conf_path,
                        "--apply",
                        "--json",
                        "--no-live",
                    ])
                self.assertNotEqual(rc2, 0)
                out2 = json.loads(buf2.getvalue())
                self.assertFalse(out2["applied"])
                self.assertIn("conflict", out2["errors"][0].lower())
            finally:
                os.environ["HKS_BACKUP_DIR"] = self.backup_dir
                os.environ["HKS_SIDECAR_PATH"] = self.sidecar_path

    def test_cli_add_apply_3layer_and_second_add(self) -> None:
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as bak_td:
            conf_path = os.path.join(td, "hyprland.lua")
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write('hl.bind("SUPER + Q", hl.dsp.window.close())\n')

            os.environ["HKS_BACKUP_DIR"] = self.backup_dir
            os.environ["HKS_SIDECAR_PATH"] = self.sidecar_path

            try:
                import io
                from contextlib import redirect_stdout

                # 1. First add (creates anchor)
                buf1 = io.StringIO()
                with redirect_stdout(buf1):
                    rc1 = main([
                        "edit", "add",
                        "--mods", "SUPER",
                        "--key", "Return",
                        "--dispatcher", "exec_cmd",
                        "--args", "kitty",
                        "--entrypoint", conf_path,
                        "--apply",
                        "--json",
                        "--no-live",
                    ])
                self.assertEqual(rc1, 0)
                out1 = json.loads(buf1.getvalue())
                self.assertTrue(out1["applied"])
                self.assertTrue(out1["anchor_created"])

                with open(conf_path, "r", encoding="utf-8") as f:
                    c1 = f.read()
                self.assertIn("-- HKS: custom binds", c1)
                self.assertIn('hl.bind("SUPER + Return", hl.dsp.exec_cmd("kitty"))', c1)

                # 2. Second add (appends under existing anchor)
                buf2 = io.StringIO()
                with redirect_stdout(buf2):
                    rc2 = main([
                        "edit", "add",
                        "--mods", "SUPER",
                        "--key", "B",
                        "--dispatcher", "exec_cmd",
                        "--args", "firefox",
                        "--entrypoint", conf_path,
                        "--apply",
                        "--json",
                        "--no-live",
                    ])
                self.assertEqual(rc2, 0)
                out2 = json.loads(buf2.getvalue())
                self.assertTrue(out2["applied"])
                self.assertFalse(out2["anchor_created"])

                with open(conf_path, "r", encoding="utf-8") as f:
                    c2 = f.read()
                # Must contain both binds under the single anchor
                self.assertEqual(c2.count("-- HKS: custom binds"), 1)
                self.assertIn('hl.bind("SUPER + Return", hl.dsp.exec_cmd("kitty"))', c2)
                self.assertIn('hl.bind("SUPER + B", hl.dsp.exec_cmd("firefox"))', c2)
            finally:
                os.environ["HKS_BACKUP_DIR"] = self.backup_dir
                os.environ["HKS_SIDECAR_PATH"] = self.sidecar_path


if __name__ == "__main__":
    unittest.main()
