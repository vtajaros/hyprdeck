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
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "H", "focus", '{ direction = "left" }'), "bind = SUPER, H, movefocus, left")
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "2", "focus", '{ workspace = 2 }'), "bind = SUPER, 2, workspace, 2")
        with self.assertRaisesRegex(ValueError, "not supported for Hyprlang"):
            generate_hyprlang_bind(["SUPER"], "H", "focus", '{ monitor = "DP-1" }')

    def test_window_move_conditional(self) -> None:
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "H", "window.move", '{ direction = "right" }'), "bind = SUPER, H, movewindow, right")
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "2", "window.move", '{ workspace = 2 }'), "bind = SUPER, 2, movetoworkspace, 2")
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "2", "window.move", '{ workspace = 2, silent = true }'), "bind = SUPER, 2, movetoworkspacesilent, 2")
        with self.assertRaisesRegex(ValueError, "not supported for Hyprlang"):
            generate_hyprlang_bind(["SUPER"], "H", "window.move", '{ monitor = "DP-1" }')

    def test_workspace_and_movetoworkspace_mapped(self) -> None:
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "1", "workspace", "1"), "bind = SUPER, 1, workspace, 1")
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "1", "movetoworkspace", '{ workspace = "1", silent = true }'), "bind = SUPER, 1, movetoworkspacesilent, 1")

    def test_window_resize_mapped_and_refused(self) -> None:
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "R", "window.resize", '{ dx = 20, dy = -10 }'), "bind = SUPER, R, resizeactive, 20 -10")
        with self.assertRaisesRegex(ValueError, "not supported for Hyprlang"):
            generate_hyprlang_bind(["SUPER"], "R", "window.resize", '{ percent = 10 }')

    def test_window_pin_mapped(self) -> None:
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "P", "window.pin", None), "bind = SUPER, P, pin")

    def test_layout_conditional(self) -> None:
        self.assertEqual(generate_hyprlang_bind(["SUPER"], "J", "layout", "togglesplit"), "bind = SUPER, J, togglesplit")
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
