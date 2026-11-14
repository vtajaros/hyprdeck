"""Unit and integration tests for backend/settings/display (Milestone S3)."""

from __future__ import annotations

import hashlib
import io
import json
import os
import signal
import subprocess
import sys
import time
import unittest
import warnings
from contextlib import redirect_stdout
from unittest import mock

from backend.core import constants, revert_guard
from backend.core.include_block import insert_include
from backend.core.overrides import parse_sections
from backend.settings.commit import commit_settings
from backend.settings.display import apply_flow as disp_apply_mod
from backend.settings.display import brightness as disp_bri_mod
from backend.settings.display.apply_flow import (
    MonitorRuleSpec,
    apply_display_changes,
    confirm_display_changes,
    render_monitors_section,
    revert_display_changes,
    validate_display_changes,
)
from backend.settings.display.brightness import (
    MIN_BRIGHTNESS_PERCENT,
    clamp_brightness_percent,
    parse_brightnessctl_machine_output,
    read_brightness,
    set_brightness,
)
from backend.settings.display.state import (
    extract_monitors_overrides,
    get_display_state,
    is_clean_scale,
    mode_matches_available,
    parse_monitors_json,
    probe_monitors,
)
from backend.tests.isolation import FORBIDDEN_REAL_PATHS, IsolatedTestCase, assert_env_isolated

_SINGLE_FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "monitors_single_edp1.json"
)
_DUAL_FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "monitors_dual.json"
)


