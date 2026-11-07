"""Sandbox security, resource limit, and error-recovery tests for HKS Lua recorder."""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest

from backend.discovery import discover_config
from backend.parser.lua_normalizer import parse_lua_config
from backend.serializer import make_scan_document, serialize_scan_document
from backend.validation import assert_valid_scan_dict


class TestLuaSandbox(unittest.TestCase):
    def _run_snippet(self, lua_code: str) -> tuple:
        with tempfile.TemporaryDirectory() as cfg_dir:
            entry = os.path.join(cfg_dir, "hyprland.lua")
            with open(entry, "w", encoding="utf-8") as f:
                f.write(lua_code)
            disc = discover_config(config_dir=cfg_dir, no_live=True)
            binds, files, diags, stats, complete = parse_lua_config(
                entrypoint=entry,
                config_dir=cfg_dir,
            )
            doc = make_scan_document(
                environment=disc.environment,
                files=files,
                binds=binds,
                unbinds=[],
                diagnostics=[*disc.diagnostics, *diags],
                stats=stats,
                complete=complete,
            )
            assert_valid_scan_dict(doc.to_dict())
            return binds, diags, complete, doc

    def test_os_execute_blocked_without_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as outside_dir:
            marker = os.path.join(outside_dir, "pwned_exec.txt")
            code = f"""
hl.bind("SUPER + 1", hl.dsp.exec_cmd("kitty"))
os.execute("touch {marker}")
hl.bind("SUPER + 2", hl.dsp.exec_cmd("firefox"))
"""
            binds, diags, complete, _ = self._run_snippet(code)
            self.assertFalse(os.path.exists(marker))
            self.assertFalse(complete)
            self.assertEqual(len(binds), 2)
            codes = [d.code for d in diags]
            self.assertIn("sandbox_denied", codes)

    def test_io_popen_blocked_without_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as outside_dir:
            marker = os.path.join(outside_dir, "pwned_popen.txt")
            code = f"""
hl.bind("SUPER + 1", hl.dsp.exec_cmd("kitty"))
local p = io.popen("touch {marker}")
hl.bind("SUPER + 2", hl.dsp.exec_cmd("firefox"))
"""
            binds, diags, complete, _ = self._run_snippet(code)
            self.assertFalse(os.path.exists(marker))
            self.assertFalse(complete)
            self.assertEqual(len(binds), 2)
            self.assertIn("sandbox_denied", [d.code for d in diags])

    def test_os_remove_blocked_without_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as outside_dir:
            target = os.path.join(outside_dir, "keep_me.txt")
            with open(target, "w", encoding="utf-8") as f:
                f.write("important data")
            code = f"""
hl.bind("SUPER + 1", hl.dsp.exec_cmd("kitty"))
os.remove("{target}")
"""
            binds, diags, complete, _ = self._run_snippet(code)
            self.assertTrue(os.path.exists(target))
            self.assertFalse(complete)
            self.assertEqual(len(binds), 1)
            self.assertIn("sandbox_denied", [d.code for d in diags])

    def test_io_open_write_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as outside_dir:
            marker = os.path.join(outside_dir, "write_attempt.txt")
            code = f"""
hl.bind("SUPER + A", hl.dsp.exec_cmd("kitty"))
local f, err = io.open("{marker}", "w")
local f2, err2 = io.open("inside.txt", "w")
"""
            binds, diags, complete, _ = self._run_snippet(code)
            self.assertFalse(os.path.exists(marker))
            self.assertFalse(complete)
            self.assertEqual(len(binds), 1)
            self.assertIn("sandbox_denied", [d.code for d in diags])

    def test_io_open_etc_passwd_blocked(self) -> None:
        code = """
hl.bind("SUPER + A", hl.dsp.exec_cmd("kitty"))
local f, err = io.open("/etc/passwd", "r")
assert(f == nil)
hl.bind("SUPER + B", hl.dsp.exec_cmd("thunar"))
"""
        binds, diags, complete, _ = self._run_snippet(code)
        self.assertFalse(complete)
        self.assertEqual(len(binds), 2)
        self.assertIn("sandbox_denied", [d.code for d in diags])

    def test_require_outside_config_dir_blocked(self) -> None:
        code = """
hl.bind("SUPER + A", hl.dsp.exec_cmd("kitty"))
require("../outside_module")
hl.bind("SUPER + B", hl.dsp.exec_cmd("never_reached"))
"""
        binds, diags, complete, _ = self._run_snippet(code)
        self.assertFalse(complete)
        self.assertEqual(len(binds), 1)
        self.assertIn("sandbox_denied", [d.code for d in diags])

    def test_infinite_loop_hits_instruction_limit_and_returns_partial_binds(self) -> None:
        code = """
hl.bind("SUPER + 1", hl.dsp.exec_cmd("kitty"))
hl.bind("SUPER + 2", hl.dsp.exec_cmd("firefox"))
while true do
end
hl.bind("SUPER + 3", hl.dsp.exec_cmd("unreachable"))
"""
        t0 = time.monotonic()
        binds, diags, complete, _ = self._run_snippet(code)
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 10.0)
        self.assertFalse(complete)
        self.assertEqual(len(binds), 2)
        self.assertIn("instruction_limit", [d.code for d in diags])

    def test_string_rep_memory_bomb_handled_gracefully(self) -> None:
        code = """
hl.bind("SUPER + 1", hl.dsp.exec_cmd("kitty"))
hl.bind("SUPER + 2", hl.dsp.exec_cmd("firefox"))
local huge = string.rep("A", 1024 * 1024 * 1024)
hl.bind("SUPER + 3", hl.dsp.exec_cmd("unreachable"))
"""
        t0 = time.monotonic()
        binds, diags, complete, _ = self._run_snippet(code)
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 10.0)
        self.assertFalse(complete)
        self.assertEqual(len(binds), 2)
        codes = [d.code for d in diags]
        self.assertTrue(
            "config_runtime_error" in codes or "recorder_failed" in codes
        )

    def test_error_after_3_binds_preserves_partial_binds(self) -> None:
        code = """
hl.bind("SUPER + 1", hl.dsp.exec_cmd("one"))
hl.bind("SUPER + 2", hl.dsp.exec_cmd("two"))
hl.bind("SUPER + 3", hl.dsp.exec_cmd("three"))
error("intentional config failure on line 5")
hl.bind("SUPER + 4", hl.dsp.exec_cmd("four"))
"""
        binds, diags, complete, _ = self._run_snippet(code)
        self.assertFalse(complete)
        self.assertEqual(len(binds), 3)
        self.assertEqual([b.key for b in binds], ["1", "2", "3"])
        err_diags = [d for d in diags if d.code == "config_runtime_error"]
        self.assertEqual(len(err_diags), 1)
        self.assertIn("intentional config failure", err_diags[0].message)

    def test_lua_callback_unknown_api_and_partial_modifiers(self) -> None:
        code = """
hl.future_hypr_api("arg1")
hl.bind("SUPER + K", function()
    os.execute("touch /tmp/never_called")
end)
hl.bind("HYPER + X", hl.dsp.exec_cmd("kitty"))
hl.bind("SUPER + ", hl.dsp.exec_cmd("kitty"))
hl.bind("SUPER + Z", hl.dsp.submap("resize"), { custom_opt = 42, description = "Enter resize" })
"""
        binds, diags, complete, doc = self._run_snippet(code)
        self.assertTrue(complete)
        self.assertEqual(len(binds), 4)
        # 1. Lua callback bind is recorded without calling the callback
        self.assertEqual(binds[0].dispatcher.path, "<lua_callback>")
        self.assertIsNotNone(binds[0].dispatcher.callback_line)
        self.assertEqual(binds[0].parse_status, "ok")
        # 2. Unknown modifier => partial
        self.assertEqual(binds[1].parse_status, "partial")
        # 3. Trailing '+' => partial
        self.assertEqual(binds[2].parse_status, "partial")
        # 4. Description and flags_extra
        self.assertEqual(binds[3].description, "Enter resize")
        self.assertEqual(binds[3].flags_extra, {"custom_opt": 42})
        self.assertEqual(binds[3].bind_type, "bindd")

        codes = {d.code for d in diags}
        self.assertIn("unknown_api", codes)
        self.assertIn("unknown_modifier", codes)
        self.assertIn("invalid_key_combo", codes)
        self.assertIn("lua_submap_unsupported", codes)
        self.assertIn("unknown_bind_opt", codes)

        raw_json = serialize_scan_document(doc)
        parsed = json.loads(raw_json)
        assert_valid_scan_dict(parsed)


if __name__ == "__main__":
    unittest.main()
