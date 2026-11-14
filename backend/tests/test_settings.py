"""Unit and integration tests for backend/settings (Milestone S2)."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest import mock

from backend.core import constants
from backend.core.include_block import insert_include
from backend.core.overrides import parse_sections
from backend.settings.catalog import CATALOG, CATALOG_BY_ID, OptionSpec
from backend.settings.commit import commit_settings, reset_settings
from backend.settings.preview import (
    PreviewValidationError,
    preview_settings,
    revert_preview,
    validate_changes,
)
from backend.settings.state import current_state, parse_getoption_output
from backend.tests.isolation import FORBIDDEN_REAL_PATHS, IsolatedTestCase

_LUA_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "settings_getoption_probe.json"
)


class TestSettingsCatalog(unittest.TestCase):
    def test_catalog_well_typed_unique_and_valid_ranges(self) -> None:
        self.assertGreaterEqual(len(CATALOG), 25)
        seen_ids: set[str] = set()
        sections = set()
        for opt in CATALOG:
            self.assertIsInstance(opt, OptionSpec)
            self.assertNotIn(opt.id, seen_ids, f"Duplicate id: {opt.id}")
            seen_ids.add(opt.id)
            self.assertIn(opt.section, ("appearance", "desktop"))
            sections.add(opt.section)
            self.assertIn(opt.type, ("bool", "int", "float", "color", "enum", "string"))
            self.assertTrue(opt.label.strip())
            self.assertTrue(opt.description.strip())
            self.assertTrue(opt.getoption_name.strip())
            for seg in opt.hyprland_path.split("."):
                self.assertRegex(seg, _LUA_ID_RE, f"Invalid Lua path segment in {opt.id}: {seg!r}")
            if opt.type in ("int", "float"):
                self.assertIsNotNone(opt.min)
                self.assertIsNotNone(opt.max)
                self.assertLess(opt.min, opt.max)
                self.assertIsNotNone(opt.step)
                self.assertGreater(opt.step, 0)
            if opt.type == "enum":
                self.assertTrue(opt.enum_values)
        self.assertEqual(sections, {"appearance", "desktop"})

    def test_catalog_matches_recorded_live_probe_fixture(self) -> None:
        with open(_FIXTURE_PATH, "r", encoding="utf-8") as f:
            probe = json.load(f)
        for opt in CATALOG:
            self.assertIn(opt.getoption_name, probe)
            raw = probe[opt.getoption_name]
            capable, val = parse_getoption_output(raw, opt.type)
            self.assertTrue(capable, f"{opt.id} not capable in probe: {raw!r}")
            self.assertIsNotNone(val, f"{opt.id} parsed None from {raw!r}")


class TestSettingsState(IsolatedTestCase):
    def test_parse_getoption_shapes(self) -> None:
        self.assertEqual(parse_getoption_output('{"bool": true, "set": true}', "bool"), (True, True))
        self.assertEqual(parse_getoption_output('{"int": 10, "set": true}', "int"), (True, 10))
        self.assertEqual(parse_getoption_output('{"float": 0.960000, "set": true}', "float"), (True, 0.96))
        self.assertEqual(parse_getoption_output('{"str": "dwindle", "set": true}', "enum"), (True, "dwindle"))
        self.assertEqual(parse_getoption_output('{"css": "8 8 8 8", "set": true}', "int"), (True, 8))
        self.assertEqual(
            parse_getoption_output('{"gradient": "ee0b0e10 0deg", "set": true}', "color"),
            (True, "0xee0b0e10"),
        )
        self.assertEqual(parse_getoption_output("no such option", "bool"), (False, None))

    def test_current_state_merges_live_and_overrides(self) -> None:
        with open(_FIXTURE_PATH, "r", encoding="utf-8") as f:
            probe = json.load(f)

        cfg_dir = os.path.join(self._isolated_root, "hypr")
        os.makedirs(cfg_dir, exist_ok=True)
        entry = os.path.join(cfg_dir, "hyprland.lua")
        with open(entry, "w", encoding="utf-8") as f:
            f.write(insert_include('hl.bind("SUPER + Return", hl.dsp.exec_cmd("kitty"))\n'))

        ov_path = os.path.join(cfg_dir, constants.OVERRIDES_FILENAME)
        with open(ov_path, "w", encoding="utf-8") as f:
            f.write(
                constants.OVERRIDES_HEADER
                + constants.section_begin_marker("appearance")
                + "\n"
                + "hl.config({ general = { gaps_in = 12 } })\n"
                + constants.section_end_marker("appearance")
                + "\n"
            )

        def fake_runner(argv, **kwargs):
            opt = argv[2]
            return subprocess.CompletedProcess(argv, 0, stdout=probe.get(opt, "no such option"), stderr="")

        st = current_state(config_dir=cfg_dir, entrypoint=entry, hyprctl_runner=fake_runner)
        self.assertTrue(st["include_installed"])
        self.assertTrue(st["overrides_present"])
        by_id = {o["id"]: o for o in st["options"]}
        self.assertEqual(by_id["general.gaps_in"]["live_value"], 8)
        self.assertEqual(by_id["general.gaps_in"]["override_value"], 12)
        self.assertEqual(by_id["general.gaps_in"]["effective_value"], 12)
        self.assertTrue(by_id["general.gaps_in"]["capable"])


class TestSettingsPreview(unittest.TestCase):
    def test_validate_rejects_unknown_range_type_and_injection(self) -> None:
        bad_cases = [
            {"nonexistent.option": 1},
            {"general.gaps_in": -1},
            {"general.gaps_in": 999},
            {"general.gaps_in": "8"},
            {"general.gaps_in": True},
            {"decoration.active_opacity": 1.5},
            {"general.resize_on_border": "yes"},
            {"general.layout": "invalid_layout"},
            {"general.layout": 'dwindle"; os.execute("id"); --'},
            {"decoration.shadow.color": "not-a-color; os.execute('id')"},
            {"decoration.shadow.color": "0xee0b0e10\n]]"},
        ]
        for changes in bad_cases:
            with self.subTest(changes=changes):
                with self.assertRaises(PreviewValidationError):
                    validate_changes(changes)

    def test_preview_and_revert_preview_argv(self) -> None:
        calls: list[list[str]] = []

        def fake_runner(argv, **kwargs):
            calls.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

        res = preview_settings(
            {"general.gaps_in": 9, "decoration.rounding": 12},
            hyprctl_runner=fake_runner,
        )
        self.assertTrue(res["ok"])
        self.assertEqual(calls[0][0:2], ["hyprctl", "eval"])
        self.assertIn("gaps_in = 9", calls[0][2])
        self.assertIn("rounding = 12", calls[0][2])

        rev = revert_preview(hyprctl_runner=fake_runner)
        self.assertTrue(rev["ok"])
        self.assertEqual(calls[1], ["hyprctl", "reload", "config-only"])


class TestSettingsCommit(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.cfg_dir = os.path.join(self._isolated_root, "hypr")
        os.makedirs(self.cfg_dir, exist_ok=True)
        self.entry = os.path.join(self.cfg_dir, "hyprland.lua")
        self.base_lua = insert_include('hl.bind("SUPER + Return", hl.dsp.exec_cmd("kitty"))\n')
        with open(self.entry, "w", encoding="utf-8") as f:
            f.write(self.base_lua)
        self.ov_path = os.path.join(self.cfg_dir, constants.OVERRIDES_FILENAME)

    def _ok_hyprland(self, argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout="Config parsing result:\nconfig ok\n", stderr="")

    def _ok_reload(self, argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    def test_refuses_when_include_not_installed(self) -> None:
        no_inc_entry = os.path.join(self.cfg_dir, "no_inc.lua")
        with open(no_inc_entry, "w", encoding="utf-8") as f:
            f.write('hl.bind("SUPER + Return", hl.dsp.exec_cmd("kitty"))\n')
        res = commit_settings(
            {"general.gaps_in": 9},
            config_dir=self.cfg_dir,
            entrypoint=no_inc_entry,
            expected_sha256=constants.SHA256_ABSENT,
            backup_dir=self.backup_dir,
            dry_run=False,
        )
        self.assertFalse(res.applied)
        self.assertTrue(any("include" in e.lower() for e in res.errors))
        self.assertFalse(os.path.exists(self.ov_path))

    def test_dry_run_default_writes_nothing(self) -> None:
        res = commit_settings(
            {"general.gaps_in": 9},
            config_dir=self.cfg_dir,
            entrypoint=self.entry,
            expected_sha256=constants.SHA256_ABSENT,
            backup_dir=self.backup_dir,
            hyprland_runner=self._ok_hyprland,
            reload_runner=self._ok_reload,
            sleep_fn=lambda _: None,
        )
        self.assertFalse(res.applied)
        self.assertEqual(res.errors, [])
        self.assertFalse(os.path.exists(self.ov_path))

    def test_commit_golden_and_reset_empty_section_removal(self) -> None:
        res = commit_settings(
            {
                "general.gaps_in": 9,
                "decoration.blur.enabled": False,
                "dwindle.preserve_split": True,
            },
            config_dir=self.cfg_dir,
            entrypoint=self.entry,
            expected_sha256=constants.SHA256_ABSENT,
            backup_dir=self.backup_dir,
            hyprland_runner=self._ok_hyprland,
            reload_runner=self._ok_reload,
            sleep_fn=lambda _: None,
            dry_run=False,
        )
        self.assertTrue(res.applied)
        with open(self.ov_path, "r", encoding="utf-8") as f:
            ov_text = f.read()
        expected_golden = (
            constants.OVERRIDES_HEADER
            + "\n"
            + constants.section_begin_marker("appearance")
            + "\n"
            + "hl.config({ decoration = { blur = { enabled = false } }, general = { gaps_in = 9 } })\n"
            + constants.section_end_marker("appearance")
            + "\n\n"
            + constants.section_begin_marker("desktop")
            + "\n"
            + "hl.config({ dwindle = { preserve_split = true } })\n"
            + constants.section_end_marker("desktop")
            + "\n"
        )
        self.assertEqual(ov_text, expected_golden)

        # Reset appearance section -> removes appearance section completely, leaves desktop
        res2 = reset_settings(
            section="appearance",
            config_dir=self.cfg_dir,
            entrypoint=self.entry,
            expected_sha256=res.sha_after,
            backup_dir=self.backup_dir,
            hyprland_runner=self._ok_hyprland,
            reload_runner=self._ok_reload,
            sleep_fn=lambda _: None,
            dry_run=False,
        )
        self.assertTrue(res2.applied)
        with open(self.ov_path, "r", encoding="utf-8") as f:
            sections = parse_sections(f.read())
        self.assertEqual(list(sections.keys()), ["desktop"])

    def test_sha_mismatch_verify_fail_and_reload_rollback(self) -> None:
        with open(self.ov_path, "w", encoding="utf-8") as f:
            f.write(constants.OVERRIDES_HEADER)
        orig_sha = hashlib.sha256(constants.OVERRIDES_HEADER.encode("utf-8")).hexdigest()

        # SHA mismatch
        r1 = commit_settings(
            {"general.gaps_in": 9},
            config_dir=self.cfg_dir,
            entrypoint=self.entry,
            expected_sha256="0" * 64,
            backup_dir=self.backup_dir,
            hyprland_runner=self._ok_hyprland,
            dry_run=False,
        )
        self.assertFalse(r1.applied)

        # Verify failure writes nothing
        def bad_hl(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 1, stdout="bad", stderr="err")

        r2 = commit_settings(
            {"general.gaps_in": 9},
            config_dir=self.cfg_dir,
            entrypoint=self.entry,
            expected_sha256=orig_sha,
            backup_dir=self.backup_dir,
            hyprland_runner=bad_hl,
            dry_run=False,
        )
        self.assertFalse(r2.applied)
        with open(self.ov_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), constants.OVERRIDES_HEADER)

        # Reload failure rolls back
        def bad_reload(argv, **kwargs):
            if argv[:2] == ["hyprctl", "reload"]:
                return subprocess.CompletedProcess(argv, 1, stdout="", stderr="boom")
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        r3 = commit_settings(
            {"general.gaps_in": 9},
            config_dir=self.cfg_dir,
            entrypoint=self.entry,
            expected_sha256=orig_sha,
            backup_dir=self.backup_dir,
            hyprland_runner=self._ok_hyprland,
            reload_runner=bad_reload,
            sleep_fn=lambda _: None,
            dry_run=False,
        )
        self.assertFalse(r3.applied)
        self.assertTrue(r3.rolled_back)
        with open(self.ov_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), constants.OVERRIDES_HEADER)

    def test_isolation_refuses_real_paths(self) -> None:
        real_hypr = FORBIDDEN_REAL_PATHS[0]
        with self.assertRaises(AssertionError):
            commit_settings(
                {"general.gaps_in": 9},
                config_dir=real_hypr,
                entrypoint=os.path.join(real_hypr, "hyprland.lua"),
                expected_sha256="a" * 64,
                dry_run=False,
            )


class TestSettingsCLI(IsolatedTestCase):
    def test_settings_cli_state_and_commit_dry_run(self) -> None:
        from backend.cli import main as cli_main

        with open(_FIXTURE_PATH, "r", encoding="utf-8") as f:
            probe = json.load(f)

        cfg_dir = os.path.join(self._isolated_root, "hypr")
        os.makedirs(cfg_dir, exist_ok=True)
        entry = os.path.join(cfg_dir, "hyprland.lua")
        with open(entry, "w", encoding="utf-8") as f:
            f.write(insert_include('hl.bind("SUPER + Return", hl.dsp.exec_cmd("kitty"))\n'))

        def fake_subproc(argv, **kwargs):
            if len(argv) >= 3 and argv[0] == "hyprctl" and argv[1] == "getoption":
                return subprocess.CompletedProcess(argv, 0, stdout=probe.get(argv[2], "no such option"), stderr="")
            return subprocess.CompletedProcess(argv, 0, stdout="Config parsing result:\nconfig ok\n", stderr="")

        buf = io.StringIO()
        with redirect_stdout(buf):
            with mock.patch("backend.settings.state.subprocess.run", side_effect=fake_subproc):
                rc = cli_main([
                    "settings", "state",
                    "--config-dir", cfg_dir,
                    "--entrypoint", entry,
                    "--no-live",
                    "--json",
                ])
        self.assertEqual(rc, 0)
        state = json.loads(buf.getvalue())
        self.assertEqual(len(state["options"]), len(CATALOG))


if __name__ == "__main__":
    unittest.main()
