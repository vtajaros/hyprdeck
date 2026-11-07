"""Unit tests for the Hyprlang (.conf) front-end parser."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from backend.discovery import discover_config
from backend.parser import parse_hyprlang_config
from backend.serializer import make_scan_document
from backend.validation import assert_valid_scan_dict

FIXTURE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "fixtures", "hyprlang_user_like")
)


class TestHyprlangParser(unittest.TestCase):
    def test_user_like_fixture_with_home_override(self) -> None:
        with tempfile.TemporaryDirectory() as fake_home:
            hypr_dir = os.path.join(fake_home, ".config", "hypr")
            os.makedirs(hypr_dir, exist_ok=True)
            shutil.copy2(
                os.path.join(FIXTURE_DIR, "hyprland.conf"),
                os.path.join(hypr_dir, "hyprland.conf"),
            )
            shutil.copy2(
                os.path.join(FIXTURE_DIR, "theme-colors.conf"),
                os.path.join(hypr_dir, "theme-colors.conf"),
            )

            disc = discover_config(config_dir=hypr_dir, no_live=True)
            self.assertEqual(disc.environment.language, "hyprlang")

            binds, unbinds, files, diags, stats, complete = parse_hyprlang_config(
                entrypoint=disc.environment.entrypoint,
                home_dir=fake_home,
            )
            self.assertTrue(complete)
            self.assertEqual(diags, [])
            self.assertEqual(unbinds, [])
            self.assertEqual(len(binds), 16)
            self.assertEqual(
                [os.path.basename(f.path) for f in files],
                ["hyprland.conf", "theme-colors.conf"],
            )

            doc = make_scan_document(
                environment=disc.environment,
                files=files,
                binds=binds,
                unbinds=unbinds,
                diagnostics=diags,
                stats=stats,
                complete=complete,
            )
            assert_valid_scan_dict(doc.to_dict())

            # Variable expansion & longest-name-first ($terminal vs $terminalAlt)
            self.assertEqual(binds[0].dispatcher.arg_summary, "kitty")
            self.assertEqual(binds[0].args_raw, "$terminal")
            self.assertEqual(binds[1].dispatcher.arg_summary, "alacritty")
            self.assertEqual(binds[1].args_raw, "$terminalAlt")
            self.assertEqual(binds[2].dispatcher.arg_summary, "wofi --show drun")

            # "killactive," empty args
            self.assertEqual(binds[3].dispatcher.path, "killactive")
            self.assertEqual(binds[3].dispatcher.args, [])
            self.assertEqual(binds[3].dispatcher.arg_summary, "")

            # "$(slurp)" untouched and ", Print" empty modifiers
            slurp_super = binds[6]
            self.assertEqual(slurp_super.modmask, 65)
            self.assertEqual(
                slurp_super.dispatcher.arg_summary,
                'grim -g "$(slurp)" - | wl-copy',
            )
            self.assertEqual(slurp_super.parse_status, "ok")

            slurp_print = binds[7]
            self.assertEqual(slurp_print.modifiers, [])
            self.assertEqual(slurp_print.modmask, 0)
            self.assertEqual(slurp_print.key, "Print")

            # Pipes and "||"
            self.assertEqual(
                binds[8].dispatcher.arg_summary,
                "dunstctl history-pop || dunstctl close",
            )

            # bindel / bindl / bindm flags
            vol_up = binds[11]
            self.assertEqual(vol_up.bind_type, "bindel")
            self.assertTrue(vol_up.flags["locked"])
            self.assertTrue(vol_up.flags["repeating"])

            vol_mute = binds[13]
            self.assertEqual(vol_mute.bind_type, "bindl")
            self.assertTrue(vol_mute.flags["locked"])
            self.assertFalse(vol_mute.flags["repeating"])

            mouse_drag = binds[14]
            self.assertEqual(mouse_drag.bind_type, "bindm")
            self.assertTrue(mouse_drag.flags["mouse"])
            self.assertEqual(mouse_drag.key_kind, "mouse_button")

    def test_extra_hyprlang_features_and_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            conf_d = os.path.join(tmpdir, "conf.d")
            os.makedirs(conf_d, exist_ok=True)

            # Glob sourced files (01-first.conf and 02-second.conf) with BOM & CRLF
            with open(os.path.join(conf_d, "02-second.conf"), "wb") as f:
                f.write(
                    b"\xef\xbb\xbfbind = SUPER, 2, exec, second_app\r\n"
                )
            with open(os.path.join(conf_d, "01-first.conf"), "wb") as f:
                f.write(
                    b"bind = SUPER, 1, exec, first_app # inline comment\r\n"
                )

            # Cycle files: cycle_a.conf -> cycle_b.conf -> cycle_a.conf
            cycle_a = os.path.join(tmpdir, "cycle_a.conf")
            cycle_b = os.path.join(tmpdir, "cycle_b.conf")
            with open(cycle_a, "w", encoding="utf-8") as f:
                f.write("source = ./cycle_b.conf\n")
            with open(cycle_b, "w", encoding="utf-8") as f:
                f.write("source = ./cycle_a.conf\n")

            entry = os.path.join(tmpdir, "hyprland.conf")
            with open(entry, "w", encoding="utf-8") as f:
                f.write(
                    """# Extra Hyprlang features test
