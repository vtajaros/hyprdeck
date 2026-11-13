"""Regression tests for Phase 3b-5 / 3b-6 fixes and Hyprlang end-to-end verification (UNIT-ONLY)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys

from backend.describe.sidecar_store import migrate_override, save_override
from backend.editor.apply import (
    apply_edit,
    resolve_insert_op,
    resolve_replace_op,
    resolve_uncomment_op,
)
from backend.editor.backups import list_backups, restore_backup
from backend.editor.codegen import generate_hyprlang_bind, generate_lua_bind
from backend.editor.disabled import detect_disabled_binds
from backend.editor.edit_plan import EditOp
from backend.parser import parse_hyprlang_config, parse_lua_config
from backend.tests.isolation import IsolatedTestCase, assert_env_isolated, assert_path_isolated

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REAL_CONF = os.path.expanduser("~/.config/hypr/hyprland.conf")


def _sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _hyprlang_runner(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    """UNIT-ONLY verification runner using validate_hyprlang_structure for .conf files."""
    if len(cmd) >= 4 and cmd[1] == "--verify-config" and cmd[2] == "--config":
        from backend.editor.validator import validate_hyprlang_structure
        cfg_path = cmd[3]
        with open(cfg_path, "r", encoding="utf-8") as f:
            res = validate_hyprlang_structure(f.read(), entrypoint=cfg_path)
        if res.ok:
            return subprocess.CompletedProcess(
                cmd, 0, stdout="======== Config parsing result:\n\nconfig ok\n", stderr=""
            )
        return subprocess.CompletedProcess(
            cmd, 1, stdout=f"======== Config parsing result:\n\n{res.message}\n", stderr=""
        )
    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


class TestMultiLineLuaBind(IsolatedTestCase):
    """Part 1.1 & Part 4: Multi-line hl.bind(...) span extraction, replace, delete, disable, enable."""

    def _write_and_parse(self, content: bytes, name: str = "hyprland.lua"):
        cfg_dir = os.path.join(self._isolated_root, "cfg")
        os.makedirs(cfg_dir, exist_ok=True)
        ep = os.path.join(cfg_dir, name)
        with open(ep, "wb") as f:
            f.write(content)
        binds, *_ = parse_lua_config(ep, cfg_dir)
        return cfg_dir, ep, binds

    def test_multiline_replace_with_table_parens_and_trailing_comment(self) -> None:
        src = (
            'local mainMod = "SUPER"\n'
            'hl.bind(\n'
            '    mainMod .. " + F9",\n'
            '    hl.dsp.exec_cmd("echo (nested)"),\n'
            '    { locked = true }\n'
            ') -- keep comment\n'
            'hl.bind("SUPER + Q", hl.dsp.window.close())\n'
        ).encode("utf-8")
        cfg_dir, ep, binds = self._write_and_parse(src)
        b_f9 = [b for b in binds if b.key == "F9"][0]
        self.assertIn("\n", b_f9.original_line)
        self.assertIn("-- keep comment", b_f9.original_line)

        op, _, exp = resolve_replace_op(
            b_f9.id, ["SUPER", "SHIFT"], "F10", binds=binds, preserve_dispatcher=True
        )
        res = apply_edit(
            config_dir=cfg_dir, entrypoint=ep, ops=[op], expected_new_bind=exp,
            dry_run=False, backup_dir=self.backup_dir,
        )
        self.assertTrue(res.applied, res.errors)
        with open(ep, "r", encoding="utf-8") as f:
            after = f.read()
        self.assertEqual(
            after,
            'local mainMod = "SUPER"\n'
            'hl.bind(\n'
            '    mainMod .. " + SHIFT + F10",\n'
            '    hl.dsp.exec_cmd("echo (nested)"),\n'
            '    { locked = true }\n'
            ') -- keep comment\n'
            'hl.bind("SUPER + Q", hl.dsp.window.close())\n',
        )

    def test_multiline_replace_crlf_and_eof_without_trailing_newline(self) -> None:
        src = (
            'hl.bind(\r\n'
            '    "SUPER + F8",\r\n'
            '    hl.dsp.exec_cmd("true")\r\n'
            ')'
        ).encode("utf-8")
        cfg_dir, ep, binds = self._write_and_parse(src)
        b_f8 = binds[0]
        op, _, exp = resolve_replace_op(
            b_f8.id, ["ALT"], "F8", binds=binds, preserve_dispatcher=True
        )
        res = apply_edit(
            config_dir=cfg_dir, entrypoint=ep, ops=[op], expected_new_bind=exp,
            dry_run=False, backup_dir=self.backup_dir,
        )
        self.assertTrue(res.applied, res.errors)
        with open(ep, "rb") as f:
            raw_after = f.read()
        self.assertEqual(
            raw_after,
            b'hl.bind(\r\n    "ALT + F8",\r\n    hl.dsp.exec_cmd("true")\r\n)',
        )

    def test_multiline_delete_disable_enable(self) -> None:
        src = (
            'hl.bind(\n'
            '    "SUPER + F7",\n'
            '    hl.dsp.exec_cmd("true")\n'
            ')\n'
            'hl.bind("SUPER + Q", hl.dsp.window.close())\n'
        ).encode("utf-8")
        cfg_dir, ep, binds = self._write_and_parse(src)
        b_f7 = [b for b in binds if b.key == "F7"][0]

        op_dis = EditOp(
            kind="comment_out", file=ep, line_number=b_f7.source_line,
            expected_text=b_f7.original_line, language="lua",
        )
        res_dis = apply_edit(
            config_dir=cfg_dir, entrypoint=ep, ops=[op_dis], dry_run=False, backup_dir=self.backup_dir
        )
        self.assertTrue(res_dis.applied, res_dis.errors)

        disabled = detect_disabled_binds(ep, cfg_dir, "lua")
        self.assertEqual(len(disabled), 1)
        op_en = resolve_uncomment_op(disabled[0].id, cfg_dir, ep)
        res_en = apply_edit(
            config_dir=cfg_dir, entrypoint=ep, ops=[op_en], dry_run=False, backup_dir=self.backup_dir
        )
        self.assertTrue(res_en.applied, res_en.errors)
        with open(ep, "rb") as f:
            self.assertEqual(f.read(), src)

        binds2, *_ = parse_lua_config(ep, cfg_dir)
        b_f7_2 = [b for b in binds2 if b.key == "F7"][0]
        op_del = EditOp(
            kind="delete_line", file=ep, line_number=b_f7_2.source_line,
            expected_text=b_f7_2.original_line, language="lua",
        )
        res_del = apply_edit(
            config_dir=cfg_dir, entrypoint=ep, ops=[op_del], dry_run=False, backup_dir=self.backup_dir
        )
        self.assertTrue(res_del.applied, res_del.errors)
        with open(ep, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), 'hl.bind("SUPER + Q", hl.dsp.window.close())\n')

    def test_multiline_parens_brackets_quotes_inside_strings(self) -> None:
        src = (
            'hl.bind(\n'
            '    "SUPER + F6",\n'
            '    hl.dsp.exec_cmd("echo \\")( [\'hi\'] )\\"")\n'
            ')\n'
        ).encode("utf-8")
        cfg_dir, ep, binds = self._write_and_parse(src)
        op, _, exp = resolve_replace_op(binds[0].id, ["ALT"], "F6", binds=binds, preserve_dispatcher=True)
        res = apply_edit(config_dir=cfg_dir, entrypoint=ep, ops=[op], expected_new_bind=exp, dry_run=False, backup_dir=self.backup_dir)
        self.assertTrue(res.applied, res.errors)
        with open(ep, "r", encoding="utf-8") as f:
            self.assertIn('"ALT + F6"', f.read())

    def test_multiline_nested_tables_and_inline_functions(self) -> None:
        src = (
            'hl.bind(\n'
            '    "SUPER + F5",\n'
            '    function()\n'
            '        local t = { a = { 1, 2 }, b = ")" }\n'
            '        return t\n'
            '    end\n'
            ')\n'
        ).encode("utf-8")
        cfg_dir, ep, binds = self._write_and_parse(src)
        op, _, exp = resolve_replace_op(binds[0].id, ["ALT"], "F5", binds=binds, preserve_dispatcher=True)
        res = apply_edit(config_dir=cfg_dir, entrypoint=ep, ops=[op], expected_new_bind=exp, dry_run=False, backup_dir=self.backup_dir)
        self.assertTrue(res.applied, res.errors)
        with open(ep, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('"ALT + F5"', content)
        self.assertIn("local t = { a = { 1, 2 }, b = \")\" }", content)

    def test_multiline_comment_with_unbalanced_parens(self) -> None:
        src = (
            'hl.bind(\n'
            '    "SUPER + F4", -- comment with unbalanced ) ) (\n'
            '    hl.dsp.exec_cmd("true") -- another )\n'
            ')\n'
        ).encode("utf-8")
        cfg_dir, ep, binds = self._write_and_parse(src)
        op, _, exp = resolve_replace_op(binds[0].id, ["ALT"], "F4", binds=binds, preserve_dispatcher=True)
        res = apply_edit(config_dir=cfg_dir, entrypoint=ep, ops=[op], expected_new_bind=exp, dry_run=False, backup_dir=self.backup_dir)
        self.assertTrue(res.applied, res.errors)
        with open(ep, "r", encoding="utf-8") as f:
            self.assertIn('"ALT + F4"', f.read())

    def test_multiline_bind_immediately_followed_by_another_bind(self) -> None:
        src = (
            'hl.bind(\n'
            '    "SUPER + F2",\n'
            '    hl.dsp.exec_cmd("one")\n'
            ')\n'
            'hl.bind("SUPER + F3", hl.dsp.exec_cmd("two"))\n'
        ).encode("utf-8")
        cfg_dir, ep, binds = self._write_and_parse(src)
        b_f2 = [b for b in binds if b.key == "F2"][0]
        op, _, exp = resolve_replace_op(b_f2.id, ["ALT"], "F2", binds=binds, preserve_dispatcher=True)
        res = apply_edit(config_dir=cfg_dir, entrypoint=ep, ops=[op], expected_new_bind=exp, dry_run=False, backup_dir=self.backup_dir)
        self.assertTrue(res.applied, res.errors)
        with open(ep, "r", encoding="utf-8") as f:
            self.assertEqual(
                f.read(),
                'hl.bind(\n    "ALT + F2",\n    hl.dsp.exec_cmd("one")\n)\nhl.bind("SUPER + F3", hl.dsp.exec_cmd("two"))\n',
            )

    def test_multiline_first_arg_on_next_line(self) -> None:
        src = (
            'hl.bind(\n'
            '    "SUPER + F1",\n'
            '    hl.dsp.window.close()\n'
            ')\n'
        ).encode("utf-8")
        cfg_dir, ep, binds = self._write_and_parse(src)
        op, _, exp = resolve_replace_op(binds[0].id, ["CTRL"], "F1", binds=binds, preserve_dispatcher=True)
        res = apply_edit(config_dir=cfg_dir, entrypoint=ep, ops=[op], expected_new_bind=exp, dry_run=False, backup_dir=self.backup_dir)
        self.assertTrue(res.applied, res.errors)
        with open(ep, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), 'hl.bind(\n    "CTRL + F1",\n    hl.dsp.window.close()\n)\n')


class TestHyprlangDispatcherMapping(IsolatedTestCase):
    """Part 1.2 & Part 2: Lossless Lua -> Hyprlang dispatcher mapping & refusal."""

    def test_exec_cmd_mapped(self) -> None:
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "F10", "exec_cmd", "kitty"), "bind = SUPER, F10, exec, kitty")
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "F10", "hl.dsp.exec_cmd", '{ cmd = "kitty" }'), "bind = SUPER, F10, exec, kitty")

    def test_window_close_mapped(self) -> None:
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "Q", "window.close", None), "bind = SUPER, Q, killactive")

    def test_window_float_conditional(self) -> None:
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "V", "window.float", '{ action = "toggle" }'), "bind = SUPER, V, togglefloating")
        with self.assertRaisesRegex(ValueError, "not supported for Hyprlang"):
            generate_hyprlang_bind(["SUPER"], "V", "window.float", '{ action = "float" }')

    def test_window_fullscreen_conditional(self) -> None:
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "F", "window.fullscreen", '{ mode = "fullscreen" }'), "bind = SUPER, F, fullscreen, 0")
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "F", "window.fullscreen", '{ mode = "maximized" }'), "bind = SUPER, F, fullscreen, 1")
        with self.assertRaisesRegex(ValueError, "not supported for Hyprlang"):
            generate_hyprlang_bind(["SUPER"], "F", "window.fullscreen", '{ mode = "bogus" }')

    def test_focus_conditional(self) -> None:
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "H", "focus", '{ direction = "left" }'), "bind = SUPER, H, movefocus, l")
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "2", "focus", '{ workspace = 2 }'), "bind = SUPER, 2, workspace, 2")
        with self.assertRaisesRegex(ValueError, "not supported for Hyprlang"):
            generate_hyprlang_bind(["SUPER"], "H", "focus", '{ monitor = "DP-1" }')

    def test_window_move_conditional(self) -> None:
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "H", "window.move", '{ direction = "right" }'), "bind = SUPER, H, movewindow, r")
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "2", "window.move", '{ workspace = 2 }'), "bind = SUPER, 2, movetoworkspace, 2")
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "2", "window.move", '{ workspace = 2, silent = true }'), "bind = SUPER, 2, movetoworkspacesilent, 2")
        with self.assertRaisesRegex(ValueError, "not supported for Hyprlang"):
            generate_hyprlang_bind(["SUPER"], "H", "window.move", '{ monitor = "DP-1" }')

    def test_workspace_and_movetoworkspace_mapped(self) -> None:
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "1", "workspace", "1"), "bind = SUPER, 1, workspace, 1")
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "1", "movetoworkspace", '{ workspace = "1", silent = true }'), "bind = SUPER, 1, movetoworkspacesilent, 1")

    def test_window_resize_mapped_and_refused(self) -> None:
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "R", "window.resize", '{ x = 20, y = -10, relative = true }'), "bind = SUPER, R, resizeactive, 20 -10")
        with self.assertRaisesRegex(ValueError, "not supported for Hyprlang"):
            generate_hyprlang_bind(["SUPER"], "R", "window.resize", '{ percent = 10 }')

    def test_window_pin_mapped(self) -> None:
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "P", "window.pin", None), "bind = SUPER, P, pin")

    def test_layout_conditional(self) -> None:
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "J", "layout", "togglesplit"), "bind = SUPER, J, layoutmsg, togglesplit")
        with self.assertRaisesRegex(ValueError, "not supported for Hyprlang"):
            generate_hyprlang_bind(["SUPER"], "J", "layout", "swapsplit")

    def test_submap_mapped(self) -> None:
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "R", "submap", "resize"), "bind = SUPER, R, submap, resize")
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "R", "hl.dsp.submap", '{ submap = "resize" }'), "bind = SUPER, R, submap, resize")

    def test_custom_and_unknown_refused_before_plan(self) -> None:
        with self.assertRaisesRegex(ValueError, "not supported for Hyprlang"):
            generate_hyprlang_bind(["SUPER"], "X", "custom", "my_custom()")
        with self.assertRaisesRegex(ValueError, "not supported for Hyprlang"):
            resolve_insert_op("/tmp/x.conf", "hyprlang", ["SUPER"], "X", "hl.dsp.unknown_fn", "1")


class TestSymlinkSafety(IsolatedTestCase):
    """Part 1.3: atomic_write_bytes preserves symlink and updates target."""

    def test_symlinked_config_stays_symlink(self) -> None:
        cfg_dir = os.path.join(self._isolated_root, "cfg")
        os.makedirs(cfg_dir, exist_ok=True)
        real_target = os.path.join(cfg_dir, "real_hyprland.lua")
        with open(real_target, "w", encoding="utf-8") as f:
            f.write('hl.bind("SUPER + Q", hl.dsp.window.close())\n')
        os.chmod(real_target, 0o640)
        sym_ep = os.path.join(cfg_dir, "hyprland.lua")
        os.symlink("real_hyprland.lua", sym_ep)

        op, _, exp = resolve_insert_op(sym_ep, "lua", ["SUPER", "ALT"], "F10", "exec_cmd", "kitty")
        res = apply_edit(
            config_dir=cfg_dir, entrypoint=sym_ep, ops=[op], expected_new_bind=exp,
            dry_run=False, backup_dir=self.backup_dir,
        )
        self.assertTrue(res.applied, res.errors)
        self.assertTrue(os.path.islink(sym_ep), "Symlink was replaced with a regular file!")
        self.assertIsNotNone(res.backup)
        with open(real_target, "r", encoding="utf-8") as f:
            self.assertIn("F10", f.read())


class TestEmptyArgsRejection(IsolatedTestCase):
    """Part 1.4: Empty / whitespace-only args rejected before plan is built."""

    def test_backend_api_rejects_empty_args(self) -> None:
        for bad in ("", "   ", None):
            with self.assertRaises(ValueError):
                generate_lua_bind(["SUPER"], "F10", "exec_cmd", bad)
            with self.assertRaises(ValueError):
                generate_hyprlang_bind(["SUPER"], "F10", "exec_cmd", bad)
            with self.assertRaises(ValueError):
                resolve_insert_op("/tmp/x.lua", "lua", ["SUPER"], "F10", "exec_cmd", bad)

        cfg_dir = os.path.join(self._isolated_root, "cfg")
        os.makedirs(cfg_dir, exist_ok=True)
        ep = os.path.join(cfg_dir, "hyprland.lua")
        with open(ep, "w", encoding="utf-8") as f:
            f.write('hl.bind("SUPER + Q", hl.dsp.window.close())\n')
        binds, *_ = parse_lua_config(ep, cfg_dir)
        with self.assertRaises(ValueError):
            resolve_replace_op(binds[0].id, ["SUPER"], "Q", "exec_cmd", "   ", binds=binds)

    def test_cli_rejects_empty_args(self) -> None:
        cfg_dir = os.path.join(self._isolated_root, "cfg")
        os.makedirs(cfg_dir, exist_ok=True)
        ep = os.path.join(cfg_dir, "hyprland.lua")
        with open(ep, "w", encoding="utf-8") as f:
            f.write('hl.bind("SUPER + Q", hl.dsp.window.close())\n')
        p = subprocess.run(
            [
                sys.executable, "-m", "backend.cli", "edit", "add",
                "--mods", "SUPER", "--key", "F10", "--dispatcher", "exec_cmd", "--args", "   ",
                "--config-dir", cfg_dir, "--entrypoint", ep, "--no-live", "--dry-run", "--json",
            ],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("requires non-empty arguments", p.stdout + p.stderr)


class TestIsolationGuard(IsolatedTestCase):
    """Part 1.5: Test-isolation guard rejects $HOME and real paths."""

    def test_guard_rejects_home_and_real_paths(self) -> None:
        with self.assertRaises(AssertionError):
            assert_path_isolated(os.path.expanduser("~/.config/hypr/hyprland.lua"), "real_cfg")
        with self.assertRaises(AssertionError):
            assert_env_isolated({"HOME": os.path.expanduser("~")})
        self.assert_isolated()


class TestHyprlangEndToEnd(IsolatedTestCase):
    """Part 2 & Part 4: Split Hyprlang .conf E2E tests (one test per operation, UNIT-ONLY)."""

    def _setup_conf(self) -> tuple[str, str]:
        cfg_dir = os.path.join(self._isolated_root, "hypr")
        os.makedirs(cfg_dir, exist_ok=True)
        ep = os.path.join(cfg_dir, "hyprland.conf")
        if os.path.isfile(REAL_CONF):
            shutil.copy2(REAL_CONF, ep)
        else:
            with open(ep, "w", encoding="utf-8") as f:
                f.write("$mainMod = SUPER\nbind = $mainMod, Q, killactive\nbind = $mainMod, Return, exec, kitty\n")
        return cfg_dir, ep

    def test_hyprlang_replace(self) -> None:
        cfg_dir, ep = self._setup_conf()
        binds, *_ = parse_hyprlang_config(ep)
        b_q = [b for b in binds if b.key == "Q" and b.modifiers == ["SUPER"]][0]
        op, _, exp = resolve_replace_op(b_q.id, ["SUPER", "ALT"], "Q", binds=binds, preserve_dispatcher=True)
        res = apply_edit(config_dir=cfg_dir, entrypoint=ep, ops=[op], expected_new_bind=exp, dry_run=False, backup_dir=self.backup_dir, hyprland_runner=_hyprlang_runner)
        self.assertTrue(res.applied, res.errors)
        self.assertIn("$mainMod ALT, Q", res.diff)

    def test_hyprlang_add(self) -> None:
        cfg_dir, ep = self._setup_conf()
        op, _, exp = resolve_insert_op(ep, "hyprlang", ["SUPER", "ALT"], "F10", "exec_cmd", "kitty")
        res = apply_edit(config_dir=cfg_dir, entrypoint=ep, ops=[op], expected_new_bind=exp, dry_run=False, backup_dir=self.backup_dir, hyprland_runner=_hyprlang_runner)
        self.assertTrue(res.applied, res.errors)
        self.assertIn("bind = SUPER ALT, F10, exec, kitty", res.diff)

    def test_hyprlang_disable_and_enable(self) -> None:
        cfg_dir, ep = self._setup_conf()
        binds, *_ = parse_hyprlang_config(ep)
        b_q = [b for b in binds if b.key == "Q" and b.modifiers == ["SUPER"]][0]
        op_dis = EditOp(kind="comment_out", file=ep, line_number=b_q.source_line, expected_text=b_q.original_line, language="hyprlang")
        res_dis = apply_edit(config_dir=cfg_dir, entrypoint=ep, ops=[op_dis], dry_run=False, backup_dir=self.backup_dir, hyprland_runner=_hyprlang_runner)
        self.assertTrue(res_dis.applied, res_dis.errors)

        disabled = [d for d in detect_disabled_binds(ep, cfg_dir, "hyprlang") if "Q" in d.key_hint]
        self.assertTrue(len(disabled) >= 1)
        op_en = resolve_uncomment_op(disabled[-1].id, cfg_dir, ep)
        res_en = apply_edit(config_dir=cfg_dir, entrypoint=ep, ops=[op_en], dry_run=False, backup_dir=self.backup_dir, hyprland_runner=_hyprlang_runner)
        self.assertTrue(res_en.applied, res_en.errors)

    def test_hyprlang_delete(self) -> None:
        cfg_dir, ep = self._setup_conf()
        binds, *_ = parse_hyprlang_config(ep)
        b_q = [b for b in binds if b.key == "Q" and b.modifiers == ["SUPER"]][0]
        op_del = EditOp(kind="delete_line", file=ep, line_number=b_q.source_line, expected_text=b_q.original_line, language="hyprlang")
        res = apply_edit(config_dir=cfg_dir, entrypoint=ep, ops=[op_del], dry_run=False, backup_dir=self.backup_dir, hyprland_runner=_hyprlang_runner)
        self.assertTrue(res.applied, res.errors)

    def test_hyprlang_rollback_on_reload_failure(self) -> None:
        cfg_dir, ep = self._setup_conf()
        pre_sha = _sha256(ep)
        def fail_reload(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="reload boom")
        op, _, exp = resolve_insert_op(ep, "hyprlang", ["SUPER", "ALT"], "F11", "exec_cmd", "true")
        res = apply_edit(config_dir=cfg_dir, entrypoint=ep, ops=[op], expected_new_bind=exp, dry_run=False, reload=True, backup_dir=self.backup_dir, hyprland_runner=_hyprlang_runner, reload_runner=fail_reload)
        self.assertFalse(res.applied)
        self.assertTrue(res.rolled_back)
        self.assertEqual(_sha256(ep), pre_sha)

    def test_hyprlang_restore(self) -> None:
        cfg_dir, ep = self._setup_conf()
        orig_sha = _sha256(ep)
        op, _, exp = resolve_insert_op(ep, "hyprlang", ["SUPER", "ALT"], "F10", "exec_cmd", "kitty")
        apply_edit(config_dir=cfg_dir, entrypoint=ep, ops=[op], expected_new_bind=exp, dry_run=False, backup_dir=self.backup_dir, hyprland_runner=_hyprlang_runner)
        self.assertNotEqual(_sha256(ep), orig_sha)
        rec = list_backups(ep, backup_dir=self.backup_dir)[0]
        restore_backup(rec.id, backup_dir=self.backup_dir, force=True)
        self.assertEqual(_sha256(ep), orig_sha)

    def test_hyprlang_sidecar_migration_on_shortcut_edit(self) -> None:
        cfg_dir, ep = self._setup_conf()
        binds, *_ = parse_hyprlang_config(ep)
        b_q = [b for b in binds if b.key == "Q" and b.modifiers == ["SUPER"]][0]
        save_override(self.sidecar_path, {"modifiers": b_q.modifiers, "key": b_q.key, "submap": b_q.submap, "dispatcher": b_q.dispatcher.path}, description="Close Win", category="Windows", backup_dir=self.backup_dir)
        op, _, exp = resolve_replace_op(b_q.id, ["SUPER", "ALT"], "Q", binds=binds, preserve_dispatcher=True)
        res = apply_edit(config_dir=cfg_dir, entrypoint=ep, ops=[op], expected_new_bind=exp, dry_run=False, backup_dir=self.backup_dir, hyprland_runner=_hyprlang_runner)
        self.assertTrue(res.applied, res.errors)
        migrate_override(self.sidecar_path, {"modifiers": b_q.modifiers, "key": b_q.key, "submap": b_q.submap, "dispatcher": b_q.dispatcher.path}, {"modifiers": exp.modifiers, "key": exp.key, "submap": exp.submap, "dispatcher": exp.dispatcher.path}, backup_dir=self.backup_dir)
        with open(self.sidecar_path, "r", encoding="utf-8") as f:
            sc_data = json.load(f)
        self.assertEqual(sc_data["overrides"][0]["match"]["modifiers"], ["SUPER", "ALT"])


class TestPhase3b7StrictLosslessMapping(IsolatedTestCase):
    """Milestone 3b-7: strictly lossless-or-refuse Hyprlang dispatcher mapping."""

    def test_1_no_native_passthrough_unvalidated_refused(self) -> None:
        from backend.editor.dispatchers import map_lua_dispatcher_to_hyprlang

        for dsp, arg in [("exec", ""), ("exec", "   "), ("movewindow", "x"), ("resizewindow", "10 10")]:
            with self.subTest(dsp=dsp, arg=arg):
                with self.assertRaisesRegex(ValueError, "not supported for Hyprlang"):
                    map_lua_dispatcher_to_hyprlang(dsp, arg)

    def test_2_lua_string_literal_decoding_and_refusal(self) -> None:
        from backend.editor.dispatchers import map_lua_dispatcher_to_hyprlang

        self.assertEqual(map_lua_dispatcher_to_hyprlang("workspace", '"3"'), ("workspace", "3"))
        self.assertEqual(
            map_lua_dispatcher_to_hyprlang("exec", r'"kitty --class \"x\""'),
            ("exec", 'kitty --class "x"'),
        )
        self.assertEqual(map_lua_dispatcher_to_hyprlang("submap", "'resize'"), ("submap", "resize"))
        for bad_dsp, bad_arg in [
            ("exec", '"unclosed'),
            ("exec", r'"bad\x1b"'),
            ("exec", "[[long string]]"),
            ("workspace", '"e+1" .. "x"'),
        ]:
            with self.subTest(bad_dsp=bad_dsp, bad_arg=bad_arg):
                with self.assertRaisesRegex(ValueError, "not supported for Hyprlang"):
                    map_lua_dispatcher_to_hyprlang(bad_dsp, bad_arg)

    def test_3_workspace_selector_validation(self) -> None:
        from backend.editor.dispatchers import map_lua_dispatcher_to_hyprlang

        valid = ["3", "+1", "-1", "e+1", "e-1", "r+2", "r-2", "m+1", "m-1", "name:web", "special", "special:term", "previous", "empty"]
        for sel in valid:
            with self.subTest(valid=sel):
                self.assertEqual(map_lua_dispatcher_to_hyprlang("workspace", sel), ("workspace", sel))
        for invalid in ["e+-5", "foo", "name:", "special:", "+-1", "e1"]:
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "not supported for Hyprlang"):
                    map_lua_dispatcher_to_hyprlang("workspace", invalid)

    def test_4_submap_name_validation(self) -> None:
        from backend.editor.dispatchers import map_lua_dispatcher_to_hyprlang

        for ok_name in ["resize", "reset", "my_submap-1"]:
            self.assertEqual(map_lua_dispatcher_to_hyprlang("submap", ok_name), ("submap", ok_name))
        for bad_name in ["bad submap", "a/b", "", "   "]:
            with self.assertRaisesRegex(ValueError, "not supported for Hyprlang"):
                map_lua_dispatcher_to_hyprlang("submap", bad_name)

    def test_5_direction_canonicalization(self) -> None:
        from backend.editor.dispatchers import map_lua_dispatcher_to_hyprlang

        for raw_dir, expected in [("left", "l"), ("right", "r"), ("up", "u"), ("down", "d"), ("l", "l"), ("r", "r"), ("u", "u"), ("d", "d")]:
            self.assertEqual(map_lua_dispatcher_to_hyprlang("focus", f'{{ direction = "{raw_dir}" }}'), ("movefocus", expected))
            self.assertEqual(map_lua_dispatcher_to_hyprlang("window.move", raw_dir), ("movewindow", expected))

    def test_6_resizeactive_requires_both_dx_and_dy(self) -> None:
        from backend.editor.dispatchers import map_lua_dispatcher_to_hyprlang

        self.assertEqual(map_lua_dispatcher_to_hyprlang("window.resize", "{ x = 20, y = 0, relative = true }"), ("resizeactive", "20 0"))
        for bad in ["{ x = 20, relative = true }", "{ y = 10, relative = true }", "{ dx = 20, dy = 0 }", "{}"]:
            with self.assertRaisesRegex(ValueError, "not supported for Hyprlang"):
                map_lua_dispatcher_to_hyprlang("window.resize", bad)

    def test_7_layout_togglesplit_emits_layoutmsg(self) -> None:
        from backend.editor.dispatchers import map_lua_dispatcher_to_hyprlang

        self.assertEqual(map_lua_dispatcher_to_hyprlang("layout", "togglesplit"), ("layoutmsg", "togglesplit"))
        self.assertEqual(map_lua_dispatcher_to_hyprlang("hl.dsp.layout", '{ action = "togglesplit" }'), ("layoutmsg", "togglesplit"))
        self.assertEqual(map_lua_dispatcher_to_hyprlang("togglesplit", None), ("layoutmsg", "togglesplit"))

    def test_8_catalog_lua_templates_compatible_with_mapper(self) -> None:
        from backend.editor.dispatchers import map_lua_dispatcher_to_hyprlang

        self.assertEqual(map_lua_dispatcher_to_hyprlang("exec_cmd", '{ cmd = "kitty" }'), ("exec", "kitty"))
        self.assertEqual(map_lua_dispatcher_to_hyprlang("window.fullscreen", '{ mode = "fullscreen" }'), ("fullscreen", "0"))
        self.assertEqual(map_lua_dispatcher_to_hyprlang("window.fullscreen", '{ mode = "maximized" }'), ("fullscreen", "1"))
        self.assertEqual(map_lua_dispatcher_to_hyprlang("window.resize", "{ x = 20, y = 0, relative = true }"), ("resizeactive", "20 0"))
        self.assertEqual(map_lua_dispatcher_to_hyprlang("movefocus", '{ direction = "left" }'), ("movefocus", "l"))
        self.assertEqual(map_lua_dispatcher_to_hyprlang("togglesplit", None), ("layoutmsg", "togglesplit"))

    def test_9_cli_add_and_replace_refusal_returns_json_error_without_write(self) -> None:
        cfg_dir = os.path.join(self._isolated_root, "cfg_cli")
        os.makedirs(cfg_dir, exist_ok=True)
        ep = os.path.join(cfg_dir, "hyprland.conf")
        with open(ep, "w", encoding="utf-8") as f:
            f.write("bind = SUPER, Q, killactive\n")
        orig_sha = _sha256(ep)
        env = os.environ.copy()
        env["HKS_BACKUP_DIR"] = self.backup_dir
        env["HKS_SIDECAR_PATH"] = self.sidecar_path

        proc_add = subprocess.run(
            [sys.executable, "-m", "backend.cli", "edit", "add", "--config-dir", cfg_dir, "--mods", "SUPER", "--key", "X", "--dispatcher", "movewindow", "--args", "x", "--no-live", "--json"],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_add.returncode, 1)
        data_add = json.loads(proc_add.stdout)
        self.assertFalse(data_add["applied"])
        self.assertTrue(any("not supported for Hyprlang" in e for e in data_add["errors"]), data_add)
        self.assertEqual(_sha256(ep), orig_sha)

        binds, *_ = parse_hyprlang_config(ep)
        proc_rep = subprocess.run(
            [sys.executable, "-m", "backend.cli", "edit", "replace", "--config-dir", cfg_dir, "--id", binds[0].id, "--mods", "SUPER", "--key", "Q", "--dispatcher", "exec", "--args", "   ", "--no-live", "--json"],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_rep.returncode, 1)
        data_rep = json.loads(proc_rep.stdout)
        self.assertFalse(data_rep["applied"])
        self.assertTrue(data_rep["errors"], data_rep)
        self.assertEqual(_sha256(ep), orig_sha)


class TestPhase3b8RecorderWatchdog(IsolatedTestCase):
    """Milestone 3b-8: detached setsid watchdog, retries, and startup heal."""

    def _make_mock_hyprctl_env(self, initial_submap: str = "default") -> tuple[dict[str, str], str, str]:
        bin_dir = os.path.join(self._isolated_root, "mock_bin")
        os.makedirs(bin_dir, exist_ok=True)
        state_path = os.path.join(self._isolated_root, "hypr_state.json")
        log_path = os.path.join(self._isolated_root, "hypr_calls.log")
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({"submap": initial_submap, "binds": []}, f)
        shim_path = os.path.join(bin_dir, "hyprctl")
        shim_code = f"""#!{sys.executable}