def _ok_proc(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class TestDisplayStateAndScales(IsolatedTestCase):
    def test_parse_single_edp1_fixture(self) -> None:
        with open(_SINGLE_FIXTURE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        outputs = parse_monitors_json(raw)
        self.assertEqual(len(outputs), 1)
        edp = outputs[0]
        self.assertEqual(edp.name, "eDP-1")
        self.assertEqual(edp.width, 1920)
        self.assertEqual(edp.height, 1200)
        self.assertAlmostEqual(edp.scale, 1.25)
        self.assertTrue(edp.scale_clean)
        self.assertIsNone(edp.scale_warning)
        self.assertFalse(edp.disabled)
        self.assertFalse(edp.vrr_capable)
        self.assertFalse(edp.hdr_capable)
        self.assertEqual(edp.vrr, 0)
        self.assertEqual(edp.mirror_of, "none")
        self.assertEqual(edp.current_mode, "1920x1200@60.00")

    def test_parse_dual_with_disabled_monitor(self) -> None:
        with open(_DUAL_FIXTURE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        raw[1]["disabled"] = True
        outputs = parse_monitors_json(raw)
        self.assertEqual(len(outputs), 2)
        self.assertFalse(outputs[0].disabled)
        self.assertTrue(outputs[1].disabled)
        self.assertTrue(outputs[1].vrr_capable)
        self.assertTrue(outputs[1].hdr_capable)
        self.assertEqual(outputs[1].vrr, 1)

    def test_clean_scale_and_fractional_warning(self) -> None:
        self.assertTrue(is_clean_scale(1920, 1200, 1.0))
        self.assertTrue(is_clean_scale(1920, 1200, 1.25))
        self.assertTrue(is_clean_scale(1920, 1200, 1.5))
        self.assertTrue(is_clean_scale(1920, 1200, 2.0))
        self.assertFalse(is_clean_scale(1920, 1200, 1.75))
        self.assertFalse(is_clean_scale(1920, 1200, 1.33))
        self.assertFalse(is_clean_scale(1920, 1200, 2.25))
        self.assertFalse(is_clean_scale(1920, 1280, 0.75))

        with open(_SINGLE_FIXTURE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        raw[0]["scale"] = 1.75
        out = parse_monitors_json(raw)[0]
        self.assertFalse(out.scale_clean)
        self.assertEqual(out.scale_warning, "fractional: may blur")
        by_scale = {item["scale"]: item for item in out.scale_options}
        self.assertTrue(by_scale[1.25]["clean"])
        self.assertIsNone(by_scale[1.25]["warning"])
        self.assertFalse(by_scale[1.75]["clean"])
        self.assertEqual(by_scale[1.75]["warning"], "fractional: may blur")

    def test_mode_matches_available_formats(self) -> None:
        avail = ["1920x1200@60.00Hz"]
        self.assertEqual(mode_matches_available("1920x1200@60.00Hz", avail), "1920x1200@60.00")
        self.assertEqual(mode_matches_available("1920x1200@60.00", avail), "1920x1200@60.00")
        self.assertEqual(mode_matches_available("1920x1200@60", avail), "1920x1200@60.00")
        self.assertIsNone(mode_matches_available("1280x720@60", avail))


class TestDisplayValidationAndLua(IsolatedTestCase):
    def _single_outputs(self):
        return probe_monitors(fixture_path=_SINGLE_FIXTURE)

    def _dual_outputs(self):
        return probe_monitors(fixture_path=_DUAL_FIXTURE)

    def test_refuses_mode_not_in_available_modes(self) -> None:
        rules, errs = validate_display_changes(
            [{"output": "eDP-1", "mode": "3840x2160@120.00"}],
            self._single_outputs(),
        )
        self.assertEqual(rules, [])
        self.assertTrue(any("availableModes" in e or "mode" in e.lower() for e in errs))

    def test_refuses_disabling_last_enabled_output(self) -> None:
        rules, errs = validate_display_changes(
            [{"output": "eDP-1", "disabled": True}],
            self._single_outputs(),
        )
        self.assertEqual(rules, [])
        self.assertTrue(any("last enabled output" in e.lower() for e in errs))

        # In dual setup, disabling both outputs is also refused
        rules2, errs2 = validate_display_changes(
            [
                {"output": "eDP-1", "disabled": True},
                {"output": "HDMI-A-1", "disabled": True},
            ],
            self._dual_outputs(),
        )
        self.assertEqual(rules2, [])
        self.assertTrue(any("last enabled output" in e.lower() for e in errs2))

        # Disabling ONE of two outputs is allowed
        rules3, errs3 = validate_display_changes(
            [{"output": "HDMI-A-1", "disabled": True}],
            self._dual_outputs(),
        )
        self.assertEqual(errs3, [])
        self.assertEqual(len(rules3), 1)
        self.assertTrue(rules3[0].disabled)

    def test_refuses_mirror_cycles_and_self_mirror_and_disabled_mirror_target(self) -> None:
        dual = self._dual_outputs()
        # Self mirror
        _, errs_self = validate_display_changes(
            [{"output": "eDP-1", "mirror_of": "eDP-1"}],
            dual,
        )
        self.assertTrue(any("itself" in e.lower() for e in errs_self))

        # 2-node mirror cycle
        _, errs_cycle = validate_display_changes(
            [
                {"output": "eDP-1", "mirror_of": "HDMI-A-1"},
                {"output": "HDMI-A-1", "mirror_of": "eDP-1"},
            ],
            dual,
        )
        self.assertTrue(any("cycle" in e.lower() for e in errs_cycle))

        # Mirroring a disabled output
        _, errs_dis = validate_display_changes(
            [
                {"output": "eDP-1", "mirror_of": "HDMI-A-1"},
                {"output": "HDMI-A-1", "disabled": True},
            ],
            dual,
        )
        self.assertTrue(any("disabled" in e.lower() for e in errs_dis))

    def test_refuses_vrr_on_non_capable_unknown_output_bad_scale_transform_position(self) -> None:
        single = self._single_outputs()
        _, e_vrr = validate_display_changes([{"output": "eDP-1", "vrr": 1}], single)
        self.assertTrue(any("vrr" in e.lower() for e in e_vrr))

        _, e_unk = validate_display_changes([{"output": "DP-99", "scale": 1.0}], single)
        self.assertTrue(any("unknown output" in e.lower() for e in e_unk))

        _, e_scale = validate_display_changes([{"output": "eDP-1", "scale": 9.0}], single)
        self.assertTrue(any("scale" in e.lower() for e in e_scale))

        _, e_tr = validate_display_changes([{"output": "eDP-1", "transform": 8}], single)
        self.assertTrue(any("transform" in e.lower() for e in e_tr))

        _, e_pos = validate_display_changes([{"output": "eDP-1", "position": "bad"}], single)
        self.assertTrue(any("position" in e.lower() for e in e_pos))

    def test_render_monitors_section_and_round_trip_without_disturbing_other_sections(self) -> None:
        rules = [
            MonitorRuleSpec(
                output="eDP-1",
                disabled=False,
                mode="1920x1200@60.00",
                position="0x0",
                scale=1.5,
                transform=1,
                vrr=0,
            )
        ]
        lua_body = render_monitors_section(rules)
        self.assertIn("hl.monitor({", lua_body)
        self.assertIn('output = "eDP-1"', lua_body)
        self.assertIn("scale = 1.5", lua_body)
        # Round-trip extractor
        doc = f"-- HKS-SECTION-BEGIN: monitors\n{lua_body}\n-- HKS-SECTION-END: monitors\n"
        extracted = extract_monitors_overrides(doc)
        self.assertEqual(extracted["eDP-1"]["scale"], 1.5)
        self.assertEqual(extracted["eDP-1"]["transform"], 1)


class TestBrightness(IsolatedTestCase):
    def test_parse_brightnessctl_and_five_percent_floor(self) -> None:
        info = parse_brightnessctl_machine_output("intel_backlight,backlight,19200,100%,19200\n")
        self.assertTrue(info.available)
        self.assertEqual(info.device, "intel_backlight")
        self.assertEqual(info.percent, 100)
        self.assertEqual(info.min_percent, MIN_BRIGHTNESS_PERCENT)

        self.assertEqual(clamp_brightness_percent(0), 5)
        self.assertEqual(clamp_brightness_percent(3), 5)
        self.assertEqual(clamp_brightness_percent(-20), 5)
        self.assertEqual(clamp_brightness_percent(5), 5)
        self.assertEqual(clamp_brightness_percent(42), 42)
        self.assertEqual(clamp_brightness_percent(150), 100)

        captured_argv: list[list[str]] = []

        def fake_runner(argv, **kwargs):
            captured_argv.append(list(argv))
            return _ok_proc("")

        res = set_brightness(0, device="intel_backlight", runner=fake_runner)
        self.assertTrue(res["ok"])
        self.assertEqual(res["percent"], 5)
        self.assertTrue(res["clamped"])
        self.assertEqual(captured_argv[0], ["brightnessctl", "-d", "intel_backlight", "set", "5%"])

    def test_read_brightness_with_mock_runner(self) -> None:
        def fake_runner(argv, **kwargs):
            if argv[0] == "brightnessctl":
                return _ok_proc("intel_backlight,backlight,9600,50%,19200\n")
            return _ok_proc("", returncode=1)

        info = read_brightness(runner=fake_runner, enable_ddc=False)
        self.assertTrue(info.available)
        self.assertEqual(info.percent, 50)
        self.assertFalse(info.ddc_available)


class TestDisplayConfirmOrRevertFlow(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        # revert_guard.arm intentionally spawns a detached setsid daemon without waiting on Popen
        warnings.simplefilter("ignore", ResourceWarning)
        self.addCleanup(warnings.resetwarnings)

    def _make_tree(self) -> tuple[str, str, str]:
        cfg_dir = os.path.join(self._isolated_root, "hypr")
        os.makedirs(cfg_dir, exist_ok=True)
        entry = os.path.join(cfg_dir, "hyprland.lua")
        ov_path = os.path.join(cfg_dir, constants.OVERRIDES_FILENAME)
        base_entry = (
            "hl.monitor({\n"
            '    output = "eDP-1",\n'
            '    mode = "1920x1200@60",\n'
            '    position = "0x0",\n'
            "    scale = 1.25,\n"
            "})\n"
        )
        with open(entry, "w", encoding="utf-8") as f:
            f.write(insert_include(base_entry))
        return cfg_dir, entry, ov_path

    def test_arm_called_strictly_before_apply_and_fail_closed_if_arm_fails(self) -> None:
        cfg_dir, entry, ov_path = self._make_tree()
        single = probe_monitors(fixture_path=_SINGLE_FIXTURE)
        events: list[str] = []

        orig_arm = revert_guard.arm
        import backend.settings.display.apply_flow as af_mod
        orig_apply = af_mod.apply_managed_change

        def spy_arm(*args, **kwargs):
            events.append("arm")
            return orig_arm(*args, **kwargs)

        def spy_apply(*args, **kwargs):
            events.append("apply")
            return orig_apply(*args, **kwargs)

        with mock.patch("backend.settings.display.apply_flow.revert_guard.arm", side_effect=spy_arm), \
             mock.patch("backend.settings.display.apply_flow.apply_managed_change", side_effect=spy_apply):
            res = apply_display_changes(
                [{"output": "eDP-1", "scale": 1.5}],
                current_outputs=single,
                config_dir=cfg_dir,
                entrypoint=entry,
                expected_sha256=constants.SHA256_ABSENT,
                timeout_seconds=5.0,
                reload_mode="none",
                hyprland_runner=lambda *a, **k: _ok_proc("config ok\n"),
                dry_run=False,
            )
        self.assertTrue(res.applied, res.errors)
        self.assertEqual(events, ["arm", "apply"])
        confirm_display_changes(handle=res.handle)

        with open(ov_path, "rb") as f:
            cur_sha = hashlib.sha256(f.read()).hexdigest()
        # Fail-closed when revert_guard.arm raises
        with mock.patch(
            "backend.settings.display.apply_flow.revert_guard.arm",
            side_effect=revert_guard.RevertGuardError("boom"),
        ), mock.patch(
            "backend.settings.display.apply_flow.apply_managed_change",
            side_effect=spy_apply,
        ):
            events.clear()
            res_fail = apply_display_changes(
                [{"output": "eDP-1", "scale": 2.0}],
                current_outputs=single,
                config_dir=cfg_dir,
                entrypoint=entry,
                expected_sha256=cur_sha,
                timeout_seconds=5.0,
                reload_mode="none",
                hyprland_runner=lambda *a, **k: _ok_proc("config ok\n"),
                dry_run=False,
            )
        self.assertFalse(res_fail.applied)
        self.assertEqual(events, [])
        self.assertIn("Revert guard failed to arm", res_fail.errors[0])

    def test_keep_revert_timeout_and_sigkill_crash_recovery(self) -> None:
        cfg_dir, entry, ov_path = self._make_tree()
        single = probe_monitors(fixture_path=_SINGLE_FIXTURE)

        # Seed existing hks-overrides.lua with appearance section so both non-empty and backup paths are exercised
        r_seed = commit_settings(
            {"general.gaps_in": 12},
            config_dir=cfg_dir,
            entrypoint=entry,
            expected_sha256=constants.SHA256_ABSENT,
            reload_mode="none",
            hyprland_runner=lambda *a, **k: _ok_proc("config ok\n"),
            sleep_fn=lambda _: None,
            dry_run=False,
        )
        self.assertTrue(r_seed.applied, r_seed.errors)
        orig_sha = r_seed.sha_after

        # 1. Keep path
        res_keep = apply_display_changes(
            [{"output": "eDP-1", "scale": 1.5}],
            current_outputs=single,
            config_dir=cfg_dir,
            entrypoint=entry,
            expected_sha256=orig_sha,
            timeout_seconds=0.8,
            reload_mode="none",
            hyprland_runner=lambda *a, **k: _ok_proc("config ok\n"),
            dry_run=False,
        )
        self.assertTrue(res_keep.applied, res_keep.errors)
        self.assertIsNotNone(res_keep.handle)
        with open(ov_path, "r", encoding="utf-8") as f:
            kept_text = f.read()
        self.assertIn("monitors", parse_sections(kept_text))
        self.assertIn("appearance", parse_sections(kept_text))

        conf = confirm_display_changes(handle=res_keep.handle)
        self.assertTrue(conf["ok"])
        time.sleep(1.0)
        with open(ov_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), kept_text)

        # 2. Explicit Revert path
        sha_after_keep = hashlib.sha256(kept_text.encode("utf-8")).hexdigest()
        res_rev = apply_display_changes(
            [{"output": "eDP-1", "scale": 2.0}],
            current_outputs=single,
            config_dir=cfg_dir,
            entrypoint=entry,
            expected_sha256=sha_after_keep,
            timeout_seconds=5.0,
            reload_mode="none",
            hyprland_runner=lambda *a, **k: _ok_proc("config ok\n"),
            dry_run=False,
        )
        self.assertTrue(res_rev.applied)
        with open(ov_path, "r", encoding="utf-8") as f:
            self.assertIn("scale = 2", f.read())
        rev_out = revert_display_changes(handle=res_rev.handle)
        self.assertTrue(rev_out["ok"])
        with open(ov_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), kept_text)

        # 3. Timeout expiry path
        res_to = apply_display_changes(
            [{"output": "eDP-1", "scale": 2.0}],
            current_outputs=single,
            config_dir=cfg_dir,
            entrypoint=entry,
            expected_sha256=sha_after_keep,
            timeout_seconds=0.35,
            reload_mode="none",
            hyprland_runner=lambda *a, **k: _ok_proc("config ok\n"),
            dry_run=False,
        )
        self.assertTrue(res_to.applied)
        deadline = time.monotonic() + 2.5
        reverted = False
        while time.monotonic() < deadline:
            with open(ov_path, "r", encoding="utf-8") as f:
                if f.read() == kept_text:
                    reverted = True
                    break
            time.sleep(0.05)
        self.assertTrue(reverted, "Watchdog did not revert on timeout")
        try:
            os.waitpid(res_to.handle.pid, os.WNOHANG)
        except ChildProcessError:
            pass
        with open(res_to.handle.log_path, "r", encoding="utf-8") as f:
            self.assertIn("Reverted", f.read())

        # 4. SIGKILL crash recovery path
        victim = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            res_kill = apply_display_changes(
                [{"output": "eDP-1", "scale": 2.0}],
                current_outputs=single,
                config_dir=cfg_dir,
                entrypoint=entry,
                expected_sha256=sha_after_keep,
                timeout_seconds=20.0,
                watch_pid=victim.pid,
                reload_mode="none",
                hyprland_runner=lambda *a, **k: _ok_proc("config ok\n"),
                dry_run=False,
            )
            self.assertTrue(res_kill.applied)
            with open(ov_path, "r", encoding="utf-8") as f:
                self.assertIn("scale = 2", f.read())
            os.kill(victim.pid, signal.SIGKILL)
            victim.wait(timeout=2.0)

            deadline2 = time.monotonic() + 2.5
            reverted2 = False
            while time.monotonic() < deadline2:
                with open(ov_path, "r", encoding="utf-8") as f:
                    if f.read() == kept_text:
                        reverted2 = True
                        break
                time.sleep(0.05)
            self.assertTrue(reverted2, "Watchdog did not revert after SIGKILL of watched process")
            try:
                os.waitpid(res_kill.handle.pid, os.WNOHANG)
            except ChildProcessError:
                pass
        finally:
            if victim.poll() is None:
                victim.kill()
                victim.wait(timeout=2.0)


class TestDisplayCLIIntegration(IsolatedTestCase):
    def test_cli_display_state_and_apply_confirm_with_fixture(self) -> None:
        from backend.cli import main

        cfg_dir = os.path.join(self._isolated_root, "hypr")
        os.makedirs(cfg_dir, exist_ok=True)
        entry = os.path.join(cfg_dir, "hyprland.lua")
        with open(entry, "w", encoding="utf-8") as f:
            f.write(insert_include('hl.monitor({ output = "eDP-1", mode = "1920x1200@60", position = "0x0", scale = 1.25 })\n'))

        buf = io.StringIO()
        with mock.patch.dict(os.environ, {constants.ENV_SETTINGS_MONITORS_FIXTURE: _SINGLE_FIXTURE}), \
             redirect_stdout(buf):
            rc = main(["settings", "display", "state", "--config-dir", cfg_dir, "--no-live", "--json"])
        self.assertEqual(rc, 0)
        st = json.loads(buf.getvalue())
        self.assertEqual(len(st["outputs"]), 1)
        self.assertEqual(st["outputs"][0]["name"], "eDP-1")
        self.assertTrue(st["include_installed"])


class TestDisplayIsolation(IsolatedTestCase):
    def test_guards_block_real_paths_and_unmocked_brightness_and_debug_env(self) -> None:
        single = probe_monitors(fixture_path=_SINGLE_FIXTURE)
        real_hypr = FORBIDDEN_REAL_PATHS[0]
        with self.assertRaises(AssertionError):
            disp_apply_mod.apply_display_changes(
                [{"output": "eDP-1", "scale": 1.25}],
                current_outputs=single,
                config_dir=real_hypr,
                entrypoint=os.path.join(real_hypr, "hyprland.lua"),
                expected_sha256=constants.SHA256_ABSENT,
                reload_mode="none",
            )
        with self.assertRaises(AssertionError):
            disp_bri_mod.set_brightness(50)
        with self.assertRaises(AssertionError):
            assert_env_isolated({
                "HKS_BACKUP_DIR": self.backup_dir,
                "HKS_SIDECAR_PATH": self.sidecar_path,
                constants.ENV_STATE_DIR: self.state_dir,
                constants.ENV_SETTINGS_CONFIG_DIR: real_hypr,
            })