$mainMod = SUPER

source = ./conf.d/*.conf
source = ./non_existent_missing.conf
source = ./cycle_a.conf

# bindd with description and '##' escape + inline comment
bindd = $mainMod, E, Launch Editor ##1, exec, kate --title "##main" # trailing comment

# unbind directive
unbind = $mainMod, Q

# unknown variable & unknown flag letter
bind = $mainMod, U, exec, $undefinedApp
bindx = $mainMod, X, exec, kitty

# submap block + reset, then unclosed submap at EOF
submap = resize
binde = , right, resizeactive, 10 0
submap = reset

submap = passthrough
bind = $mainMod, Escape, submap, reset
"""
                )

            disc = discover_config(config_dir=tmpdir, no_live=True)
            binds, unbinds, files, diags, stats, complete = parse_hyprlang_config(
                entrypoint=entry,
                home_dir=tmpdir,
            )
            doc = make_scan_document(
                environment=disc.environment,
                files=files,
                binds=binds,
                unbinds=unbinds,
                diagnostics=diags,
                stats=stats,
                complete=complete,
            )
            assert_valid_scan_dict(doc.to_dict())

            # Glob sorted order: 01-first.conf before 02-second.conf
            self.assertEqual(binds[0].dispatcher.arg_summary, "first_app")
            self.assertEqual(binds[1].dispatcher.arg_summary, "second_app")

            # bindd description & '##' escape
            bindd_rec = binds[2]
            self.assertEqual(bindd_rec.bind_type, "bindd")
            self.assertEqual(bindd_rec.description, "Launch Editor #1")
            self.assertEqual(bindd_rec.dispatcher.path, "exec")
            self.assertEqual(bindd_rec.dispatcher.arg_summary, 'kate --title "#main"')

            # unbind recorded
            self.assertEqual(len(unbinds), 1)
            self.assertEqual(unbinds[0].modmask, 64)
            self.assertEqual(unbinds[0].key, "Q")

            # unresolved variable
            unres_bind = binds[3]
            self.assertEqual(unres_bind.parse_status, "unresolved")
            self.assertEqual(unres_bind.dispatcher.arg_summary, "$undefinedApp")

            # unsupported flag letter 'x'
            unsup_bind = binds[4]
            self.assertEqual(unsup_bind.parse_status, "unsupported")

            # submaps
            resize_bind = binds[5]
            self.assertEqual(resize_bind.submap, "resize")
            pass_bind = binds[6]
            self.assertEqual(pass_bind.submap, "passthrough")

            diag_codes = {d.code for d in diags}
            self.assertIn("source_missing", diag_codes)
            self.assertIn("source_cycle", diag_codes)
            self.assertIn("unresolved_variable", diag_codes)
            self.assertIn("unknown_bind_flag", diag_codes)
            self.assertIn("unclosed_submap", diag_codes)


if __name__ == "__main__":
    unittest.main()