import json, sys
state_file = {state_path!r}
log_file = {log_path!r}
args = sys.argv[1:]
with open(log_file, "a", encoding="utf-8") as lf:
    lf.write(" ".join(args) + "\\n")
with open(state_file, "r", encoding="utf-8") as sf:
    st = json.load(sf)
if args == ["submap"]:
    print(st["submap"])
elif args == ["binds", "-j"]:
    print(json.dumps(st["binds"]))
elif len(args) >= 2 and args[0] == "eval":
    st["binds"] = [{{"submap": "hks_record", "key": "XF86Tools", "modmask": 0, "dispatcher": "HL.Dispatcher(submap)"}}]
    with open(state_file, "w", encoding="utf-8") as sf:
        json.dump(st, sf)
elif len(args) >= 2 and args[0] == "dispatch":
    cmd = " ".join(args[1:])
    if "reset" in cmd:
        st["submap"] = "default"
    elif "hks_record" in cmd:
        st["submap"] = "hks_record"
    with open(state_file, "w", encoding="utf-8") as sf:
        json.dump(st, sf)
elif len(args) >= 2 and args[0] == "repl" and "unbind" in args[1]:
    st["binds"] = []
    with open(state_file, "w", encoding="utf-8") as sf:
        json.dump(st, sf)
