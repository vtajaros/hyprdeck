"""Unit and integration tests for backend/settings/input (Milestone S4)."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import time
import warnings
from contextlib import redirect_stdout
from unittest import mock

from backend.core import constants, revert_guard
from backend.core.confirm_flow import DEFAULT_CONFIRM_TIMEOUT_SECONDS
from backend.core.include_block import insert_include
from backend.core.overrides import parse_sections
from backend.settings.catalog import CATALOG, CATALOG_BY_ID
from backend.settings.input.apply_flow import (
    apply_input_changes,
    confirm_input_changes,
    get_input_state,
    revert_input_changes,
)
from backend.settings.input.devices import (
    SUPPORTED_DEVICE_KEYS,
    extract_devices_overrides,
    parse_devices_json,
    probe_devices,
    render_devices_section,
    validate_device_rules,
)
from backend.settings.input.xkb import (
    load_xkb_rules,
    parse_evdev_lst,
    validate_keyboard_layout,
)
from backend.tests.isolation import IsolatedTestCase, assert_env_isolated

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
_REAL_DEVICES_FIXTURE = os.path.join(_FIXTURES, "devices_real.json")
_SYN_DEVICES_FIXTURE = os.path.join(_FIXTURES, "devices_synthetic.json")
_XKB_SAMPLE_FIXTURE = os.path.join(_FIXTURES, "evdev_sample.lst")


def _ok_proc(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _ok_reload(argv, *a, **k) -> subprocess.CompletedProcess[str]:
    if "configerrors" in argv:
        return _ok_proc("")
    return _ok_proc("ok\n")


class TestInputCatalog(IsolatedTestCase):
    def test_input_catalog_entries_and_risky_flags(self) -> None:
        input_specs = [s for s in CATALOG if s.section == "input"]
        self.assertGreaterEqual(len(input_specs), 20)
        for spec in input_specs:
            self.assertIsInstance(spec.risky, bool)
            self.assertTrue(spec.getoption_name)
            self.assertTrue(spec.hyprland_path)
            self.assertIn("risky", spec.to_dict())

        expected_risky = {
            "input.kb_layout",
            "input.kb_variant",
            "input.kb_options",
            "input.sensitivity",
            "input.accel_profile",
            "input.force_no_accel",
            "input.left_handed",
            "input.touchpad.tap_to_click",
            "input.touchpad.disable_while_typing",
            "input.touchpad.clickfinger_behavior",
            "input.touchpad.middle_button_emulation",
        }
        for opt_id in expected_risky:
            self.assertIn(opt_id, CATALOG_BY_ID, f"Missing expected risky option: {opt_id}")
            self.assertTrue(CATALOG_BY_ID[opt_id].risky, f"{opt_id} must be marked risky")

        expected_non_risky = {
            "input.repeat_rate",
            "input.repeat_delay",
            "input.numlock_by_default",
            "input.follow_mouse",
            "input.scroll_factor",
            "input.natural_scroll",
            "input.touchpad.natural_scroll",
            "input.touchpad.scroll_factor",
            "input.touchpad.drag_lock",
            "gestures.workspace_swipe_distance",
        }
        for opt_id in expected_non_risky:
            self.assertIn(opt_id, CATALOG_BY_ID, f"Missing expected non-risky option: {opt_id}")
            self.assertFalse(CATALOG_BY_ID[opt_id].risky, f"{opt_id} must not be risky")

        # Dropped options on 0.57.1 must not be present
        self.assertNotIn("gestures.workspace_swipe", CATALOG_BY_ID)
        self.assertNotIn("gestures.workspace_swipe_fingers", CATALOG_BY_ID)


class TestXkbParserAndValidation(IsolatedTestCase):
    def test_parse_sample_and_system_evdev_lst(self) -> None:
        with open(_XKB_SAMPLE_FIXTURE, "r", encoding="utf-8") as f:
            rules = parse_evdev_lst(f.read())
        layout_codes = {item["code"] for item in rules.layouts}
        self.assertEqual(layout_codes, {"us", "de", "fr", "ru", "ara"})
        self.assertIn("nodeadkeys", {v["code"] for v in rules.variants["de"]})
        grp_names = {g["group"] for g in rules.option_groups}
        self.assertEqual(grp_names, {"grp", "caps"})

        sys_rules = load_xkb_rules()
        self.assertGreater(len(sys_rules.layouts), 50)
        self.assertIn("us", {item["code"] for item in sys_rules.layouts})

    def test_layout_and_variant_validation_matrix_and_non_latin_warning(self) -> None:
        with open(_XKB_SAMPLE_FIXTURE, "r", encoding="utf-8") as f:
            rules = parse_evdev_lst(f.read())

        # Valid single & multi-layout
        errs, warns = validate_keyboard_layout("us", "", "", xkb_rules=rules)
        self.assertEqual(errs, [])
        self.assertEqual(warns, [])

        errs, warns = validate_keyboard_layout("us,de", ",nodeadkeys", "grp:alt_shift_toggle", xkb_rules=rules)
        self.assertEqual(errs, [])
        self.assertEqual(warns, [])

        # Empty layout refused
        errs, _ = validate_keyboard_layout("", "", "", xkb_rules=rules)
        self.assertTrue(errs)
        errs, _ = validate_keyboard_layout("   ", "", "", xkb_rules=rules)
        self.assertTrue(errs)

        # Unknown layout refused
        errs, _ = validate_keyboard_layout("xx_unknown", "", "", xkb_rules=rules)
        self.assertTrue(errs)

        # Variant list length mismatch refused
        errs, _ = validate_keyboard_layout("us,de", "intl", "", xkb_rules=rules)
        self.assertTrue(errs)

        # Variant belonging to wrong layout refused
        errs, _ = validate_keyboard_layout("us", "nodeadkeys", "", xkb_rules=rules)
        self.assertTrue(errs)

        # Unknown option refused
        errs, _ = validate_keyboard_layout("us", "", "grp:does_not_exist", xkb_rules=rules)
        self.assertTrue(errs)

        # Non-Latin first layout: non-blocking warning only
        errs, warns = validate_keyboard_layout("ru,us", "phonetic,", "", xkb_rules=rules)
        self.assertEqual(errs, [])
        self.assertTrue(any("non-latin" in w.lower() for w in warns), warns)


class TestInputDevices(IsolatedTestCase):
    def test_parse_real_and_synthetic_devices_and_virtual_heuristics(self) -> None:
        real_devs = probe_devices(fixture_path=_REAL_DEVICES_FIXTURE)
        by_name = {d.name: d for d in real_devs}
        self.assertIn("at-translated-set-2-keyboard", by_name)
        self.assertFalse(by_name["at-translated-set-2-keyboard"].is_virtual)
        self.assertEqual(by_name["at-translated-set-2-keyboard"].category, "keyboard")

        self.assertIn("pixa3815:00-093a:3817-touchpad", by_name)
        self.assertEqual(by_name["pixa3815:00-093a:3817-touchpad"].category, "touchpad")
        self.assertFalse(by_name["pixa3815:00-093a:3817-touchpad"].is_virtual)

        for noise in (
            "power-button",
            "video-bus",
            "intel-hid-events",
            "acer-wmi-hotkeys",
            "input-remapper-keyboard",
            "ysd-speaker-(avrcp)",
            "Lid Switch",
            "gaming-mouse-keyboard-1",
        ):
            self.assertTrue(by_name[noise].is_virtual, f"{noise} should be virtual")

        syn_devs = probe_devices(fixture_path=_SYN_DEVICES_FIXTURE)
        syn_names = {d.name: d for d in syn_devs}
        self.assertEqual(syn_names["syn-elan-touchpad"].category, "touchpad")
        self.assertFalse(syn_names["syn-mech-keyboard"].is_virtual)
        self.assertTrue(syn_names["syn-virtual-mouse"].is_virtual)

    def test_render_devices_injection_and_roundtrip(self) -> None:
        syn_devs = probe_devices(fixture_path=_SYN_DEVICES_FIXTURE)
        tricky_name = 'syn-quote"back\\slash-kbd-ü'
        rules, errs = validate_device_rules(
            [{"name": tricky_name, "kb_layout": "de", "repeat_rate": 40}],
            syn_devs,
        )
        self.assertEqual(errs, [])
        rendered = render_devices_section(rules)
        self.assertIn('name = "syn-quote\\"back\\\\slash-kbd-ü"', rendered)

        wrapped = f"-- HKS-SECTION-BEGIN: devices\n{rendered}\n-- HKS-SECTION-END: devices\n"
        parsed = extract_devices_overrides(wrapped)
        self.assertIn(tricky_name, parsed)
        self.assertEqual(parsed[tricky_name]["kb_layout"], "de")
        self.assertEqual(parsed[tricky_name]["repeat_rate"], 40)

    def test_refuses_unknown_device_unsupported_key_and_last_kbd_or_pointer(self) -> None:
        real_devs = probe_devices(fixture_path=_REAL_DEVICES_FIXTURE)

        _, errs = validate_device_rules([{"name": "no-such-device", "enabled": False}], real_devs)
        self.assertTrue(errs)

        self.assertNotIn("force_no_accel", SUPPORTED_DEVICE_KEYS)
        _, errs = validate_device_rules(
            [{"name": "gaming-mouse", "force_no_accel": True}],
            real_devs,
        )
        self.assertTrue(errs)

        # Disabling the last real keyboard must fail even though power-button etc. exist
        _, errs = validate_device_rules(
            [
                {"name": "at-translated-set-2-keyboard", "enabled": False},
                {"name": "gaming-mouse-keyboard", "enabled": False},
            ],
            real_devs,
        )
        self.assertTrue(any("last" in e.lower() and "keyboard" in e.lower() for e in errs), errs)

        # Disabling all real pointing devices (mice + touchpad) must fail
        _, errs = validate_device_rules(
            [
                {"name": "gaming-mouse", "enabled": False},
                {"name": "gaming-mouse-1", "enabled": False},
                {"name": "pixa3815:00-093a:3817-mouse", "enabled": False},
                {"name": "pixa3815:00-093a:3817-touchpad", "enabled": False},
            ],
            real_devs,
        )
        self.assertTrue(any("last" in e.lower() and "pointing" in e.lower() for e in errs), errs)


class TestInputApplyAndConfirmRouting(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        warnings.simplefilter("ignore", ResourceWarning)
        self.addCleanup(warnings.resetwarnings)

    def _make_tree(self) -> tuple[str, str, str]:
        cfg_dir = os.path.join(self._isolated_root, "hypr")
        os.makedirs(cfg_dir, exist_ok=True)
        entry = os.path.join(cfg_dir, "hyprland.lua")
        ov_path = os.path.join(cfg_dir, constants.OVERRIDES_FILENAME)
        base_entry = (
            "hl.config({\n"
            '    input = { kb_layout = "us", repeat_rate = 25 },\n'
            "})\n"
        )
        with open(entry, "w", encoding="utf-8") as f:
            f.write(insert_include(base_entry))
        return cfg_dir, entry, ov_path

    def test_non_risky_uses_commit_without_guard_while_risky_uses_confirm_flow(self) -> None:
        cfg_dir, entry, ov_path = self._make_tree()
        real_devs = probe_devices(fixture_path=_REAL_DEVICES_FIXTURE)

        # Non-risky change -> direct commit, no watchdog handle
        with mock.patch("backend.core.confirm_flow.revert_guard.arm") as mock_arm:
            res_nr = apply_input_changes(
                {"input.repeat_rate": 35},
                current_devices=real_devs,
                config_dir=cfg_dir,
                entrypoint=entry,
                expected_sha256=constants.SHA256_ABSENT,
                reload_mode="config-only",
                hyprland_runner=lambda *a, **k: _ok_proc("config ok\n"),
                reload_runner=_ok_reload,
                sleep_fn=lambda _: None,
                dry_run=False,
            )
            mock_arm.assert_not_called()
        self.assertTrue(res_nr.applied, res_nr.errors)
        self.assertFalse(res_nr.requires_confirm)
        self.assertIsNone(res_nr.handle)
        with open(ov_path, "r", encoding="utf-8") as f:
            self.assertIn("repeat_rate = 35", f.read())

        # Risky change (kb_layout = "ru,us") -> routes through confirm_flow with non-blocking warning
        cur_sha = hashlib.sha256(open(ov_path, "rb").read()).hexdigest()
        res_r = apply_input_changes(
            {"input.kb_layout": "ru,us"},
            current_devices=real_devs,
            config_dir=cfg_dir,
            entrypoint=entry,
            expected_sha256=cur_sha,
            timeout_seconds=0.5,
            reload_mode="none",
            hyprland_runner=lambda *a, **k: _ok_proc("config ok\n"),
            dry_run=False,
        )
        self.assertTrue(res_r.applied, res_r.errors)
        self.assertTrue(res_r.requires_confirm)
        self.assertIsNotNone(res_r.handle)
        self.assertTrue(any("non-latin" in w.lower() for w in res_r.warnings), res_r.warnings)

        conf = confirm_input_changes(handle=res_r.handle)
        self.assertTrue(conf["confirmed"])
        with open(ov_path, "r", encoding="utf-8") as f:
            txt = f.read()
        self.assertIn('kb_layout = "ru,us"', txt)
        self.assertIn("repeat_rate = 35", txt)

        # Device rule change -> always risky -> timeout auto-reverts
        cur_sha2 = hashlib.sha256(open(ov_path, "rb").read()).hexdigest()
        res_dev = apply_input_changes(
            {},
            device_changes=[{"name": "gaming-mouse", "sensitivity": 0.5}],
            current_devices=real_devs,
            config_dir=cfg_dir,
            entrypoint=entry,
            expected_sha256=cur_sha2,
            timeout_seconds=0.35,
            reload_mode="none",
            hyprland_runner=lambda *a, **k: _ok_proc("config ok\n"),
            dry_run=False,
        )
        self.assertTrue(res_dev.applied, res_dev.errors)
        self.assertTrue(res_dev.requires_confirm)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if "gaming-mouse" not in open(ov_path, "r", encoding="utf-8").read():
                break
            time.sleep(0.05)
        self.assertNotIn("gaming-mouse", open(ov_path, "r", encoding="utf-8").read())

    def test_cli_input_state_and_apply_confirm(self) -> None:
        from backend.cli import main as cli_main

        cfg_dir, entry, ov_path = self._make_tree()
        with mock.patch.dict(
            os.environ,
            {
                constants.ENV_SETTINGS_DEVICES_FIXTURE: _REAL_DEVICES_FIXTURE,
                constants.ENV_SETTINGS_XKB_PATH: _XKB_SAMPLE_FIXTURE,
            },
        ):
            buf = io.StringIO()
            with redirect_stdout(buf), mock.patch(
                "backend.settings.state.subprocess.run", return_value=_ok_proc("{}")
            ):
                rc = cli_main(
                    [
                        "settings",
                        "input",
                        "state",
                        "--config-dir",
                        cfg_dir,
                        "--entrypoint",
                        entry,
                        "--json",
                    ]
                )
            self.assertEqual(rc, 0)
            st = json.loads(buf.getvalue())
            self.assertIn("options", st)
            self.assertIn("devices", st)
            self.assertIn("xkb", st)

            # Dry-run default writes nothing
            buf2 = io.StringIO()
            from backend.editor.validator import VerifyResult

            with redirect_stdout(buf2), mock.patch(
                "backend.core.transaction.verify_with_hyprland",
                return_value=VerifyResult(ok=True, exit_code=0, message="config ok"),
            ):
                rc2 = cli_main(
                    [
                        "settings",
                        "input",
                        "apply",
                        "--config-dir",
                        cfg_dir,
                        "--entrypoint",
                        entry,
                        "--inline",
                        json.dumps({"options": {"input.kb_layout": "de"}}),
                        "--reload-mode",
                        "none",
                        "--json",
                    ]
                )
            self.assertEqual(rc2, 0, buf2.getvalue())
            self.assertFalse(os.path.exists(ov_path))


class TestInputIsolation(IsolatedTestCase):
    def test_guards_block_real_paths_and_debug_env(self) -> None:
        with self.assertRaises(AssertionError):
            assert_env_isolated({constants.ENV_SETTINGS_DEVICES_FIXTURE: "/etc/foo.json"})
        with self.assertRaises(AssertionError):
            apply_input_changes(
                {"input.repeat_rate": 30},
                config_dir=os.path.expanduser("~/.config/hypr"),
                entrypoint=os.path.expanduser("~/.config/hypr/hyprland.lua"),
                expected_sha256="x",
                dry_run=True,
            )
