"""Unit tests for Phase 2a human descriptions and category derivation."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from backend.cli import main, run_scan_pipeline
from backend.describe.sidecar import resolve_sidecar_path, validate_sidecar_data
from backend.parser.hyprlang_parser import parse_hyprlang_config
from backend.parser.lua_normalizer import parse_lua_config
from backend.validation import assert_valid_scan_dict

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


class TestSidecarOverrides(unittest.TestCase):
    def test_sidecar_path_precedence_and_no_sidecar(self) -> None:
        env = {
            "HKS_SIDECAR": "/tmp/from_env.json",
            "XDG_CONFIG_HOME": "/tmp/xdg_cfg",
            "HOME": "/tmp/home_dir",
        }
        self.assertIsNone(resolve_sidecar_path(cli_path="/tmp/cli.json", no_sidecar=True, env=env))
        self.assertEqual(resolve_sidecar_path(cli_path="/tmp/cli.json", env=env), "/tmp/cli.json")
        self.assertEqual(resolve_sidecar_path(env=env), "/tmp/from_env.json")

        env_no_hks = {"XDG_CONFIG_HOME": "/tmp/xdg_cfg", "HOME": "/tmp/home_dir"}
        self.assertEqual(
            resolve_sidecar_path(env=env_no_hks),
            "/tmp/xdg_cfg/hyprdeck/descriptions.json",
        )

        env_home_only = {"HOME": "/tmp/home_dir"}
        self.assertEqual(
            resolve_sidecar_path(env=env_home_only),
            "/tmp/home_dir/.config/hyprdeck/descriptions.json",
        )

    def test_missing_sidecar_is_silent(self) -> None:
        doc, rc = run_scan_pipeline(
            config_dir=LUA_FIXTURE_DIR,
            no_live=True,
            sidecar_path="/tmp/definitely_missing_hks_sidecar_file_12345.json",
        )
        self.assertEqual(rc, 0)
        self.assertTrue(doc.complete)
        self.assertFalse(doc.stats.sidecar.loaded)
        self.assertEqual(doc.stats.sidecar.overrides, 0)
        sidecar_codes = [d.code for d in doc.diagnostics if d.code.startswith("sidecar_")]
        self.assertEqual(sidecar_codes, [])
        assert_valid_scan_dict(doc.to_dict())

    def test_sidecar_precedence_over_config_and_derived_and_read_only(self) -> None:
        lua_src = """