"""
        with open(shim_path, "w", encoding="utf-8") as f:
            f.write(shim_code)
        os.chmod(shim_path, 0o755)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HKS_BACKUP_DIR"] = self.backup_dir
        env["HKS_SIDECAR_PATH"] = self.sidecar_path
        return env, state_path, log_path

    def test_watchdog_required_before_entering_submap(self) -> None:
        from backend.editor.recorder_submap import enter

        calls: list[list[str]] = []

        def fake_runner(cmd, **_kwargs):
            calls.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, "", "")

        res = enter(
            language="lua",
            runner=fake_runner,
            watchdog_spawner=lambda **_kw: (False, None, "spawn blocked"),
        )
        self.assertFalse(res["ok"])
        self.assertIn("Watchdog failed to start", res["reason"])
        self.assertEqual(calls, [])

    def test_kill9_parent_triggers_detached_watchdog_reset(self) -> None:
        import signal
        import time

        env, state_path, _ = self._make_mock_hyprctl_env("default")
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import os, time; from backend.editor.recorder_submap import enter; "
                "r = enter(language='lua', watch_pid=os.getpid(), watchdog_timeout=15.0); "
                "assert r['ok'] and r['submap'] == 'hks_record', r; "
                "print('ENTERED', flush=True); time.sleep(30)",
            ],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        line = child.stdout.readline().strip() if child.stdout else ""
        self.assertEqual(line, "ENTERED")
        with open(state_path, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["submap"], "hks_record")

        os.kill(child.pid, signal.SIGKILL)
        child.wait(timeout=5)
        if child.stdout:
            child.stdout.close()
        if child.stderr:
            child.stderr.close()

        deadline = time.monotonic() + 4.0
        cur_submap = "hks_record"
        while time.monotonic() < deadline:
            with open(state_path, "r", encoding="utf-8") as f:
                st = json.load(f)
            cur_submap = st["submap"]
            if cur_submap == "default" and st["binds"] == []:
                break
            time.sleep(0.1)
        self.assertEqual(cur_submap, "default")

    def test_watchdog_fires_once_on_timeout(self) -> None:
        import time

        env, state_path, log_path = self._make_mock_hyprctl_env("default")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.cli",
                "recorder",
                "enter",
                "--watch-pid",
                str(os.getpid()),
                "--watchdog-timeout",
                "0.3",
                "--json",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        time.sleep(1.0)
        with open(state_path, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["submap"], "default")
        with open(log_path, "r", encoding="utf-8") as f:
            reset_calls = [ln for ln in f.read().splitlines() if "dispatch" in ln and "reset" in ln]
        self.assertEqual(len(reset_calls), 1, reset_calls)

    def test_watchdog_idempotent_when_already_default(self) -> None:
        from backend.editor.recorder_watchdog import run_watchdog

        env, _, log_path = self._make_mock_hyprctl_env("default")
        old_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = env["PATH"]
            rc = run_watchdog(submap_name="hks_record", language="lua", timeout_seconds=0.05, watch_pid=0, poll_interval=0.02)
            self.assertEqual(rc, 0)
        finally:
            os.environ["PATH"] = old_path
        with open(log_path, "r", encoding="utf-8") as f:
            reset_calls = [ln for ln in f.read().splitlines() if "dispatch" in ln and "reset" in ln]
        self.assertEqual(reset_calls, [])

    def test_leave_failure_retries_three_times(self) -> None:
        from backend.editor.recorder_submap import leave

        submap_reads = ["hks_record", "hks_record", "hks_record", "default"]
        reset_attempts = 0

        def flaky_runner(cmd, **_kwargs):
            nonlocal reset_attempts
            if cmd == ["hyprctl", "submap"]:
                return subprocess.CompletedProcess(cmd, 0, submap_reads.pop(0) + "\n", "")
            if len(cmd) >= 2 and cmd[1] == "dispatch":
                reset_attempts += 1
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return subprocess.CompletedProcess(cmd, 0, "[]", "")

        res = leave(language="lua", runner=flaky_runner)
        self.assertTrue(res["ok"], res)
        self.assertEqual(reset_attempts, 3)

        always_stuck = 0

        def stuck_runner(cmd, **_kwargs):
            nonlocal always_stuck
            if cmd == ["hyprctl", "submap"]:
                return subprocess.CompletedProcess(cmd, 0, "hks_record\n", "")
            if len(cmd) >= 2 and cmd[1] == "dispatch":
                always_stuck += 1
            return subprocess.CompletedProcess(cmd, 0, "", "")

        fail_res = leave(language="lua", runner=stuck_runner)
        self.assertFalse(fail_res["ok"])
        self.assertEqual(always_stuck, 3)
        self.assertIn("3 attempts", fail_res["message"])

    def test_startup_heal_on_backend_launch(self) -> None:
        cfg_dir = os.path.join(self._isolated_root, "cfg_heal")
        os.makedirs(cfg_dir, exist_ok=True)
        with open(os.path.join(cfg_dir, "hyprland.conf"), "w", encoding="utf-8") as f:
            f.write("bind = SUPER, Q, killactive\n")
        env, state_path, _ = self._make_mock_hyprctl_env("hks_record")
        proc = subprocess.run(
            [sys.executable, "-m", "backend.cli", "conflicts", "--config-dir", cfg_dir],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(state_path, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["submap"], "default")


class TestPhase3b9ResizeAndWatchdogFixes(IsolatedTestCase):
    """Milestone 3b-9: resize x/y/relative, plain movewindow refusal, and ancestor watch PID."""

    def test_1_resize_catalog_renders_x_y_relative(self) -> None:
        from backend.editor.dispatchers import render_from_catalog

        dsp, arg = render_from_catalog("resizeactive", {"dx": 20, "dy": -10}, language="lua")
        self.assertEqual(dsp, "window.resize({ x = 20, y = -10, relative = true })")
        self.assertIsNone(arg)

    def test_2_resize_hyprlang_accepts_relative_refuses_others(self) -> None:
        from backend.editor.dispatchers import map_lua_dispatcher_to_hyprlang

        self.assertEqual(
            map_lua_dispatcher_to_hyprlang("window.resize", "{ x = 20, y = 0, relative = true }"),
            ("resizeactive", "20 0"),
        )
        for bad in [
            "{ x = 20, y = 0 }",
            "{ x = 20, y = 0, relative = false }",
            '{ x = 20, y = 0, relative = true, window = "kitty" }',
            "{ x = 20, y = 0, relative = true, z = 1 }",
            '{ x = "20", y = 0, relative = true }',
            "{ dx = 20, dy = 0 }",
        ]:
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ValueError, "not supported for Hyprlang"):
                    map_lua_dispatcher_to_hyprlang("window.resize", bad)

    def test_3_movewindow_empty_args_refused_for_plain_bind_allowed_for_mouse(self) -> None:
        from backend.editor.dispatchers import map_lua_dispatcher_to_hyprlang

        with self.assertRaisesRegex(ValueError, "only valid for mouse binds"):
            map_lua_dispatcher_to_hyprlang("movewindow", None)
        with self.assertRaisesRegex(ValueError, "only valid for mouse binds"):
            map_lua_dispatcher_to_hyprlang("window.move", "")
        self.assertEqual(
            generate_hyprlang_bind(["SUPER"], "mouse:272", "movewindow", None, flags={"mouse": True}),
            "bindm = SUPER, mouse:272, movewindow",
        )

    def test_4_resolve_watch_pid_walks_ancestors_to_quickshell(self) -> None:
        import io
        from unittest import mock
        from backend.editor.recorder_submap import resolve_watch_pid

        fake_proc = {
            "/proc/300/cmdline": b"sh\x00-c\x00python3\x00",
            "/proc/300/stat": "300 (sh) S 200 1 1 0 -1 0 0 0 0 0 0 0 0 0 20 0 1 0 0 0 0\n",
            "/proc/200/cmdline": b"/usr/bin/quickshell\x00-p\x00frontend/shell.qml\x00",
            "/proc/200/stat": "200 (quickshell) S 100 1 1 0 -1 0 0 0 0 0 0 0 0 0 20 0 1 0 0 0 0\n",
        }

        def fake_open(path, mode="r", **_kwargs):
            if path in fake_proc:
                data = fake_proc[path]
                return io.BytesIO(data) if "b" in mode else io.StringIO(data)
            raise FileNotFoundError(path)

        with mock.patch("backend.editor.recorder_submap.os.getppid", return_value=300):
            with mock.patch("builtins.open", side_effect=fake_open):
                self.assertEqual(resolve_watch_pid(), 200)


class TestPhase3b10ExecQuotingAndResizeDescribe(IsolatedTestCase):
    def test_1_exec_cmd_quoting_end_to_end_lua_and_roundtrip(self) -> None:
        import tempfile
        from backend.editor.codegen import encode_lua_string
        from backend.editor.dispatchers import _decode_lua_string, render_from_catalog

        cases = [
            ("plain", "kitty"),
            ("spaces", "firefox --new-window"),
            ("double_quotes", 'notify-send "hi"'),
            ("single_quotes", "sh -c 'echo hi'"),
            ("both_quotes", 'sh -c \'echo "a b"\''),
            ("backslash", "printf 'a\\nb'"),
            ("dollar_backtick", "echo $HOME `date`"),
            ("unicode", 'notify-send "café"'),
            ("trailing_space", "kitty "),
            ("already_wrapped", '"kitty"'),
        ]

        for label, cmd in cases:
            with self.subTest(label=label, cmd=cmd):
                encoded = encode_lua_string(cmd)
                self.assertEqual(_decode_lua_string(encoded), cmd)
                dsp, arg = render_from_catalog("exec_cmd", {"cmd": cmd}, language="lua")
                self.assertEqual(dsp, "exec_cmd")
                self.assertEqual(arg, encoded)

                with tempfile.TemporaryDirectory() as td:
                    cfg_dir = os.path.join(td, "hypr")
                    bak_dir = os.path.join(td, "backups")
                    sc_path = os.path.join(td, "hks", "descriptions.json")
                    os.makedirs(cfg_dir, exist_ok=True)
                    cfg_path = os.path.join(cfg_dir, "hyprland.lua")
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        f.write('hl.bind("SUPER + Q", hl.dsp.window.close())\n')

                    payload = json.dumps({"cmd": cmd})
                    proc = subprocess.run(
                        [
                            sys.executable, "-m", "backend.cli",
                            "edit", "add",
                            "--config-dir", cfg_dir,
                            "--entrypoint", cfg_path,
                            "--mods", "SUPER",
                            "--key", "F12",
                            "--dispatcher-id", "exec_cmd",
                            "--args-json", payload,
                            "--no-live",
                            "--apply",
                        ],
                        cwd=REPO_ROOT,
                        env={**os.environ, "HKS_BACKUP_DIR": bak_dir, "HKS_SIDECAR_PATH": sc_path},
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(proc.returncode, 0, f"{label}: {proc.stderr or proc.stdout}")
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    expected_line = f'hl.bind("SUPER + F12", hl.dsp.exec_cmd({encoded}))'
                    self.assertIn(expected_line, content)

        for bad in ["", "   ", "echo a\nb", "echo a\rb", "echo a\x00b"]:
            with self.subTest(bad=bad):
                if "\n" in bad or "\r" in bad or "\x00" in bad:
                    with self.assertRaises(ValueError):
                        encode_lua_string(bad)
                with self.assertRaises(ValueError):
                    render_from_catalog("exec_cmd", {"cmd": bad}, language="lua")

                with tempfile.TemporaryDirectory() as td:
                    cfg_dir = os.path.join(td, "hypr")
                    bak_dir = os.path.join(td, "backups")
                    sc_path = os.path.join(td, "hks", "descriptions.json")
                    os.makedirs(cfg_dir, exist_ok=True)
                    cfg_path = os.path.join(cfg_dir, "hyprland.lua")
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        f.write('hl.bind("SUPER + Q", hl.dsp.window.close())\n')

                    proc = subprocess.run(
                        [
                            sys.executable, "-m", "backend.cli",
                            "edit", "add",
                            "--config-dir", cfg_dir,
                            "--entrypoint", cfg_path,
                            "--mods", "SUPER",
                            "--key", "F12",
                            "--dispatcher-id", "exec_cmd",
                            "--args-json", json.dumps({"cmd": bad}),
                            "--no-live",
                        ],
                        cwd=REPO_ROOT,
                        env={**os.environ, "HKS_BACKUP_DIR": bak_dir, "HKS_SIDECAR_PATH": sc_path},
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(proc.returncode, 0)

    def test_2_exec_cmd_already_quoted_consistent_across_lua_and_hyprlang(self) -> None:
        import tempfile
        from backend.editor.dispatchers import _decode_lua_string, render_from_catalog

        lua_dsp, lua_arg = render_from_catalog("exec_cmd", {"cmd": '"kitty"'}, language="lua")
        self.assertEqual(lua_dsp, "exec_cmd")
        self.assertEqual(lua_arg, r'"\"kitty\""')
        self.assertEqual(_decode_lua_string(lua_arg), '"kitty"')

        hl_dsp, hl_arg = render_from_catalog("exec_cmd", {"cmd": '"kitty"'}, language="hyprlang")
        self.assertEqual(hl_dsp, "exec")
        self.assertEqual(hl_arg, '"kitty"')

        self.assertEqual(
            generate_lua_bind(["SUPER"], "F12", "exec_cmd", '"kitty"'),
            r'hl.bind("SUPER + F12", hl.dsp.exec_cmd("\"kitty\""))',
        )
        self.assertEqual(
            generate_hyprlang_bind(["SUPER"], "F12", "exec_cmd", '"kitty"'),
            'bind = SUPER, F12, exec, "kitty"',
        )

        with tempfile.TemporaryDirectory() as td:
            cfg_dir = os.path.join(td, "hypr")
            bak_dir = os.path.join(td, "backups")
            sc_path = os.path.join(td, "hks", "descriptions.json")
            os.makedirs(cfg_dir, exist_ok=True)
            hl_cfg = os.path.join(cfg_dir, "hyprland.conf")
            with open(hl_cfg, "w", encoding="utf-8") as f:
                f.write("bind = SUPER, Q, killactive\n")
            proc = subprocess.run(
                [
                    sys.executable, "-m", "backend.cli",
                    "edit", "add",
                    "--config-dir", cfg_dir,
                    "--entrypoint", hl_cfg,
                    "--mods", "SUPER",
                    "--key", "F12",
                    "--dispatcher-id", "exec_cmd",
                    "--args-json", json.dumps({"cmd": '"kitty"'}),
                    "--no-live",
                    "--dry-run",
                    "--json",
                ],
                cwd=REPO_ROOT,
                env={**os.environ, "HKS_BACKUP_DIR": bak_dir, "HKS_SIDECAR_PATH": sc_path},
                capture_output=True,
                text=True,
            )
            out = json.loads(proc.stdout)
            self.assertIn('bind = SUPER, F12, exec, "kitty"', out["diff"])
            self.assertEqual(out["expected_new_bind"]["args_raw"], '"kitty"')

    def test_3_untouched_dispatcher_preserved_byte_for_byte_on_shortcut_replace(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg_dir = os.path.join(td, "hypr")
            bak_dir = os.path.join(td, "backups")
            sc_path = os.path.join(td, "hks", "descriptions.json")
            os.makedirs(cfg_dir, exist_ok=True)
            cfg_path = os.path.join(cfg_dir, "hyprland.lua")
            orig_dsp = "hl.dsp.exec_cmd('sh -c \"echo hi\"')"
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write(f'hl.bind("SUPER + Return", {orig_dsp})\n')

            binds, _, _, _, _ = parse_lua_config(cfg_path, cfg_dir)
            bind_id = binds[0].id

            rep = subprocess.run(
                [
                    sys.executable, "-m", "backend.cli",
                    "edit", "replace",
                    "--config-dir", cfg_dir,
                    "--entrypoint", cfg_path,
                    "--id", bind_id,
                    "--mods", "SUPER",
                    "--key", "T",
                    "--preserve-dispatcher",
                    "--no-live",
                    "--apply",
                ],
                cwd=REPO_ROOT,
                env={**os.environ, "HKS_BACKUP_DIR": bak_dir, "HKS_SIDECAR_PATH": sc_path},
                capture_output=True,
                text=True,
            )
            self.assertEqual(rep.returncode, 0, rep.stderr or rep.stdout)
            with open(cfg_path, "r", encoding="utf-8") as f:
                self.assertIn(f'hl.bind("SUPER + T", {orig_dsp})', f.read())

    def test_4_derive_description_keyboard_vs_mouse_window_resize(self) -> None:
        from backend.describe.derive import derive_category, derive_description
        from backend.models.types import BindRecord, DispatcherInfo, default_flags

        def make_resize_bind(*, args=None, is_mouse: bool = False) -> BindRecord:
            flags = default_flags()
            flags["mouse"] = is_mouse
            return BindRecord(
                id="b_test",
                language="lua",
                bind_type="bindm" if is_mouse else "bind",
                declared_via="bindm" if is_mouse else "bind",
                modifiers=["SUPER"],
                modifiers_raw="SUPER",
                modmask=64,
                key="mouse:273" if is_mouse else "R",
                key_kind="mouse" if is_mouse else "keysym",
                keys_raw="SUPER + mouse:273" if is_mouse else "SUPER + R",
                flags=flags,
                flags_extra={},
                description=None,
                dispatcher=DispatcherInfo(
                    path="window.resize",
                    args=args or [],
                    arg_summary="",
                ),
                submap="",
                source_file="hyprland.lua",
                source_line=1,
                original_line="",
                original_line_number=1,
                generated=False,
                occurrence=0,
                occurrences_at_site=1,
                trace=[],
                parse_status="ok",
                args_raw="",
            )

        kb_num = make_resize_bind(args=[{"x": 20, "y": 0, "relative": True}], is_mouse=False)
        self.assertEqual(derive_description(kb_num), ("Resize window by 20, 0", False))
        self.assertEqual(derive_category(kb_num), "Windows")

        kb_plain = make_resize_bind(args=[], is_mouse=False)
        self.assertEqual(derive_description(kb_plain), ("Resize window", False))
        self.assertEqual(derive_category(kb_plain), "Windows")

        mouse_b = make_resize_bind(args=[], is_mouse=True)
        self.assertEqual(derive_description(mouse_b), ("Resize window with mouse", False))
        self.assertEqual(derive_category(mouse_b), "Mouse")
