"""Unit tests for backend.settings.bluetooth (no real busctl/bluetoothctl/rfkill/pactl)."""

from __future__ import annotations

import copy
import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

from backend.core.live_cmd import LiveCmdResult, run_live_cmd
from backend.settings.bluetooth import (
    connect_device,
    disconnect_device,
    get_bluetooth_state,
    mac_to_dbus_path,
    pair_device,
    remove_device,
    scan_bounded,
    scan_results,
    scan_start,
    scan_stop,
    set_alias,
    set_blocked,
    set_discoverable,
    set_pairable,
    set_powered,
    set_trusted,
    validate_mac,
)
from backend.tests.isolation import IsolatedTestCase

_FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "bluetooth_bluez_sample.json",
)


def _load_fixture() -> dict:
    with open(_FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class FakeBluezRunner:
    """In-memory stateful fake runner for busctl, rfkill, bluetoothctl, and pactl."""

    def __init__(self, fixture: dict | None = None) -> None:
        data = copy.deepcopy(fixture if fixture is not None else _load_fixture())
        self.rfkill: dict = data.get("rfkill", {"rfkilldevices": []})
        self.managed_objects: dict = data.get("managed_objects", {"type": "a{oa{sa{sv}}}", "data": [{}]})
        self.default_sink: str = data.get("default_sink", "")
        self.calls: list[list[str]] = []
        self.fail_cmd: dict[tuple[str, ...], LiveCmdResult] = {}
        self.ignore_writes: bool = False
        self.pair_mode: str = "ok"  # "ok" | "passkey" | "fail"

    def _objects(self) -> dict:
        return self.managed_objects["data"][0]

    def __call__(self, argv: list[str], timeout: float = 5.0) -> LiveCmdResult:
        self.calls.append(list(argv))
        key = tuple(argv)
        if key in self.fail_cmd:
            return self.fail_cmd[key]

        if argv == ["rfkill", "--json"]:
            return LiveCmdResult(ok=True, rc=0, out=json.dumps(self.rfkill), err="")
        if argv == ["rfkill", "unblock", "bluetooth"]:
            if not self.ignore_writes:
                for d in self.rfkill.get("rfkilldevices", []):
                    if d.get("type") == "bluetooth":
                        d["soft"] = "unblocked"
            return LiveCmdResult(ok=True, rc=0, out="", err="")

        if argv == ["pactl", "get-default-sink"]:
            return LiveCmdResult(ok=True, rc=0, out=self.default_sink + "\n", err="")

        if argv == [
            "busctl",
            "--system",
            "--json=short",
            "call",
            "org.bluez",
            "/",
            "org.freedesktop.DBus.ObjectManager",
            "GetManagedObjects",
        ]:
            return LiveCmdResult(ok=True, rc=0, out=json.dumps(self.managed_objects), err="")

        if len(argv) >= 9 and argv[:3] == ["busctl", "--system", "set-property"]:
            _, _, _, _, path, iface, prop, sig, val = argv[:9]
            objs = self._objects()
            if path not in objs or iface not in objs[path]:
                return LiveCmdResult(ok=False, rc=1, out="", err=f"Unknown object/interface: {path} {iface}")
            if self.ignore_writes:
                return LiveCmdResult(ok=True, rc=0, out="", err="")
            if sig == "b":
                parsed_val: object = val == "true"
            elif sig == "u":
                parsed_val = int(val)
            else:
                parsed_val = val
            objs[path][iface][prop] = {"type": sig, "data": parsed_val}
            if prop == "Powered":
                objs[path][iface]["PowerState"] = {"type": "s", "data": "on" if parsed_val else "off"}
            return LiveCmdResult(ok=True, rc=0, out="", err="")

        if len(argv) >= 7 and argv[:3] == ["busctl", "--system", "call"]:
            _, _, _, _, path, iface, method = argv[:7]
            rest = argv[7:]
            objs = self._objects()
            if path not in objs or iface not in objs[path]:
                return LiveCmdResult(ok=False, rc=1, out="", err=f"Unknown object/interface: {path} {iface}")
            if self.ignore_writes:
                return LiveCmdResult(ok=True, rc=0, out="", err="")
            if iface == "org.bluez.Device1" and method == "Connect":
                objs[path][iface]["Connected"] = {"type": "b", "data": True}
                return LiveCmdResult(ok=True, rc=0, out="", err="")
            if iface == "org.bluez.Device1" and method == "Disconnect":
                objs[path][iface]["Connected"] = {"type": "b", "data": False}
                return LiveCmdResult(ok=True, rc=0, out="", err="")
            if iface == "org.bluez.Adapter1" and method == "RemoveDevice" and len(rest) == 2:
                dev_path = rest[1]
                if dev_path not in objs:
                    return LiveCmdResult(ok=False, rc=1, out="", err="Does Not Exist")
                del objs[dev_path]
                return LiveCmdResult(ok=True, rc=0, out="", err="")
            if iface == "org.bluez.Adapter1" and method == "StartDiscovery":
                objs[path][iface]["Discovering"] = {"type": "b", "data": True}
                return LiveCmdResult(ok=True, rc=0, out="", err="")
            if iface == "org.bluez.Adapter1" and method == "StopDiscovery":
                objs[path][iface]["Discovering"] = {"type": "b", "data": False}
                return LiveCmdResult(ok=True, rc=0, out="", err="")

        if len(argv) == 7 and argv[0] == "bluetoothctl" and argv[5] == "pair":
            mac = argv[6]
            dev_path = mac_to_dbus_path(mac)
            objs = self._objects()
            if dev_path not in objs:
                return LiveCmdResult(ok=False, rc=1, out="", err=f"Device {mac} not available")
            if self.pair_mode == "passkey":
                return LiveCmdResult(
                    ok=False,
                    rc=1,
                    out="Request passkey confirmation: 123456",
                    err="AuthenticationFailed",
                )
            if self.pair_mode == "fail":
                return LiveCmdResult(ok=False, rc=1, out="", err="Failed to pair")
            if not self.ignore_writes:
                objs[dev_path]["org.bluez.Device1"]["Paired"] = {"type": "b", "data": True}
            return LiveCmdResult(ok=True, rc=0, out="Pairing successful", err="")

        return LiveCmdResult(ok=False, rc=1, out="", err=f"Unexpected command: {argv!r}")


class TestBluetoothIsolationAndMacValidation(IsolatedTestCase):
    """Tests for isolation guard and strict MAC validation."""

    def test_isolation_guard_blocks_unmocked_bluez_tools(self) -> None:
        with self.assertRaises(AssertionError):
            get_bluetooth_state()
        for cmd in (["busctl", "status"], ["bluetoothctl", "show"], ["rfkill", "--json"]):
            with self.assertRaises(AssertionError):
                run_live_cmd(cmd)

    def test_mac_validation_and_injection_rejection(self) -> None:
        self.assertEqual(validate_mac("d4:50:8a:ca:53:ff"), "D4:50:8A:CA:53:FF")
        self.assertEqual(mac_to_dbus_path("d4:50:8a:ca:53:ff"), "/org/bluez/hci0/dev_D4_50_8A_CA_53_FF")

        for bad in ("D4:50:8A:CA:53", "D4:50:8A:CA:53:FF; rm -rf /", "ZZ:50:8A:CA:53:FF", "", 123, None):
            with self.assertRaises(ValueError):
                validate_mac(bad)
            res = connect_device(bad, runner=FakeBluezRunner())  # type: ignore[arg-type]
            self.assertFalse(res["ok"])


class TestBluetoothStateParsing(IsolatedTestCase):
    """Tests for state parsing, safety flags, and failure/edge conditions."""

    def test_fixture_state_devices_audio_and_safety_flags(self) -> None:
        runner = FakeBluezRunner()
        st = get_bluetooth_state(runner=runner)
        self.assertTrue(st["available"])
        self.assertFalse(st["no_controller"])
        self.assertEqual(st["controller"]["address"], "88:F4:DA:1B:CB:45")
        self.assertTrue(st["controller"]["powered"])
        self.assertFalse(st["controller"]["pairable"])
        self.assertFalse(st["rfkill"]["soft_blocked"])

        devs = {d["address"]: d for d in st["devices"]}
        self.assertEqual(len(devs), 3)
        spk = devs["D4:50:8A:CA:53:FF"]
        self.assertTrue(spk["connected"])
        self.assertTrue(spk["is_audio"])
        self.assertTrue(spk["is_default_sink"])
        self.assertIsNone(spk["rssi"])

        kbd = devs["11:22:33:44:55:66"]
        self.assertTrue(kbd["paired"])
        self.assertFalse(kbd["connected"])
        self.assertFalse(kbd["is_audio"])

        buds = devs["AA:BB:CC:DD:EE:FF"]
        self.assertFalse(buds["paired"])
        self.assertEqual(buds["rssi"], -58)
        self.assertTrue(buds["is_audio"])

        self.assertTrue(st["safety"]["disconnecting_default_audio"])
        self.assertEqual(st["safety"]["default_audio_mac"], "D4:50:8A:CA:53:FF")
        self.assertTrue(st["safety"]["powering_off_disconnects"])
        self.assertEqual(st["safety"]["connected_count"], 1)

    def test_controller_off_rfkill_blocked_no_controller_malformed_timeout(self) -> None:
        # Controller off
        fx = _load_fixture()
        fx["managed_objects"]["data"][0]["/org/bluez/hci0"]["org.bluez.Adapter1"]["Powered"]["data"] = False
        fx["managed_objects"]["data"][0]["/org/bluez/hci0/dev_D4_50_8A_CA_53_FF"]["org.bluez.Device1"]["Connected"]["data"] = False
        st_off = get_bluetooth_state(runner=FakeBluezRunner(fx))
        self.assertTrue(st_off["available"])
        self.assertFalse(st_off["controller"]["powered"])
        self.assertFalse(st_off["safety"]["powering_off_disconnects"])
        self.assertFalse(st_off["safety"]["disconnecting_default_audio"])

        # rfkill soft blocked
        fx_rf = _load_fixture()
        fx_rf["rfkill"]["rfkilldevices"][1]["soft"] = "blocked"
        st_rf = get_bluetooth_state(runner=FakeBluezRunner(fx_rf))
        self.assertTrue(st_rf["rfkill"]["soft_blocked"])

        # No controller
        fx_nc = _load_fixture()
        del fx_nc["managed_objects"]["data"][0]["/org/bluez/hci0"]
        st_nc = get_bluetooth_state(runner=FakeBluezRunner(fx_nc))
        self.assertFalse(st_nc["available"])
        self.assertTrue(st_nc["no_controller"])

        # Malformed JSON
        r_bad = FakeBluezRunner()
        r_bad.fail_cmd[(
            "busctl", "--system", "--json=short", "call", "org.bluez", "/",
            "org.freedesktop.DBus.ObjectManager", "GetManagedObjects",
        )] = LiveCmdResult(ok=True, rc=0, out="{broken json", err="")
        st_bad = get_bluetooth_state(runner=r_bad)
        self.assertFalse(st_bad["available"])
        self.assertIn("Malformed JSON", st_bad["error"])

        # Timeout / bluetoothd down
        r_to = FakeBluezRunner()
        r_to.fail_cmd[(
            "busctl", "--system", "--json=short", "call", "org.bluez", "/",
            "org.freedesktop.DBus.ObjectManager", "GetManagedObjects",
        )] = LiveCmdResult(ok=False, rc=-1, out="", err="timed out", timed_out=True)
        st_to = get_bluetooth_state(runner=r_to)
        self.assertFalse(st_to["available"])
        self.assertIn("timed out", st_to["error"])


class TestBluetoothOpsAndCLI(IsolatedTestCase):
    """Tests for Bluetooth ops, readback verification, scan safety, and CLI."""

    def test_unknown_mac_and_readback_mismatch_and_vanished_device(self) -> None:
        runner = FakeBluezRunner()
        res_unk = connect_device("00:11:22:33:44:55", runner=runner)
        self.assertFalse(res_unk["ok"])
        self.assertFalse(any("Connect" in c for c in runner.calls))

        runner2 = FakeBluezRunner()
        runner2.ignore_writes = True
        res_mis = set_pairable(True, runner=runner2)
        self.assertFalse(res_mis["ok"])
        self.assertIn("readback mismatch", res_mis["error"].lower())

        # Device vanishes between write and readback
        fx = _load_fixture()
        runner3 = FakeBluezRunner(fx)
        orig_call = runner3.__call__

        def vanish_on_readback(argv, timeout=5.0):
            res = orig_call(argv, timeout=timeout)
            if len(argv) >= 7 and argv[2] == "set-property" and argv[6] == "Trusted":
                runner3._objects().pop("/org/bluez/hci0/dev_11_22_33_44_55_66", None)
            return res

        res_van = set_trusted("11:22:33:44:55:66", False, runner=vanish_on_readback)
        self.assertFalse(res_van["ok"])
        self.assertIn("vanished", res_van["error"].lower())

    def test_power_rfkill_unblock_pairable_discoverable_and_device_ops(self) -> None:
        fx = _load_fixture()
        fx["managed_objects"]["data"][0]["/org/bluez/hci0"]["org.bluez.Adapter1"]["Powered"]["data"] = False
        fx["rfkill"]["rfkilldevices"][1]["soft"] = "blocked"
        runner = FakeBluezRunner(fx)

        r_pwr = set_powered(True, runner=runner)
        self.assertTrue(r_pwr["ok"])
        self.assertTrue(r_pwr["after"]["powered"])
        self.assertIn(["rfkill", "unblock", "bluetooth"], runner.calls)

        r_pair = set_pairable(True, runner=runner)
        self.assertTrue(r_pair["ok"])
        self.assertTrue(r_pair["after"]["pairable"])

        r_disc = set_discoverable(True, discoverable_timeout=999, runner=runner)
        self.assertTrue(r_disc["ok"])
        self.assertIn(["busctl", "--system", "set-property", "org.bluez", "/org/bluez/hci0", "org.bluez.Adapter1", "DiscoverableTimeout", "u", "300"], runner.calls)

        r_conn = connect_device("11:22:33:44:55:66", runner=runner)
        self.assertTrue(r_conn["ok"])
        self.assertTrue(r_conn["after"]["connected"])

        r_dis = disconnect_device("11:22:33:44:55:66", runner=runner)
        self.assertTrue(r_dis["ok"])
        self.assertFalse(r_dis["after"]["connected"])

        r_blk = set_blocked("11:22:33:44:55:66", True, runner=runner)
        self.assertTrue(r_blk["ok"])
        self.assertTrue(r_blk["after"]["blocked"])

        r_al = set_alias("11:22:33:44:55:66", "My K2", runner=runner)
        self.assertTrue(r_al["ok"])
        self.assertEqual(r_al["after"]["alias"], "My K2")

        r_rm = remove_device("11:22:33:44:55:66", runner=runner)
        self.assertTrue(r_rm["ok"])
        self.assertIsNone(r_rm["after"])

    def test_scan_bounded_always_stops_even_on_error_and_pairing_modes(self) -> None:
        runner = FakeBluezRunner()
        r_scan = scan_bounded(duration=2.0, runner=runner, sleep_fn=lambda _: None)
        self.assertTrue(r_scan["ok"])
        self.assertFalse(r_scan["after"]["discovering"])
        self.assertEqual(len(r_scan["discovered"]), 1)
        self.assertIn(["busctl", "--system", "call", "org.bluez", "/org/bluez/hci0", "org.bluez.Adapter1", "StopDiscovery"], runner.calls)

        # Even if sleep raises, StopDiscovery MUST be called
        runner_err = FakeBluezRunner()
        with self.assertRaises(RuntimeError):
            scan_bounded(duration=2.0, runner=runner_err, sleep_fn=lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
        self.assertIn(["busctl", "--system", "call", "org.bluez", "/org/bluez/hci0", "org.bluez.Adapter1", "StopDiscovery"], runner_err.calls)

        # Just-works pair
        r_pair_ok = pair_device("AA:BB:CC:DD:EE:FF", runner=runner)
        self.assertTrue(r_pair_ok["ok"])
        self.assertTrue(r_pair_ok["after"]["paired"])
        self.assertIn(["bluetoothctl", "--timeout", "20", "--agent", "NoInputNoOutput", "pair", "AA:BB:CC:DD:EE:FF"], runner.calls)

        # Passkey required -> needs_manual=True
        runner_pk = FakeBluezRunner()
        runner_pk.pair_mode = "passkey"
        r_pair_pk = pair_device("AA:BB:CC:DD:EE:FF", runner=runner_pk)
        self.assertFalse(r_pair_pk["ok"])
        self.assertTrue(r_pair_pk["needs_manual"])
        self.assertFalse(r_pair_pk["pairable_restored"]["changed"])
        # Unchanged Pairable -> no Pairable write
        self.assertFalse(any("Pairable" in c for c in runner_pk.calls))

    def test_pair_restores_pairable_on_change_timeout_and_exception(self) -> None:
        # 1. Pair flips Pairable to True -> finally restores it to False
        runner = FakeBluezRunner()
        orig_call = runner.__call__

        def pair_flips_pairable(argv, timeout=5.0):
            res = orig_call(argv, timeout=timeout)
            if len(argv) >= 6 and argv[0] == "bluetoothctl" and argv[5] == "pair":
                runner._objects()["/org/bluez/hci0"]["org.bluez.Adapter1"]["Pairable"]["data"] = True
            return res

        r_ok = pair_device("AA:BB:CC:DD:EE:FF", runner=pair_flips_pairable)
        self.assertTrue(r_ok["ok"])
        self.assertTrue(r_ok["pairable_restored"]["changed"])
        self.assertTrue(r_ok["pairable_restored"]["ok"])
        self.assertFalse(r_ok["pairable_restored"]["after"])
        self.assertFalse(get_bluetooth_state(runner=runner)["controller"]["pairable"])

        # 2. Pair raises exception after flipping Pairable -> finally still restores
        runner2 = FakeBluezRunner()
        orig_call2 = runner2.__call__

        def pair_raises(argv, timeout=5.0):
            if len(argv) >= 6 and argv[0] == "bluetoothctl" and argv[5] == "pair":
                runner2._objects()["/org/bluez/hci0"]["org.bluez.Adapter1"]["Pairable"]["data"] = True
                raise RuntimeError("bluetoothctl crashed")
            return orig_call2(argv, timeout=timeout)

        with self.assertRaises(RuntimeError):
            pair_device("AA:BB:CC:DD:EE:FF", runner=pair_raises)
        self.assertFalse(get_bluetooth_state(runner=runner2)["controller"]["pairable"])

    def test_cli_settings_bluetooth(self) -> None:
        from backend.cli import main as cli_main

        runner = FakeBluezRunner()
        with mock.patch("backend.settings.bluetooth.state.run_live_cmd", side_effect=lambda argv, **kw: runner(list(argv), timeout=kw.get("timeout", 5.0))):
            with mock.patch("backend.settings.bluetooth.ops.run_live_cmd", side_effect=lambda argv, **kw: runner(list(argv), timeout=kw.get("timeout", 5.0))):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cli_main(["settings", "bluetooth", "state", "--json"])
                self.assertEqual(rc, 0)
                self.assertTrue(json.loads(buf.getvalue())["available"])

                buf2 = io.StringIO()
                with redirect_stdout(buf2):
                    rc2 = cli_main(["settings", "bluetooth", "pairable", "on", "--json"])
                self.assertEqual(rc2, 0)
                self.assertTrue(json.loads(buf2.getvalue())["after"]["pairable"])