hl.bind("SUPER + Q", hl.dsp.exec_cmd("kitty"), { description = "Config Description" })
hl.bind("SUPER + SHIFT + Return", hl.dsp.exec_cmd("alacritty"))
"""
        sidecar_payload = {
            "_note": "Root note ignored",
            "version": 1,
            "overrides": [
                {
                    "_note": "Override config description",
                    "match": {
                        "_comment": "Match note ignored",
                        "modifiers": ["SUPER"],
                        "key": "q",
                        "submap": "",
                    },
                    "description": "Sidecar Wins Over Config",
                    "category": "System",
                },
                {
                    "match": {
                        "modifiers": ["SHIFT", "WIN"],
                        "key": "return",
                    },
                    "description": "Sidecar Wins Over Derived",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as cfg_dir, tempfile.TemporaryDirectory() as ext_dir:
            lua_path = os.path.join(cfg_dir, "hyprland.lua")
            with open(lua_path, "w", encoding="utf-8") as f:
                f.write(lua_src)

            sidecar_file = os.path.join(ext_dir, "descriptions.json")
            raw_sidecar = json.dumps(sidecar_payload, indent=2)
            with open(sidecar_file, "w", encoding="utf-8") as f:
                f.write(raw_sidecar)
            os.chmod(sidecar_file, 0o400)

            try:
                doc, rc = run_scan_pipeline(
                    config_dir=cfg_dir,
                    no_live=True,
                    sidecar_path=sidecar_file,
                )
                self.assertEqual(rc, 0)
                self.assertTrue(doc.complete)
                self.assertTrue(doc.stats.sidecar.loaded)
                self.assertEqual(doc.stats.sidecar.overrides, 2)
                self.assertEqual(doc.stats.sidecar.matched, 2)
                self.assertEqual(doc.stats.sidecar.unmatched, 0)

                b_q = _find_bind(doc.binds, ["SUPER"], "Q")
                # Raw config description stays untouched
                self.assertEqual(b_q.description, "Config Description")
                self.assertEqual(b_q.description_effective.text, "Sidecar Wins Over Config")
                self.assertEqual(b_q.description_effective.source, "sidecar")
                self.assertFalse(b_q.description_effective.generic)
                self.assertEqual(b_q.category, "System")
                self.assertEqual(b_q.category_source, "sidecar")

                b_ret = _find_bind(doc.binds, ["SUPER", "SHIFT"], "Return")
                self.assertEqual(b_ret.description_effective.text, "Sidecar Wins Over Derived")
                self.assertEqual(b_ret.description_effective.source, "sidecar")
                self.assertEqual(b_ret.category, "Apps")
                self.assertEqual(b_ret.category_source, "derived")

                with open(sidecar_file, "r", encoding="utf-8") as f:
                    self.assertEqual(f.read(), raw_sidecar)
                assert_valid_scan_dict(doc.to_dict())
            finally:
                os.chmod(sidecar_file, 0o600)

    def test_stacked_binds_ambiguous_vs_dispatcher_disambiguated_and_unmatched(self) -> None:
        # Step 1: Match ALT+Tab without dispatcher => hits both stacked binds and emits sidecar_ambiguous
        sidecar_ambig = {
            "version": 1,
            "overrides": [
                {
                    "match": {"modifiers": ["ALT"], "key": "Tab"},
                    "description": "Switch active window",
                },
                {
                    "match": {"modifiers": ["SUPER"], "key": "NonExistentKey99"},
                    "description": "Stale override",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as ext_dir:
            sc_path = os.path.join(ext_dir, "ambig.json")
            with open(sc_path, "w", encoding="utf-8") as f:
                json.dump(sidecar_ambig, f)

            doc, _ = run_scan_pipeline(
                config_dir=LUA_FIXTURE_DIR,
                no_live=True,
                sidecar_path=sc_path,
            )
            self.assertTrue(doc.complete)
            self.assertEqual(doc.stats.sidecar.overrides, 2)
            self.assertEqual(doc.stats.sidecar.matched, 1)
            self.assertEqual(doc.stats.sidecar.unmatched, 1)

            alt_tabs = [b for b in doc.binds if b.modifiers == ["ALT"] and b.key == "Tab"]
            self.assertEqual(len(alt_tabs), 2)
            for b in alt_tabs:
                self.assertEqual(b.description_effective.text, "Switch active window")
                self.assertEqual(b.description_effective.source, "sidecar")

            ambig_diags = [d for d in doc.diagnostics if d.code == "sidecar_ambiguous"]
            self.assertEqual(len(ambig_diags), 1)
            self.assertEqual(ambig_diags[0].level, "info")
            for b in alt_tabs:
                self.assertIn(b.id, ambig_diags[0].message)

            unmatched_diags = [d for d in doc.diagnostics if d.code == "sidecar_unmatched"]
            self.assertEqual(len(unmatched_diags), 1)
            self.assertEqual(unmatched_diags[0].level, "warning")
            self.assertIn("1", unmatched_diags[0].message)

        # Step 2: Match ALT+Tab WITH dispatcher => hits only one and emits no sidecar_ambiguous
        sidecar_specific = {
            "version": 1,
            "overrides": [
                {
                    "match": {
                        "modifiers": ["ALT"],
                        "key": "Tab",
                        "dispatcher": "cycle_next",
                    },
                    "description": "Cycle next window only",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as ext_dir:
            sc_path = os.path.join(ext_dir, "specific.json")
            with open(sc_path, "w", encoding="utf-8") as f:
                json.dump(sidecar_specific, f)

            doc2, _ = run_scan_pipeline(
                config_dir=LUA_FIXTURE_DIR,
                no_live=True,
                sidecar_path=sc_path,
            )
            b_cycle = _find_bind(doc2.binds, ["ALT"], "Tab", "cycle_next")
            b_top = _find_bind(doc2.binds, ["ALT"], "Tab", "bring_to_top")
            self.assertEqual(b_cycle.description_effective.text, "Cycle next window only")
            self.assertEqual(b_cycle.description_effective.source, "sidecar")
            self.assertEqual(b_top.description_effective.text, "Bring window to top")
            self.assertEqual(b_top.description_effective.source, "derived")
            self.assertEqual([d for d in doc2.diagnostics if d.code == "sidecar_ambiguous"], [])

    def test_invalid_sidecar_emits_error_and_scan_completes(self) -> None:
        invalid_payloads = [
            "{not valid json",
            json.dumps({"version": 2, "overrides": []}),
            json.dumps({"version": 1, "overrides": "not-a-list"}),
            json.dumps(
                {
                    "version": 1,
                    "overrides": [
                        {
                            "match": {"modifiers": ["SUPER"], "key": "Return"},
                            "category": "NotACategory",
                        }
                    ],
                }
            ),
            json.dumps(
                {
                    "version": 1,
                    "overrides": [
                        {
                            "match": {"modifiers": ["SUPER"], "key": "Return"},
                        }
                    ],
                }
            ),
        ]
        with tempfile.TemporaryDirectory() as ext_dir:
            for idx, payload in enumerate(invalid_payloads):
                with self.subTest(case_idx=idx):
                    sc_path = os.path.join(ext_dir, f"bad_{idx}.json")
                    with open(sc_path, "w", encoding="utf-8") as f:
                        f.write(payload)

                    doc, rc = run_scan_pipeline(
                        config_dir=LUA_FIXTURE_DIR,
                        no_live=True,
                        sidecar_path=sc_path,
                    )
                    self.assertEqual(rc, 0)
                    self.assertTrue(doc.complete)
                    self.assertFalse(doc.stats.sidecar.loaded)
                    inv_diags = [d for d in doc.diagnostics if d.code == "sidecar_invalid"]
                    self.assertEqual(len(inv_diags), 1)
                    self.assertEqual(inv_diags[0].level, "error")
                    b_ret = _find_bind(doc.binds, ["SUPER"], "Return")
                    self.assertEqual(b_ret.description_effective.text, "Launch kitty")
                    self.assertEqual(b_ret.description_effective.source, "derived")
                    assert_valid_scan_dict(doc.to_dict())


class TestPhase2aCLI(unittest.TestCase):
    def test_summary_columns_and_width_limit(self) -> None:
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = main(
                [
                    "summary",
                    "--config-dir",
                    LUA_FIXTURE_DIR,
                    "--no-live",
                    "--no-sidecar",
                ]
            )
        self.assertEqual(rc, 0)
        lines = out_buf.getvalue().splitlines()
        self.assertGreater(len(lines), 10)
        header = lines[0]
        self.assertIn("SHORTCUT", header)
        self.assertIn("DISPATCHER", header)
        self.assertIn("ARGS", header)
        self.assertIn("DESCRIPTION", header)
        self.assertIn("CATEGORY", header)
        self.assertIn("file:line", header)

        # Every table row (excluding footer Sandbox: line) fits in 120 columns
        for row_line in lines[:-1]:
            self.assertLessEqual(
                len(row_line),
                120,
                f"Summary table row exceeds 120 columns ({len(row_line)}): {row_line!r}",
            )

        full_table = out_buf.getvalue()
        self.assertIn("Launch kitty", full_table)
        self.assertIn("Apps", full_table)
        self.assertIn("Launch hyprlock", full_table)
        self.assertIn("System", full_table)
        self.assertIn("Media & Hardware", full_table)
        self.assertIn("Close window", full_table)
        self.assertIn("Windows", full_table)
        self.assertIn("Switch to workspace 1", full_table)
        self.assertIn("Workspaces", full_table)
        self.assertIn("Drag window with mouse", full_table)
        self.assertIn("Mouse", full_table)

    def test_sidecar_template_default_and_all(self) -> None:
        # 1) Default template (1 example, valid sidecar JSON, no file writes)
        out_default = io.StringIO()
        with redirect_stdout(out_default), redirect_stderr(io.StringIO()):
            rc1 = main(["sidecar-template"])
        self.assertEqual(rc1, 0)
        parsed_default = json.loads(out_default.getvalue())
        self.assertEqual(parsed_default["version"], 1)
        self.assertIn("_note", parsed_default)
        self.assertEqual(len(parsed_default["overrides"]), 1)
        self.assertIn("_note", parsed_default["overrides"][0])
        validated_default = validate_sidecar_data(parsed_default)
        self.assertEqual(len(validated_default), 1)

        # 2) Full template (--all) on Lua fixture
        out_all = io.StringIO()
        with redirect_stdout(out_all), redirect_stderr(io.StringIO()):
            rc2 = main(
                [
                    "sidecar-template",
                    "--all",
                    "--config-dir",
                    LUA_FIXTURE_DIR,
                    "--no-live",
                ]
            )
        self.assertEqual(rc2, 0)
        parsed_all = json.loads(out_all.getvalue())
        self.assertEqual(parsed_all["version"], 1)
        self.assertEqual(len(parsed_all["overrides"]), 69)
        validated_all = validate_sidecar_data(parsed_all)
        self.assertEqual(len(validated_all), 69)
        first_ov = parsed_all["overrides"][0]
        self.assertTrue(first_ov["_note"].startswith("hyprland.lua:"))
        self.assertEqual(first_ov["description"], "Launch kitty")
        self.assertEqual(first_ov["category"], "Apps")

    def test_cli_scan_and_summary_with_sidecar_flag(self) -> None:
        with tempfile.TemporaryDirectory() as ext_dir:
            sc_path = os.path.join(ext_dir, "cli_sidecar.json")
            with open(sc_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "version": 1,
                        "overrides": [
                            {
                                "match": {"modifiers": ["SUPER"], "key": "Return"},
                                "description": "CLI Custom Terminal",
                                "category": "System",
                            }
                        ],
                    },
                    f,
                )

            out_scan = io.StringIO()
            with redirect_stdout(out_scan), redirect_stderr(io.StringIO()):
                rc_scan = main(
                    [
                        "scan",
                        "--config-dir",
                        LUA_FIXTURE_DIR,
                        "--no-live",
                        "--sidecar",
                        sc_path,
                    ]
                )
            self.assertEqual(rc_scan, 0)
            scan_data = json.loads(out_scan.getvalue())
            assert_valid_scan_dict(scan_data)
            self.assertTrue(scan_data["stats"]["sidecar"]["loaded"])
            self.assertEqual(scan_data["stats"]["sidecar"]["matched"], 1)

            out_sum = io.StringIO()
            with redirect_stdout(out_sum), redirect_stderr(io.StringIO()):
                rc_sum = main(
                    [
                        "summary",
                        "--config-dir",
                        LUA_FIXTURE_DIR,
                        "--no-live",
                        "--sidecar",
                        sc_path,
                    ]
                )
            self.assertEqual(rc_sum, 0)
            self.assertIn("CLI Custom Terminal", out_sum.getvalue())


if __name__ == "__main__":
    unittest.main()
