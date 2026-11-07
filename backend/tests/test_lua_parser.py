"""Unit tests for the Lua parser and user-like fixture."""

from __future__ import annotations

import os
import unittest

from backend.discovery import discover_config
from backend.parser.lua_normalizer import parse_lua_config
from backend.serializer import make_scan_document
from backend.validation import assert_valid_scan_dict

FIXTURE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "fixtures", "lua_user_like")
)


class TestLuaUserLikeFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.discovery = discover_config(config_dir=FIXTURE_DIR, no_live=True)
        (
            cls.binds,
            cls.files,
            cls.diagnostics,
            cls.stats,
            cls.complete,
        ) = parse_lua_config(
            entrypoint=cls.discovery.environment.entrypoint,
            config_dir=cls.discovery.environment.config_dir,
        )
        cls.doc = make_scan_document(
            environment=cls.discovery.environment,
            files=cls.files,
            binds=cls.binds,
            unbinds=[],
            diagnostics=[*cls.discovery.diagnostics, *cls.diagnostics],
            stats=cls.stats,
            complete=cls.complete,
        )

    def test_schema_and_completeness(self) -> None:
        self.assertTrue(self.complete)
        self.assertEqual(self.diagnostics, [])
        assert_valid_scan_dict(self.doc.to_dict())

    def test_loaded_files_includes_theme_colors(self) -> None:
        paths = [os.path.basename(f.path) for f in self.files]
        self.assertEqual(paths, ["hyprland.lua", "theme-colors.lua"])
        self.assertEqual(self.files[0].role, "entrypoint")
        self.assertEqual(self.files[1].role, "loaded")

    def test_exact_bind_and_call_site_counts(self) -> None:
        # 33 distinct call sites expanding to 68 total binds (46 generated, 22 static)
        self.assertEqual(len(self.binds), 68)
        self.assertEqual(self.stats.total_binds, 68)
        self.assertEqual(self.stats.generated_binds, 46)
        distinct_sites = {(b.source_file, b.source_line) for b in self.binds}
        self.assertEqual(len(distinct_sites), 33)

    def test_mouse_binds_and_source_lines(self) -> None:
        mouse_binds = [b for b in self.binds if b.flags["mouse"]]
        self.assertEqual(len(mouse_binds), 2)
        self.assertEqual(self.stats.flag_counts["mouse"], 2)

        for mb in mouse_binds:
            self.assertEqual(mb.bind_type, "bindm")
            self.assertEqual(mb.declared_via, "bindm")
            self.assertEqual(mb.key_kind, "mouse_button")
            self.assertTrue(mb.original_line.strip().startswith("hl.bindm("))
            self.assertEqual(mb.source_line, mb.original_line_number)

    def test_loop_binds_source_line_and_occurrences(self) -> None:
        ws_loop_binds = [
            b
            for b in self.binds
            if b.generated and b.occurrences_at_site == 10
        ]
        self.assertEqual(len(ws_loop_binds), 30)
        for b in ws_loop_binds:
            # Must point to the hl.bind(...) call inside the loop, not the 'for' header
            self.assertIn("hl.bind(", b.original_line)
            self.assertNotIn("for i = 1, 10", b.original_line)
            self.assertTrue(0 <= b.occurrence < 10)

        focus_loop_binds = [
            b
            for b in self.binds
            if b.dispatcher.path == "window.focus"
        ]
        self.assertEqual(len(focus_loop_binds), 8)
        for b in focus_loop_binds:
            self.assertTrue(b.generated)
            self.assertEqual(b.occurrences_at_site, 2)
            self.assertIn("hl.bind(", b.original_line)

    def test_modmasks_verified(self) -> None:
        by_combo = {
            (" + ".join([*b.modifiers, b.key]) if b.modifiers else b.key): b
            for b in self.binds
        }
        # SUPER + SHIFT = 65
        self.assertEqual(by_combo["SUPER + SHIFT + Return"].modmask, 65)
        # SUPER + CTRL = 68
        self.assertEqual(by_combo["SUPER + CTRL + L"].modmask, 68)
        # SUPER + ALT = 72
        self.assertEqual(by_combo["SUPER + ALT + Left"].modmask, 72)
        # CTRL + ALT = 12
        self.assertEqual(by_combo["CTRL + ALT + Delete"].modmask, 12)
        # ALT + SHIFT = 9
        self.assertEqual(by_combo["ALT + SHIFT + Tab"].modmask, 9)

    def test_alt_tab_pair_both_preserved(self) -> None:
        alt_tab = [
            b
            for b in self.binds
            if b.modifiers == ["ALT"] and b.key == "Tab"
        ]
        self.assertEqual(len(alt_tab), 2)
        paths = [b.dispatcher.path for b in alt_tab]
        self.assertEqual(paths, ["window.cycle_next", "window.bring_to_top"])
        self.assertNotEqual(alt_tab[0].id, alt_tab[1].id)

    def test_special_strings_and_flags(self) -> None:
        slurp_bind = next(
            b for b in self.binds if b.key == "S" and b.modmask == 65
        )
        self.assertEqual(
            slurp_bind.dispatcher.arg_summary,
            'grim -g "$(slurp)" - | wl-copy',
        )

        pipe_bind = next(
            b for b in self.binds if b.key == "N" and b.modmask == 64
        )
        self.assertEqual(
            pipe_bind.dispatcher.arg_summary,
            "dunstctl history-pop || dunstctl close",
        )

        vol_up = next(
            b for b in self.binds if b.key == "XF86AudioRaiseVolume"
        )
        self.assertTrue(vol_up.flags["locked"])
        self.assertTrue(vol_up.flags["repeating"])
        self.assertEqual(vol_up.bind_type, "bindel")

        vol_mute = next(
            b for b in self.binds if b.key == "XF86AudioMute"
        )
        self.assertTrue(vol_mute.flags["locked"])
        self.assertFalse(vol_mute.flags["repeating"])
        self.assertEqual(vol_mute.bind_type, "bindl")

        wheel_down = next(
            b for b in self.binds if b.key == "mouse_down"
        )
        self.assertEqual(wheel_down.key_kind, "mouse_wheel")


if __name__ == "__main__":
    unittest.main()
