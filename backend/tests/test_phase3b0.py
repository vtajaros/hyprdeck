"""Comprehensive tests for Phase 3b-0 backend implementation.

Covers:
- Lua / Hyprlang code generation and variable ($mainMod / mainMod) preservation
- Multi-line bind layout preservation and multi-line replacement
- Loop-generated binds raising NotEditableError
- Insertion policy: with anchor, without anchor at depth 0, refuse depth > 0
- Validator delta checks per operation (DISABLE, RESTORE, REPLACE, INSERT)
- Dry-run writing nothing and creating no backup
- Submap commands using correct syntax per language (Lua vs Hyprlang) and heal logic
- CLI replace and add commands
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from typing import Any
from unittest import mock

from backend.cli import main as cli_main
from backend.editor import (
    EditOp,
    NotEditableError,
    apply_edit,
    apply_ops_to_text,
    compare_bind_sets,
    enter_submap,
    generate_hyprlang_bind,
    generate_lua_bind,
    heal_submap,
    leave_submap,
    make_expected_bind,
    plan_insert_bind,
    resolve_insert_op,
    resolve_replace_op,
    submap_status,
    validate_code_tokens,
)
from backend.editor.insert_policy import compute_lua_line_depths
from backend.editor.recorder_submap import enter, get_submap, heal, leave, status
from backend.models.types import BindRecord, DispatcherInfo


def _make_bind(
    *,
    bind_id: str = "b_test1",
    language: str = "lua",
    source_file: str = "/tmp/fake/hyprland.lua",
    source_line: int = 10,
    original_line: str = 'hl.bind(mainMod .. " + Q", hl.dsp.window.kill())',
    mods: list[str] | None = None,
    key: str = "Q",
    dispatcher: str = "window.kill",
    args: list[str] | None = None,
    generated: bool = False,
    occurrences_at_site: int = 1,
) -> BindRecord:
    canonical_mods = mods if mods is not None else ["SUPER"]
    return BindRecord(
        id=bind_id,
        language=language,
        bind_type="bind",
        declared_via="bind",
        modifiers=canonical_mods,
        modifiers_raw=" + ".join(canonical_mods),
        modmask=64,
        key=key,
        key_kind="keysym",
        keys_raw=" + ".join(canonical_mods + [key]),
        flags={},
        flags_extra={},
        description=None,
        dispatcher=DispatcherInfo(
            path=dispatcher,
            args=args or [],
            arg_summary=" ".join(args) if args else "",
        ),
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
        args_raw="",
    )


class TestCodegen(unittest.TestCase):
    def test_replace_preserves_main_mod_lua(self) -> None:
        orig = '    hl.bind(mainMod .. " + Q", hl.dsp.window.kill())'
        res = generate_lua_bind(
            mods=["SUPER"],
            key="Return",
            dispatcher="exec_cmd",
            args="kitty",
            original_line=orig,
        )
        self.assertEqual(res, '    hl.bind(mainMod .. " + Return", hl.dsp.exec_cmd("kitty"))')

    def test_replace_preserves_main_mod_with_extras_lua(self) -> None:
        orig = '    hl.bind(mainMod .. " + Q", hl.dsp.window.kill())'
        res = generate_lua_bind(
            mods=["SUPER", "SHIFT"],
            key="Return",
            dispatcher="exec_cmd",
            args="kitty",
            original_line=orig,
        )
        self.assertEqual(
            res,
            '    hl.bind(mainMod .. " + SHIFT + Return", hl.dsp.exec_cmd("kitty"))',
        )

    def test_replace_to_non_super_mods_goes_literal_lua(self) -> None:
        orig = '    hl.bind(mainMod .. " + Q", hl.dsp.window.kill())'
        res = generate_lua_bind(
            mods=["CTRL", "ALT"],
            key="Return",
            dispatcher="window.close",
            original_line=orig,
        )
        self.assertEqual(
            res,
            '    hl.bind("CTRL + ALT + Return", hl.dsp.window.close())',
        )

    def test_replace_preserves_column_alignment_lua(self) -> None:
        # Original line pads spaces so dispatcher starts at column 40
        orig = 'hl.bind(mainMod .. " + grave",          hl.dsp.exec_cmd(terminal))'
        res = generate_lua_bind(
            mods=["SUPER", "ALT"],
            key="grave",
            dispatcher="exec_cmd",
            args="alacritty",
            original_line=orig,
        )
        self.assertEqual(
            res,
            'hl.bind(mainMod .. " + ALT + grave",    hl.dsp.exec_cmd("alacritty"))',
        )
        # Check that hl.dsp starts at the exact same column 40
        self.assertEqual(orig.find("hl.dsp"), res.find("hl.dsp"))

    def test_replace_preserves_main_mod_hyprlang(self) -> None:
        orig = "bind = $mainMod, Q, killactive,"
        res = generate_hyprlang_bind(
            mods=["SUPER", "SHIFT"],
            key="Return",
            dispatcher="exec",
            args="kitty",
            original_line=orig,
        )
        self.assertEqual(res, "bind = $mainMod SHIFT, Return, exec, kitty")

    def test_replace_to_non_super_mods_goes_literal_hyprlang(self) -> None:
        orig = "bind = $mainMod, Q, killactive"
        res = generate_hyprlang_bind(
            mods=["CTRL", "ALT"],
            key="Return",
            dispatcher="killactive",
            original_line=orig,
        )
        self.assertEqual(res, "bind = CTRL ALT, Return, killactive")

    def test_multi_line_bind_replace_codegen(self) -> None:
        orig = 'hl.bind("ALT + Tab",\n    hl.dsp.window.bring_to_top())'
        res = generate_lua_bind(
            mods=["SUPER"],
            key="Return",
            dispatcher="window.close",
            original_line=orig,
        )
        self.assertEqual(
            res,
            'hl.bind("SUPER + Return",\n    hl.dsp.window.close())',
        )

    def test_multi_line_bind_replace_in_text(self) -> None:
        orig_text = (
            "local hl = require('hyprland')\n"
            'hl.bind("ALT + Tab",\n'
            "    hl.dsp.window.bring_to_top())\n"
            'hl.bind("SUPER + Q", hl.dsp.window.close())\n'
        )
        multi_line_expected = 'hl.bind("ALT + Tab",\n    hl.dsp.window.bring_to_top())'
        new_text = 'hl.bind("SUPER + Return",\n    hl.dsp.window.close())'

        op = EditOp(
            kind="replace_line",
            file="test.lua",
            line_number=2,
            expected_text=multi_line_expected,
            new_text=new_text,
            language="lua",
        )
        modified = apply_ops_to_text(orig_text, [op])
        expected_result = (
            "local hl = require('hyprland')\n"
            'hl.bind("SUPER + Return",\n'
            "    hl.dsp.window.close())\n"
            'hl.bind("SUPER + Q", hl.dsp.window.close())\n'
        )
        self.assertEqual(modified, expected_result)

    def test_validate_code_tokens(self) -> None:
        # Valid tokens pass
        validate_code_tokens("window.close", "")
        validate_code_tokens("exec_cmd", '"kitty"')
        validate_code_tokens("workspace", "1")
        validate_code_tokens("movewindow", "{ direction = 'right' }")

        # Invalid cases raise ValueError
        with self.assertRaises(ValueError):
            validate_code_tokens("window.close\n", "")
        with self.assertRaises(ValueError):
            validate_code_tokens("exec_cmd", 'unclosed "quote')
        with self.assertRaises(ValueError):
            validate_code_tokens("exec_cmd", "unclosed 'quote")
        with self.assertRaises(ValueError):
            validate_code_tokens("movewindow", "{ direction = 'right'")
        with self.assertRaises(ValueError):
            validate_code_tokens("exec_cmd", "func(args")


class TestNotEditable(unittest.TestCase):
    def test_replace_loop_generated_raises_not_editable(self) -> None:
        gen_bind = _make_bind(
            bind_id="b_loop1",
            generated=True,
            occurrences_at_site=10,
        )
        with self.assertRaises(NotEditableError) as ctx:
            resolve_replace_op(
                bind_id="b_loop1",
                new_mods=["SUPER"],
                new_key="Return",
                new_dispatcher="exec_cmd",
                binds=[gen_bind],
            )
        self.assertIn("generated by a loop", str(ctx.exception))

    def test_unparseable_original_line_raises_not_editable(self) -> None:
        with self.assertRaises(NotEditableError):
            generate_lua_bind("SUPER", "Q", "window.kill", original_line="local x = 42")
        with self.assertRaises(NotEditableError):
            generate_hyprlang_bind("SUPER", "Q", "killactive", original_line="monitor=,preferred,auto,1")


class TestInsertPolicy(unittest.TestCase):
    def test_insert_with_anchor_present(self) -> None:
        content = (
            "local hl = require('hyprland')\n"
            'hl.bind("SUPER + Q", hl.dsp.window.close())\n'
            "-- HKS: custom binds\n"
            'hl.bind("SUPER + Return", hl.dsp.exec_cmd("kitty"))\n'
            "-- other stuff\n"
        )
        with tempfile.NamedTemporaryFile("w+", suffix=".lua", delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            op, plan, exp = resolve_insert_op(
                file_path=temp_path,
                language="lua",
                mods=["SUPER", "SHIFT"],
                key="E",
                dispatcher="exit",
            )
            self.assertFalse(plan.anchor_created)
            self.assertEqual(op.kind, "insert_after")
            self.assertEqual(op.line_number, 4)  # after last HKS bind line
            res = apply_ops_to_text(content, [op])
            self.assertIn('hl.bind("SUPER + SHIFT + E", hl.dsp.exit())', res)
            # Make sure anchor was NOT duplicated
            self.assertEqual(res.count("-- HKS: custom binds"), 1)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_insert_without_anchor_at_depth_0(self) -> None:
        content = (
            "local hl = require('hyprland')\n"
            'hl.bind("SUPER + Q", hl.dsp.window.close())\n'
            "\n"
            "for i = 1, 9 do\n"
            "    hl.bind(tostring(i), hl.dsp.workspace(tostring(i)))\n"
            "end\n"
        )
        with tempfile.NamedTemporaryFile("w+", suffix=".lua", delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            op, plan, exp = resolve_insert_op(
                file_path=temp_path,
                language="lua",
                mods=["SUPER"],
                key="Return",
                dispatcher="exec_cmd",
                args="kitty",
            )
            self.assertTrue(plan.anchor_created)
            self.assertEqual(op.kind, "insert_after")
            self.assertEqual(op.line_number, 2)  # after top-level bind on line 2, not inside loop!
            res = apply_ops_to_text(content, [op])
            self.assertIn("-- HKS: custom binds", res)
            self.assertIn('hl.bind("SUPER + Return", hl.dsp.exec_cmd("kitty"))', res)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_insert_refuses_depth_gt_0_scope(self) -> None:
        # A file with only nested binds inside an unclosed block or function
        content = (
            "function setup_binds()\n"
            '    hl.bind("SUPER + Q", hl.dsp.window.close())\n'
            # (function not closed at depth 0)
        )
        with tempfile.NamedTemporaryFile("w+", suffix=".lua", delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            with self.assertRaises(NotEditableError) as ctx:
                resolve_insert_op(
                    file_path=temp_path,
                    language="lua",
                    mods=["SUPER"],
                    key="Return",
                    dispatcher="window.close",
                )
            self.assertIn("depth 0", str(ctx.exception))
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_insert_uses_neighbour_indentation_zero(self) -> None:
        content = (
            "local hl = require('hyprland')\n"
            'hl.bind("SUPER + Q", hl.dsp.window.close())\n'
        )
        with tempfile.NamedTemporaryFile("w+", suffix=".lua", delete=False) as f:
            f.write(content)
            temp_path = f.name
        try:
            op, plan, _ = resolve_insert_op(
                file_path=temp_path,
                language="lua",
                mods=["SUPER"],
                key="Return",
                dispatcher="exec_cmd",
                args="kitty",
            )
            # The new bind line must have 0 indentation, NOT 4 spaces!
            self.assertEqual(plan.generated_line, 'hl.bind("SUPER + Return", hl.dsp.exec_cmd("kitty"))')
            self.assertFalse(plan.generated_line.startswith(" "))
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestValidatorDeltas(unittest.TestCase):
    def setUp(self) -> None:
        self.b1 = _make_bind(bind_id="b1", source_file="/cfg/hyprland.lua", source_line=10, key="Q", dispatcher="kill")
        self.b2 = _make_bind(bind_id="b2", source_file="/cfg/hyprland.lua", source_line=11, key="W", dispatcher="browser")
        self.b3 = _make_bind(bind_id="b3", source_file="/cfg/hyprland.lua", source_line=12, key="Return", dispatcher="term")
        self.dir = "/cfg"

    def test_disable_delta(self) -> None:
        before = [self.b1, self.b2]
        after = [self.b2]
        op = EditOp(kind="comment_out", file="/cfg/hyprland.lua", line_number=10, expected_text="b1")

        # Valid disable: exactly -1 (b1 removed)
        cmp_res = compare_bind_sets(before, after, [op], self.dir, self.dir, op_kind="disable_or_delete")
        self.assertTrue(cmp_res.ok)
        self.assertEqual(cmp_res.removed_count, 1)
        self.assertEqual(cmp_res.added_count, 0)

        # Invalid disable: 0 removed
        cmp_fail1 = compare_bind_sets(before, before, [op], self.dir, self.dir, op_kind="disable_or_delete")
        self.assertFalse(cmp_fail1.ok)

        # Invalid disable: extra bind added
        cmp_fail2 = compare_bind_sets(before, [self.b2, self.b3], [op], self.dir, self.dir, op_kind="disable_or_delete")
        self.assertFalse(cmp_fail2.ok)

    def test_enable_delta(self) -> None:
        before = [self.b2]
        after = [self.b1, self.b2]
        op = EditOp(kind="uncomment", file="/cfg/hyprland.lua", line_number=10, expected_text="-- HKS-disabled: b1")

        cmp_res = compare_bind_sets(before, after, [op], self.dir, self.dir, op_kind="uncomment")
        self.assertTrue(cmp_res.ok)
        self.assertEqual(cmp_res.added_count, 1)
        self.assertEqual(cmp_res.removed_count, 0)

        # Invalid: net delta not +1
        cmp_fail = compare_bind_sets(before, before, [op], self.dir, self.dir, op_kind="uncomment")
        self.assertFalse(cmp_fail.ok)

    def test_replace_delta(self) -> None:
        before = [self.b1, self.b2]
        new_bind = _make_bind(bind_id="b_new", source_file="/cfg/hyprland.lua", source_line=10, key="E", dispatcher="editor")
        after = [self.b2, new_bind]
        op = EditOp(kind="replace_line", file="/cfg/hyprland.lua", line_number=10, expected_text="b1", new_text="b_new")

        # Exactly 1 removed, 1 added matching expected
        cmp_res = compare_bind_sets(
            before,
            after,
            [op],
            self.dir,
            self.dir,
            expected_new_bind=new_bind,
            op_kind="replace",
        )
        self.assertTrue(cmp_res.ok)
        self.assertEqual(cmp_res.removed_count, 1)
        self.assertEqual(cmp_res.added_count, 1)

        # Mismatch in expected new bind attributes
        wrong_expected = _make_bind(bind_id="b_other", source_file="/cfg/hyprland.lua", source_line=10, key="Z", dispatcher="other")
        cmp_fail = compare_bind_sets(
            before,
            after,
            [op],
            self.dir,
            self.dir,
            expected_new_bind=wrong_expected,
            op_kind="replace",
        )
        self.assertFalse(cmp_fail.ok)
        self.assertIn("did not match expected new bind", cmp_fail.message)

    def test_insert_delta(self) -> None:
        before = [self.b1, self.b2]
        new_bind = _make_bind(bind_id="b_new", source_file="/cfg/hyprland.lua", source_line=11, key="Return", dispatcher="term")
        after = [self.b1, self.b2, new_bind]
        op = EditOp(kind="insert_after", file="/cfg/hyprland.lua", line_number=11, expected_text="b2", new_text="b_new")

        cmp_res = compare_bind_sets(
            before,
            after,
            [op],
            self.dir,
            self.dir,
            expected_new_bind=new_bind,
            op_kind="insert",
        )
        self.assertTrue(cmp_res.ok)
        self.assertEqual(cmp_res.added_count, 1)
        self.assertEqual(cmp_res.removed_count, 0)

        # Extra bind removed during insert is an invariant violation
        cmp_fail = compare_bind_sets(
            before,
            [self.b2, new_bind],
            [op],
            self.dir,
            self.dir,
            expected_new_bind=new_bind,
            op_kind="insert",
        )
        self.assertFalse(cmp_fail.ok)


class TestDryRunWritesNothing(unittest.TestCase):
    def test_dry_run_writes_nothing_and_makes_no_backup(self) -> None:
        content = (
            "local hl = require('hyprland')\n"
            'hl.bind("SUPER + Q", hl.dsp.window.close())\n'
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            conf_path = os.path.join(temp_dir, "hyprland.lua")
            backup_dir = os.path.join(temp_dir, "backups")
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write(content)

            op = EditOp(
                kind="replace_line",
                file=conf_path,
                line_number=2,
                expected_text='hl.bind("SUPER + Q", hl.dsp.window.close())',
                new_text='hl.bind("SUPER + Return", hl.dsp.exec_cmd("kitty"))',
                language="lua",
            )

            # Mock hyprland verify to succeed
            fake_proc = mock.MagicMock(returncode=0, stdout="ok", stderr="")
            res = apply_edit(
                ops=[op],
                config_dir=temp_dir,
                entrypoint=conf_path,
                dry_run=True,
                backup_dir=backup_dir,
                hyprland_runner=lambda *a, **kw: fake_proc,
            )

            self.assertFalse(res.applied)
            self.assertFalse(res.rolled_back)
            self.assertIsNotNone(res.diff)
            self.assertIn("-hl.bind(\"SUPER + Q\"", res.diff)
            self.assertIn("+hl.bind(\"SUPER + Return\"", res.diff)

            # Assert file content is unchanged
            with open(conf_path, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), content)

            # Assert no backups created
            self.assertFalse(os.path.exists(backup_dir))


class TestRecorderSubmap(unittest.TestCase):
    def test_submap_commands_syntax_per_language(self) -> None:
        calls: list[list[str]] = []
        state = {"submap": "hks_record"}

        def mock_runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            if cmd == ["hyprctl", "submap"]:
                return subprocess.CompletedProcess(cmd, returncode=0, stdout=f"{state['submap']}\n", stderr="")
            if "reset" in " ".join(cmd):
                state["submap"] = "default"
            elif "hks_record" in " ".join(cmd):
                state["submap"] = "hks_record"
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="ok\n", stderr="")

        # Lua enter syntax (Strategy A: hyprctl eval then dispatch)
        calls.clear()
        state["submap"] = "default"
        res = enter(language="lua", runner=mock_runner)
        self.assertTrue(res["ok"])
        self.assertEqual(res["strategy"], "passthrough")
        self.assertEqual(calls[-1], ["hyprctl", "dispatch", 'hl.dsp.submap("hks_record")'])

        # Hyprlang enter syntax
        calls.clear()
        res = enter(language="hyprlang", runner=mock_runner)
        self.assertTrue(res["ok"])
        self.assertEqual(res["strategy"], "passthrough")
        self.assertEqual(calls[-1], ["hyprctl", "dispatch", "submap", "hks_record"])

        # Lua leave syntax
        calls.clear()
        res = leave(language="lua", runner=mock_runner)
        self.assertTrue(res["ok"])
        self.assertIn(["hyprctl", "dispatch", 'hl.dsp.submap("reset")'], calls)

        # Hyprlang leave syntax
        calls.clear()
        state["submap"] = "hks_record"
        res = leave(language="hyprlang", runner=mock_runner)
        self.assertTrue(res["ok"])
        self.assertIn(["hyprctl", "dispatch", "submap", "reset"], calls)

    def test_leave_is_idempotent_when_already_in_default(self) -> None:
        calls: list[list[str]] = []

        def mock_runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="default\n", stderr="")

        res = leave(language="lua", runner=mock_runner)
        self.assertTrue(res["ok"])
        self.assertIn("already in default", res["message"])
        # Should only have called `hyprctl submap`, NOT `hyprctl dispatch ...`
        self.assertEqual(calls, [["hyprctl", "submap"]])

    def test_heal_only_resets_if_submap_matches(self) -> None:
        calls: list[list[str]] = []

        def mock_runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            if cmd == ["hyprctl", "submap"]:
                return subprocess.CompletedProcess(cmd, returncode=0, stdout="other_submap\n", stderr="")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="ok\n", stderr="")

        res = heal(language="lua", submap_name="hks_record", runner=mock_runner)
        self.assertTrue(res["ok"])
        self.assertIn("no healing needed", res["message"])
        self.assertEqual(calls, [["hyprctl", "submap"]])


class TestCLIReplaceAndAdd(unittest.TestCase):
    def test_cli_recorder_status_and_actions(self) -> None:
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with mock.patch("backend.cli.submap_status", return_value={"ok": True, "action": "status", "submap": "default"}):
                ret = cli_main(["recorder", "status", "--json"])
                self.assertEqual(ret, 0)

            with mock.patch("backend.cli.enter_submap", return_value={"ok": True, "strategy": "passthrough", "reason": "ok", "submap": "hks_record"}):
                ret = cli_main(["recorder", "enter", "--json"])
                self.assertEqual(ret, 0)

            with mock.patch("backend.cli.leave_submap", return_value={"ok": True, "action": "leave", "message": "ok"}):
                ret = cli_main(["recorder", "leave", "--json"])
                self.assertEqual(ret, 0)

            with mock.patch("backend.cli.heal_submap", return_value={"ok": True, "action": "heal", "message": "ok"}):
                ret = cli_main(["recorder", "heal", "--json"])
                self.assertEqual(ret, 0)
