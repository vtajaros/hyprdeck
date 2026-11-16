"""Unit tests for shared live_cmd runner and backend.settings.audio (no real pactl/wpctl)."""

from __future__ import annotations

import copy
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

from backend.core.live_cmd import LiveCmdResult, run_live_cmd
from backend.settings.audio import (
    classify_device_kind,
    get_audio_state,
    parse_channel_volumes,
    parse_sink_inputs_json,
    parse_sinks_json,
    parse_sources_json,
    set_default_sink,
    set_default_source,
    set_sink_mute,
    set_sink_volume,
    set_source_mute,
    set_source_volume,
    validate_and_clamp_volume,
)
from backend.tests.isolation import IsolatedTestCase

_FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "audio_pactl_sample.json",
)


def _load_fixture() -> dict:
    with open(_FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class FakePactlRunner:
    """In-memory stateful fake pactl runner for unit tests."""

    def __init__(self, fixture: dict | None = None) -> None:
        data = copy.deepcopy(fixture if fixture is not None else _load_fixture())
        self.sinks: list[dict] = data.get("sinks", [])
        self.sources: list[dict] = data.get("sources", [])
        self.sink_inputs: list[dict] = data.get("sink_inputs", [])
        self.default_sink: str = data.get("default_sink", "")
        self.default_source: str = data.get("default_source", "")
        self.calls: list[list[str]] = []
        self.fail_cmd: dict[tuple[str, ...], LiveCmdResult] = {}
        self.ignore_writes: bool = False

    def __call__(self, argv: list[str], timeout: float = 5.0) -> LiveCmdResult:
        self.calls.append(list(argv))
        key = tuple(argv)
        if key in self.fail_cmd:
            return self.fail_cmd[key]
        if argv[:2] == ["pactl", "--format=json"] and len(argv) >= 4 and argv[2] == "list":
            what = argv[3]
            if what == "sinks":
                return LiveCmdResult(ok=True, rc=0, out=json.dumps(self.sinks), err="")
            if what == "sources":
                return LiveCmdResult(ok=True, rc=0, out=json.dumps(self.sources), err="")
            if what == "sink-inputs":
                return LiveCmdResult(ok=True, rc=0, out=json.dumps(self.sink_inputs), err="")
        if argv == ["pactl", "get-default-sink"]:
            return LiveCmdResult(ok=True, rc=0, out=self.default_sink + "\n", err="")
        if argv == ["pactl", "get-default-source"]:
            return LiveCmdResult(ok=True, rc=0, out=self.default_source + "\n", err="")

        if len(argv) >= 3 and argv[0] == "pactl":
            action = argv[1]
            if self.ignore_writes:
                return LiveCmdResult(ok=True, rc=0, out="", err="")
            if action in ("set-sink-volume", "set-source-volume") and len(argv) == 4:
                target, pct_str = argv[2], argv[3]
                pool = self.sinks if action == "set-sink-volume" else self.sources
                dev = next((d for d in pool if d.get("name") == target), None)
                if dev is None:
                    return LiveCmdResult(ok=False, rc=1, out="", err=f"No such entity: {target}")
                for ch in (dev.get("volume") or {}).values():
                    ch["value_percent"] = pct_str
                return LiveCmdResult(ok=True, rc=0, out="", err="")

            if action in ("set-sink-mute", "set-source-mute") and len(argv) == 4:
                target, mode = argv[2], argv[3]
                pool = self.sinks if action == "set-sink-mute" else self.sources
                dev = next((d for d in pool if d.get("name") == target), None)
                if dev is None:
                    return LiveCmdResult(ok=False, rc=1, out="", err=f"No such entity: {target}")
                if mode == "toggle":
                    dev["mute"] = not bool(dev.get("mute", False))
                else:
                    dev["mute"] = mode == "1"
                return LiveCmdResult(ok=True, rc=0, out="", err="")

            if action in ("set-default-sink", "set-default-source") and len(argv) == 3:
                target = argv[2]
                pool = self.sinks if action == "set-default-sink" else self.sources
                if not any(d.get("name") == target for d in pool):
                    return LiveCmdResult(ok=False, rc=1, out="", err=f"No such entity: {target}")
                if action == "set-default-sink":
                    self.default_sink = target
                else:
                    self.default_source = target
                return LiveCmdResult(ok=True, rc=0, out="", err="")

        return LiveCmdResult(ok=False, rc=1, out="", err=f"Unexpected command: {argv!r}")


class TestLiveCmd(IsolatedTestCase):
    """Tests for shared backend.core.live_cmd."""

    def test_rejects_string_argv_and_invalid_timeout(self) -> None:
        with self.assertRaises(ValueError):
            run_live_cmd("pactl list sinks")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            run_live_cmd([])
        with self.assertRaises(ValueError):
            run_live_cmd(["echo", "hi"], timeout=0)
        with self.assertRaises(ValueError):
            run_live_cmd(["echo", "hi"], timeout=float("nan"))
        with self.assertRaises(ValueError):
            run_live_cmd(["echo", "hi"], timeout=True)  # type: ignore[arg-type]

    def test_runs_real_safe_argv_and_handles_timeout_and_missing_binary(self) -> None:
        res_ok = run_live_cmd([sys.executable, "-c", "print('hello')"], timeout=5.0)
        self.assertTrue(res_ok.ok)
        self.assertEqual(res_ok.rc, 0)
        self.assertEqual(res_ok.out.strip(), "hello")
        self.assertFalse(res_ok.timed_out)

        res_to = run_live_cmd(
            [sys.executable, "-c", "import time; time.sleep(2)"],
            timeout=0.05,
        )
        self.assertFalse(res_to.ok)
        self.assertTrue(res_to.timed_out)

        res_miss = run_live_cmd(["__nonexistent_binary_hks_test__"], timeout=1.0)
        self.assertFalse(res_miss.ok)
        self.assertEqual(res_miss.rc, 127)
        self.assertFalse(res_miss.timed_out)

    def test_isolation_guard_blocks_unmocked_pactl_and_wpctl(self) -> None:
        with self.assertRaises(AssertionError):
            get_audio_state()
        with self.assertRaises(AssertionError):
            run_live_cmd(["wpctl", "status"])


class TestAudioStateParsing(IsolatedTestCase):
    """Tests for audio JSON parsing, monitor filtering, classification, and failure modes."""

    def test_fixture_state_shape_kinds_balance_and_monitor_filter(self) -> None:
        runner = FakePactlRunner()
        st = get_audio_state(runner=runner)
        self.assertTrue(st["available"])
        self.assertIsNone(st["error"])
        self.assertEqual(st["default_sink"], "bluez_output.D4_50_8A_CA_53_FF.1")
        self.assertEqual(
            st["default_source"],
            "alsa_input.pci-0000_00_1f.3-platform-skl_hda_dsp_generic.HiFi__Mic1__source",
        )

        outputs = {d["name"]: d for d in st["outputs"]}
        self.assertEqual(len(outputs), 3)
        self.assertEqual(outputs["bluez_output.D4_50_8A_CA_53_FF.1"]["kind"], "bluez")
        self.assertTrue(outputs["bluez_output.D4_50_8A_CA_53_FF.1"]["is_default"])
        self.assertEqual(outputs["bluez_output.D4_50_8A_CA_53_FF.1"]["volume_percent"], 80)
        self.assertEqual(outputs["bluez_output.D4_50_8A_CA_53_FF.1"]["balance_diff"], 0)
        self.assertEqual(outputs["bluez_output.D4_50_8A_CA_53_FF.1"]["running_state"], "RUNNING")

        hdmi = outputs["alsa_output.pci-0000_00_1f.3-platform-skl_hda_dsp_generic.HiFi__HDMI3__sink"]
        self.assertEqual(hdmi["kind"], "hdmi")
        self.assertFalse(hdmi["is_default"])

        spk = outputs["alsa_output.pci-0000_00_1f.3-platform-skl_hda_dsp_generic.HiFi__Speaker__sink"]
        self.assertEqual(spk["kind"], "alsa")
        self.assertTrue(spk["mute"])
        self.assertEqual(spk["volume_percent"], 55)  # avg(50, 60)
        self.assertEqual(spk["balance_diff"], 10)  # 60 - 50

        # Monitor sources must be excluded
        input_names = [d["name"] for d in st["inputs"]]
        self.assertEqual(len(input_names), 2)
        for name in input_names:
            self.assertFalse(name.endswith(".monitor"))

        # Streams resolve numeric sink index 109 -> bluez sink name
        self.assertEqual(len(st["streams"]), 1)
        stream = st["streams"][0]
        self.assertEqual(stream["app"], "Firefox")
        self.assertEqual(stream["name"], "YouTube Playback")
        self.assertEqual(stream["sink"], "bluez_output.D4_50_8A_CA_53_FF.1")
        self.assertEqual(stream["volume"], 100)
        self.assertFalse(stream["mute"])

    def test_classify_other_kind_and_empty_lists(self) -> None:
        self.assertEqual(classify_device_kind("hks-test", "Null Output", {}), "other")
        self.assertEqual(parse_channel_volumes({}), (0, 0))
        empty_runner = FakePactlRunner(
            {"default_sink": "", "default_source": "", "sinks": [], "sources": [], "sink_inputs": []}
        )
        st = get_audio_state(runner=empty_runner)
        self.assertTrue(st["available"])
        self.assertEqual(st["outputs"], [])
        self.assertEqual(st["inputs"], [])
        self.assertEqual(st["streams"], [])

    def test_vanished_sink_mid_read_does_not_crash(self) -> None:
        fx = _load_fixture()
        # Stream points to sink index 999 which vanished from sinks list; default_sink also vanished
        fx["sink_inputs"][0]["sink"] = 999
        fx["default_sink"] = "vanished.sink.name"
        runner = FakePactlRunner(fx)
        st = get_audio_state(runner=runner)
        self.assertTrue(st["available"])
        self.assertEqual(st["streams"][0]["sink"], "999")
        self.assertTrue(all(not o["is_default"] for o in st["outputs"]))

    def test_malformed_json_and_timeout_and_daemon_down(self) -> None:
        runner = FakePactlRunner()
        runner.fail_cmd[("pactl", "--format=json", "list", "sinks")] = LiveCmdResult(
            ok=True, rc=0, out="{not valid json", err=""
        )
        st = get_audio_state(runner=runner)
        self.assertFalse(st["available"])
        self.assertIn("Malformed JSON", st["error"])

        runner2 = FakePactlRunner()
        runner2.fail_cmd[("pactl", "--format=json", "list", "sinks")] = LiveCmdResult(
            ok=False, rc=-1, out="", err="Command 'pactl' timed out after 5.0s.", timed_out=True
        )
        st2 = get_audio_state(runner=runner2)
        self.assertFalse(st2["available"])
        self.assertIn("timed out", st2["error"])

        runner3 = FakePactlRunner()
        runner3.fail_cmd[("pactl", "--format=json", "list", "sources")] = LiveCmdResult(
            ok=False, rc=1, out="", err="Connection refused"
        )
        st3 = get_audio_state(runner=runner3)
        self.assertFalse(st3["available"])
        self.assertIn("Connection refused", st3["error"])


class TestAudioOpsAndCLI(IsolatedTestCase):
    """Tests for volume clamping, name-not-index addressing, readback verification, and CLI."""

    def test_volume_clamp_and_reject_invalid(self) -> None:
        self.assertEqual(validate_and_clamp_volume(-10), 0)
        self.assertEqual(validate_and_clamp_volume(120), 100)
        self.assertEqual(validate_and_clamp_volume(120, max_percent=150), 120)
        self.assertEqual(validate_and_clamp_volume(200, max_percent=200), 150)  # hard cap 150
        self.assertEqual(validate_and_clamp_volume("75.6"), 76)

        for bad in ("abc", None, True, False, float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                validate_and_clamp_volume(bad)

    def test_unknown_name_and_numeric_index_fail_without_write(self) -> None:
        runner = FakePactlRunner()
        res_unknown = set_sink_volume("nonexistent.sink", 50, runner=runner)
        self.assertFalse(res_unknown["ok"])
        self.assertIsNone(res_unknown["before"])
        self.assertFalse(any(c[1] == "set-sink-volume" for c in runner.calls))

        runner2 = FakePactlRunner()
        res_idx = set_sink_volume("109", 50, runner=runner2)
        self.assertFalse(res_idx["ok"])
        self.assertIn("node name", res_idx["error"])
        self.assertEqual(runner2.calls, [])

    def test_sink_and_source_volume_mute_default_with_readback(self) -> None:
        runner = FakePactlRunner()
        sink_name = "alsa_output.pci-0000_00_1f.3-platform-skl_hda_dsp_generic.HiFi__Speaker__sink"
        src_name = "alsa_input.pci-0000_00_1f.3-platform-skl_hda_dsp_generic.HiFi__Mic1__source"

        res_vol = set_sink_volume(sink_name, 140, runner=runner)  # clamped to 100
        self.assertTrue(res_vol["ok"])
        self.assertEqual(res_vol["before"]["volume_percent"], 55)
        self.assertEqual(res_vol["after"]["volume_percent"], 100)
        self.assertIn(["pactl", "set-sink-volume", sink_name, "100%"], runner.calls)

        res_mute = set_sink_mute(sink_name, "toggle", runner=runner)
        self.assertTrue(res_mute["ok"])
        self.assertTrue(res_mute["before"]["mute"])
        self.assertFalse(res_mute["after"]["mute"])

        res_src_vol = set_source_volume(src_name, 90, runner=runner)
        self.assertTrue(res_src_vol["ok"])
        self.assertEqual(res_src_vol["before"]["volume_percent"], 100)
        self.assertEqual(res_src_vol["after"]["volume_percent"], 90)
        self.assertIn(["pactl", "set-source-volume", src_name, "90%"], runner.calls)

        res_src_mute = set_source_mute(src_name, "1", runner=runner)
        self.assertTrue(res_src_mute["ok"])
        self.assertTrue(res_src_mute["after"]["mute"])

        res_def_sink = set_default_sink(sink_name, runner=runner)
        self.assertTrue(res_def_sink["ok"])
        self.assertEqual(res_def_sink["after"]["default_sink"], sink_name)
        self.assertTrue(res_def_sink["after"]["device"]["is_default"])

        src2 = "alsa_input.pci-0000_00_1f.3-platform-skl_hda_dsp_generic.HiFi__Mic2__source"
        res_def_src = set_default_source(src2, runner=runner)
        self.assertTrue(res_def_src["ok"])
        self.assertEqual(res_def_src["after"]["default_source"], src2)

    def test_readback_mismatch_fails_cleanly(self) -> None:
        runner = FakePactlRunner()
        runner.ignore_writes = True
        sink_name = "bluez_output.D4_50_8A_CA_53_FF.1"
        res = set_sink_volume(sink_name, 40, runner=runner)
        self.assertFalse(res["ok"])
        self.assertIn("readback mismatch", res["error"].lower())
        self.assertEqual(res["before"]["volume_percent"], 80)
        self.assertEqual(res["after"]["volume_percent"], 80)

    def test_cli_settings_audio_subcommands(self) -> None:
        from backend.cli import main as cli_main

        runner = FakePactlRunner()
        sink_name = "bluez_output.D4_50_8A_CA_53_FF.1"

        with mock.patch("backend.settings.audio.state.run_live_cmd", side_effect=lambda argv, **kw: runner(list(argv), timeout=kw.get("timeout", 5.0))):
            with mock.patch("backend.settings.audio.ops.run_live_cmd", side_effect=lambda argv, **kw: runner(list(argv), timeout=kw.get("timeout", 5.0))):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cli_main(["settings", "audio", "state", "--json"])
                self.assertEqual(rc, 0)
                parsed = json.loads(buf.getvalue())
                self.assertTrue(parsed["available"])

                buf2 = io.StringIO()
                with redirect_stdout(buf2):
                    rc2 = cli_main(["settings", "audio", "set-volume", sink_name, "65", "--json"])
                self.assertEqual(rc2, 0)
                res2 = json.loads(buf2.getvalue())
                self.assertTrue(res2["ok"])
                self.assertEqual(res2["after"]["volume_percent"], 65)
