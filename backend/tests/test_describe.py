"""Unit tests for Phase 2a human descriptions and category derivation."""

from __future__ import annotations

import os
import tempfile
import unittest

from backend.parser.hyprlang_parser import parse_hyprlang_config
from backend.parser.lua_normalizer import parse_lua_config

FIXTURES_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "fixtures"))
LUA_FIXTURE_DIR = os.path.join(FIXTURES_ROOT, "lua_user_like")
HYPRLANG_FIXTURE_DIR = os.path.join(FIXTURES_ROOT, "hyprlang_user_like")


def _find_bind(binds, modifiers: list[str], key: str, dsp_substr: str | None = None):
    mod_tuple = tuple(modifiers)
    key_lower = key.lower()
    for b in binds:
        if tuple(b.modifiers) == mod_tuple and b.key.lower() == key_lower:
            if dsp_substr is None or dsp_substr in b.dispatcher.path:
                return b
    raise AssertionError(f"Bind not found: modifiers={modifiers}, key={key}, dsp={dsp_substr}")


class TestDescribeDerivation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lua_binds, _, _, _, _ = parse_lua_config(
            entrypoint=os.path.join(LUA_FIXTURE_DIR, "hyprland.lua"),
            config_dir=LUA_FIXTURE_DIR,
        )
        cls.conf_binds, _, _, _, _, _ = parse_hyprlang_config(
            entrypoint=os.path.join(HYPRLANG_FIXTURE_DIR, "hyprland.conf"),
            home_dir=HYPRLANG_FIXTURE_DIR,
        )

    def test_existing_fixtures_and_lua_hyprlang_parity(self) -> None:
        # Table-driven checks on existing lua_user_like fixture
        lua_cases = [
            (["SUPER"], "C", None, "Close window", "Windows"),
            (["SUPER"], "Left", None, "Move window left", "Windows"),
            (["SUPER"], "1", None, "Switch to workspace 1", "Workspaces"),
            (["SUPER"], "0", None, "Switch to workspace 10", "Workspaces"),
            (["SUPER"], "bracketright", None, "Switch to next workspace", "Workspaces"),
            (["SUPER"], "bracketleft", None, "Switch to previous workspace", "Workspaces"),
            (["ALT", "SHIFT"], "Tab", None, "Cycle to previous window", "Windows"),
            (["ALT"], "Tab", "cycle_next", "Cycle to next window", "Windows"),
            (["ALT"], "Tab", "bring_to_top", "Bring window to top", "Windows"),
            ([], "XF86AudioMute", None, "Run: quickshell ipc call osd toggleMute", "Media & Hardware"),
            (["SUPER", "CTRL"], "L", None, "Launch hyprlock", "System"),
            (["CTRL", "ALT"], "Delete", None, "Launch wlogout", "System"),
            (["SUPER"], "Return", None, "Launch kitty", "Apps"),
            (["SUPER"], "mouse:272", None, "Drag window with mouse", "Mouse"),
            (["SUPER"], "mouse:273", None, "Resize window with mouse", "Mouse"),
            (["SUPER"], "M", None, "Maximize window", "Windows"),
            (["SUPER"], "J", None, "Toggle split direction", "Windows"),
        ]
        for mods, key, dsp_sub, exp_desc, exp_cat in lua_cases:
            with self.subTest(lang="lua", mods=mods, key=key, dsp=dsp_sub):
                b = _find_bind(self.lua_binds, mods, key, dsp_sub)
                self.assertEqual(b.description_effective.text, exp_desc)
                self.assertEqual(b.description_effective.source, "derived")
                self.assertFalse(b.description_effective.generic)
                self.assertEqual(b.category, exp_cat)
                self.assertEqual(b.category_source, "derived")

        # Parity assertions for every bind in hyprlang_user_like that also exists in lua_user_like
        parity_combos = [
            (["SUPER"], "Return", None),
            (["SUPER", "SHIFT"], "Return", None),
            (["SUPER"], "Space", None),
            (["SUPER"], "C", None),
            (["SUPER"], "M", None),
            (["SUPER"], "J", None),
            (["SUPER", "SHIFT"], "S", None),
            (["SUPER"], "N", None),
            ([], "XF86AudioRaiseVolume", None),
            ([], "XF86AudioLowerVolume", None),
            ([], "XF86AudioMute", None),
            (["SUPER"], "mouse:272", None),
            (["SUPER"], "mouse:273", None),
        ]
        for mods, key, dsp_sub in parity_combos:
            with self.subTest(parity_mods=mods, parity_key=key):
                lb = _find_bind(self.lua_binds, mods, key, dsp_sub)
                cb = _find_bind(self.conf_binds, mods, key, dsp_sub)
                self.assertEqual(lb.description_effective.text, cb.description_effective.text)
                self.assertEqual(lb.category, cb.category)

    def test_b7_exact_table_driven_parity_suite(self) -> None:
        """Verify the exact 12 B7 assertions across both Lua and Hyprlang."""
        lua_src = """
hl.bind("SUPER + X", hl.dsp.window.close())
hl.bind("SUPER + left", hl.dsp.window.move({ direction = "left" }))
hl.bind("SUPER + 1", hl.dsp.workspace.focus(1))
hl.bind("SUPER + 0", hl.dsp.workspace.focus(10))
hl.bind("SUPER + CTRL + right", hl.dsp.workspace.focus("e+1"))
hl.bind("ALT + Escape", hl.dsp.window.move({ workspace = "special:minimized" }))
hl.bind("ALT + SHIFT + Tab", hl.dsp.window.cycle_next({ prev = true }))
hl.bind("XF86AudioMute", hl.dsp.exec_cmd("quickshell ipc call osd toggleMute"), { locked = true })
hl.bind("XF86ScreenSaver", hl.dsp.exec_cmd("hyprlock"), { locked = true })
hl.bind("SUPER + SHIFT + P", hl.dsp.exec_cmd("wlogout"))
hl.bind("SUPER + Q", hl.dsp.exec_cmd("firefox"))
hl.bind("SUPER + mouse:272", hl.dsp.window.drag(), { mouse = true })
"""
        conf_src = """
bind = SUPER, X, killactive,
bind = SUPER, left, movewindow, l
bind = SUPER, 1, workspace, 1
bind = SUPER, 0, workspace, 10
bind = SUPER CTRL, right, workspace, e+1
bind = ALT, Escape, movetoworkspace, special:minimized
bind = ALT SHIFT, Tab, cyclenext, prev
bindl = , XF86AudioMute, exec, quickshell ipc call osd toggleMute
bindl = , XF86ScreenSaver, exec, hyprlock
bind = SUPER SHIFT, P, exec, wlogout
bind = SUPER, Q, exec, firefox
bindm = SUPER, mouse:272, movewindow
"""
        expected_table = [
            (["SUPER"], "X", "Close window", "Windows"),
            (["SUPER"], "left", "Move window left", "Windows"),
            (["SUPER"], "1", "Switch to workspace 1", "Workspaces"),
            (["SUPER"], "0", "Switch to workspace 10", "Workspaces"),
            (["SUPER", "CTRL"], "right", "Switch to next workspace", "Workspaces"),
            (["ALT"], "Escape", "Minimize window", "Windows"),
            (["ALT", "SHIFT"], "Tab", "Cycle to previous window", "Windows"),
            ([], "XF86AudioMute", "Run: quickshell ipc call osd toggleMute", "Media & Hardware"),
            ([], "XF86ScreenSaver", "Launch hyprlock", "System"),
            (["SUPER", "SHIFT"], "P", "Launch wlogout", "System"),
            (["SUPER"], "Q", "Launch firefox", "Apps"),
            (["SUPER"], "mouse:272", "Drag window with mouse", "Mouse"),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            lua_file = os.path.join(tmpdir, "hyprland.lua")
            conf_file = os.path.join(tmpdir, "hyprland.conf")
            with open(lua_file, "w", encoding="utf-8") as f:
                f.write(lua_src)
            with open(conf_file, "w", encoding="utf-8") as f:
                f.write(conf_src)

            l_binds, _, _, _, _ = parse_lua_config(entrypoint=lua_file, config_dir=tmpdir)
            c_binds, _, _, _, _, _ = parse_hyprlang_config(entrypoint=conf_file, home_dir=tmpdir)

            for mods, key, exp_desc, exp_cat in expected_table:
                with self.subTest(mods=mods, key=key):
                    lb = _find_bind(l_binds, mods, key)
                    cb = _find_bind(c_binds, mods, key)
                    self.assertEqual(lb.description_effective.text, exp_desc)
                    self.assertEqual(lb.category, exp_cat)
                    self.assertEqual(cb.description_effective.text, exp_desc)
                    self.assertEqual(cb.category, exp_cat)
                    self.assertFalse(lb.description_effective.generic)
                    self.assertFalse(cb.description_effective.generic)

    def test_additional_derivation_rules_and_generic_fallback(self) -> None:
        long_cmd = "python3 -c 'print(\"a very long command string that exceeds sixty characters easily\")'"
        lua_src = f"""
hl.bind("SUPER + F", hl.dsp.window.fullscreen({{ mode = "fullscreen" }}))
hl.bind("SUPER + V", hl.dsp.window.float())
hl.bind("SUPER + P", hl.dsp.window.pseudo())
hl.bind("SUPER + K", hl.dsp.layout("master"))
hl.bind("SUPER + S", hl.dsp.workspace.toggle_special("scratchpad"))
hl.bind("SUPER + SHIFT + S", hl.dsp.window.move({{ workspace = "special:scratchpad" }}))
hl.bind("SUPER + SHIFT + bracketright", hl.dsp.window.move({{ workspace = "e+1" }}))
hl.bind("SUPER + SHIFT + bracketleft", hl.dsp.window.move({{ workspace = "e-1" }}))
hl.bind("SUPER + L", hl.dsp.exec_cmd({long_cmd!r}))
hl.bind("SUPER + D", hl.dsp.exec_cmd("kitty"), {{ description = "Custom Terminal Description" }})
hl.bind("SUPER + U", hl.dsp.custom.unknown_action("arg1"))
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            lua_file = os.path.join(tmpdir, "hyprland.lua")
            with open(lua_file, "w", encoding="utf-8") as f:
                f.write(lua_src)
            binds, _, _, _, _ = parse_lua_config(entrypoint=lua_file, config_dir=tmpdir)

            self.assertEqual(_find_bind(binds, ["SUPER"], "F").description_effective.text, "Toggle fullscreen")
            self.assertEqual(_find_bind(binds, ["SUPER"], "V").description_effective.text, "Toggle floating")
            self.assertEqual(_find_bind(binds, ["SUPER"], "P").description_effective.text, "Toggle pseudo-tiling")
            self.assertEqual(_find_bind(binds, ["SUPER"], "K").description_effective.text, "Layout: master")

            sp_toggle = _find_bind(binds, ["SUPER"], "S")
            self.assertEqual(sp_toggle.description_effective.text, "Toggle special workspace scratchpad")
            self.assertEqual(sp_toggle.category, "Workspaces")

            sp_move = _find_bind(binds, ["SUPER", "SHIFT"], "S")
            self.assertEqual(sp_move.description_effective.text, "Send window to special workspace scratchpad")
            self.assertEqual(sp_move.category, "Windows")

            mv_next = _find_bind(binds, ["SUPER", "SHIFT"], "bracketright")
            self.assertEqual(mv_next.description_effective.text, "Move window to next workspace")
            self.assertEqual(mv_next.category, "Workspaces")

            mv_prev = _find_bind(binds, ["SUPER", "SHIFT"], "bracketleft")
            self.assertEqual(mv_prev.description_effective.text, "Move window to previous workspace")
            self.assertEqual(mv_prev.category, "Workspaces")

            long_b = _find_bind(binds, ["SUPER"], "L")
            self.assertEqual(len(long_b.description_effective.text), 60)
            self.assertTrue(long_b.description_effective.text.startswith("Run: "))
            self.assertTrue(long_b.description_effective.text.endswith("..."))

            cfg_b = _find_bind(binds, ["SUPER"], "D")
            self.assertEqual(cfg_b.description, "Custom Terminal Description")
            self.assertEqual(cfg_b.description_effective.text, "Custom Terminal Description")
            self.assertEqual(cfg_b.description_effective.source, "config")
            self.assertFalse(cfg_b.description_effective.generic)

            gen_b = _find_bind(binds, ["SUPER"], "U")
            self.assertEqual(gen_b.description_effective.text, "custom.unknown_action: arg1")
            self.assertEqual(gen_b.description_effective.source, "derived")
            self.assertTrue(gen_b.description_effective.generic)
            self.assertEqual(gen_b.category, "Other")


if __name__ == "__main__":
    unittest.main()
