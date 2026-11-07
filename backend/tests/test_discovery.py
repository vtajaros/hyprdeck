"""Unit tests for configuration discovery and entrypoint selection."""

from __future__ import annotations

import os
import tempfile
import unittest

from backend.discovery import (
    DiscoveryError,
    discover_config,
    resolve_default_config_dir,
)


class TestDiscovery(unittest.TestCase):
    def test_xdg_and_home_default_dir_resolution(self) -> None:
        env1 = {"XDG_CONFIG_HOME": "/tmp/custom_xdg", "HOME": "/tmp/custom_home"}
        self.assertEqual(resolve_default_config_dir(env1), "/tmp/custom_xdg/hypr")

        env2 = {"HOME": "/tmp/custom_home"}
        self.assertEqual(resolve_default_config_dir(env2), "/tmp/custom_home/.config/hypr")

    def test_both_present_selects_lua_and_shadows_conf(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lua_path = os.path.join(tmpdir, "hyprland.lua")
            conf_path = os.path.join(tmpdir, "hyprland.conf")
            bak1 = os.path.join(tmpdir, "hyprland.lua.bak_20261104")
            bak2 = os.path.join(tmpdir, "hyprland.conf.bak2")
            bak3 = os.path.join(tmpdir, "hyprland.lua.pre-reload.bak")

            with open(lua_path, "w", encoding="utf-8") as f:
                f.write("-- lua entrypoint\nhl.bind('SUPER + Q', hl.dsp.exec_cmd('kitty'))\n")
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write("# conf entrypoint\nbind = SUPER, Q, exec, kitty\n")
            for b in (bak1, bak2, bak3):
                with open(b, "w", encoding="utf-8") as f:
                    f.write("corrupted backup that must never be read\n")
                os.chmod(b, 0o000)

            try:
                res = discover_config(config_dir=tmpdir, no_live=True)
                self.assertEqual(res.environment.language, "lua")
                self.assertEqual(res.environment.entrypoint, lua_path)
                self.assertEqual(res.environment.detected_by, "file-precedence")
                self.assertEqual(len(res.environment.shadowed), 1)
                self.assertEqual(res.environment.shadowed[0].path, conf_path)
                self.assertIn("precedence", res.environment.shadowed[0].reason)
                self.assertEqual(res.entrypoint_record.path, lua_path)
                self.assertEqual(res.entrypoint_record.role, "entrypoint")
                self.assertEqual(res.entrypoint_record.line_count, 2)
            finally:
                for b in (bak1, bak2, bak3):
                    os.chmod(b, 0o600)

    def test_only_conf_selects_hyprlang(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "hyprland.conf")
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write("bind = SUPER, Return, exec, kitty\n")

            res = discover_config(config_dir=tmpdir, no_live=True)
            self.assertEqual(res.environment.language, "hyprlang")
            self.assertEqual(res.environment.entrypoint, conf_path)
            self.assertEqual(res.environment.shadowed, [])
            self.assertEqual(res.entrypoint_record.line_count, 1)

    def test_neither_present_raises_discovery_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bak = os.path.join(tmpdir, "hyprland.lua.bak_20261106")
            with open(bak, "w", encoding="utf-8") as f:
                f.write("-- backup only\n")
            with self.assertRaises(DiscoveryError):
                discover_config(config_dir=tmpdir, no_live=True)

    def test_live_hyprctl_agreement_and_mismatch_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lua_path = os.path.join(tmpdir, "hyprland.lua")
            with open(lua_path, "w", encoding="utf-8") as f:
                f.write("-- lua\n")

            # Live agrees with Lua
            res_agree = discover_config(
                config_dir=tmpdir,
                no_live=True,
                live_binds_override=[{"dispatcher": "HL.Dispatcher(exec_cmd)", "key": "Q"}],
            )
            self.assertEqual(res_agree.environment.detected_by, "live-hyprctl")
            self.assertEqual(res_agree.diagnostics, [])

            # Live disagrees (reports hyprlang dispatcher) - auto entrypoint
            res_mismatch = discover_config(
                config_dir=tmpdir,
                no_live=True,
                live_binds_override=[{"dispatcher": "exec", "key": "Q"}],
            )
            self.assertEqual(res_mismatch.environment.detected_by, "file-precedence")
            self.assertEqual(res_mismatch.environment.entrypoint_source, "auto")
            self.assertEqual(len(res_mismatch.diagnostics), 1)
            self.assertEqual(res_mismatch.diagnostics[0].code, "entrypoint_live_mismatch")
            self.assertEqual(res_mismatch.diagnostics[0].level, "warning")

            # Explicit entrypoint with live disagreement => no warning, entrypoint_source == "explicit"
            res_explicit = discover_config(
                entrypoint=lua_path,
                no_live=True,
                live_binds_override=[{"dispatcher": "exec", "key": "Q"}],
            )
            self.assertEqual(res_explicit.environment.detected_by, "file-precedence")
            self.assertEqual(res_explicit.environment.entrypoint_source, "explicit")
            self.assertEqual(res_explicit.diagnostics, [])

            # Explicit via config_dir with explicit file => no warning, entrypoint_source == "explicit"
            res_explicit_file = discover_config(
                config_dir=lua_path,
                no_live=True,
                live_binds_override=[{"dispatcher": "exec", "key": "Q"}],
            )
            self.assertEqual(res_explicit_file.environment.detected_by, "file-precedence")
            self.assertEqual(res_explicit_file.environment.entrypoint_source, "explicit")
            self.assertEqual(res_explicit_file.diagnostics, [])


if __name__ == "__main__":
    unittest.main()
