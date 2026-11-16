"""Unit tests for backend.settings.network (no real nmcli)."""

from __future__ import annotations

import copy
import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

from backend.core.live_cmd import LiveCmdResult, run_live_cmd
from backend.settings.network import (
    connect_new_wifi,
    connect_saved,
    disconnect,
    forget,
    get_network_state,
    rescan,
    set_autoconnect,
    set_ipv4_dns,
    set_metered,
    set_wifi_enabled,
    split_nmcli_terse_line,
    validate_ip_list,
    validate_uuid,
)
from backend.tests.isolation import IsolatedTestCase

_FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "network_nmcli_sample.json",
)


def _load_fixture() -> dict:
    with open(_FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class FakeNmcliRunner:
    """In-memory stateful fake nmcli runner."""

    def __init__(self, scenario: str = "dual") -> None:
        fx = _load_fixture()
        self.general = fx["general_dual"]
        self.devices = list(fx["devices_dual"])
        self.device_show = list(fx["device_show_dual"])
        self.connections = list(fx["connections_dual"])
        self.wifi_list = list(fx["wifi_list_sample"])
        self.conn_details: dict[str, dict[str, str]] = {
            "373f29e9-13ec-310b-a026-e07187e48386": {
                "connection.uuid": "373f29e9-13ec-310b-a026-e07187e48386",
                "connection.autoconnect": "yes",
                "connection.metered": "unknown",
                "ipv4.dns": "8.8.8.8",
                "ipv4.ignore-auto-dns": "no",
            },
            "eb23a063-94aa-4482-8a9b-d9fb8e3bfe34": {
                "connection.uuid": "eb23a063-94aa-4482-8a9b-d9fb8e3bfe34",
                "connection.autoconnect": "yes",
                "connection.metered": "unknown",
                "ipv4.dns": "",
                "ipv4.ignore-auto-dns": "no",
            },
        }
        if scenario == "wifi_only":
            self.devices = [d for d in self.devices if not d.startswith("enp62s0:")]
            self.connections = [c for c in self.connections if not c.startswith("373f29e9")]
        elif scenario == "ethernet_only":
            self.devices = [d for d in self.devices if not d.startswith("wlp0s20f3:")]
            self.connections = [c for c in self.connections if not c.startswith("1b7f5db6")]
        elif scenario == "wifi_disabled":
            self.general = fx["general_wifi_disabled"]
            self.devices = [
                d.replace(":connected:EWAKWI-FI_5G:1b7f5db6-4c36-4232-b6f5-dc75b8970cc6", ":unavailable::")
                for d in self.devices
            ]
            self.connections = [
                c.replace(":wlp0s20f3:yes", "::no")
                for c in self.connections
            ]

        self.calls: list[list[str]] = []
        self.fail_cmd: dict[tuple[str, ...], LiveCmdResult] = {}
        self.ignore_writes: bool = False
        self.never_activate: bool = False
        self.seen_passwd_file_contents: list[str] = []

    def __call__(self, argv: list[str], timeout: float = 5.0) -> LiveCmdResult:
        self.calls.append(list(argv))
        key = tuple(argv)
        if key in self.fail_cmd:
            return self.fail_cmd[key]

        if argv[:3] == ["nmcli", "-t", "-f"] and argv[4:] == ["general", "status"]:
            return LiveCmdResult(ok=True, rc=0, out=self.general, err="")
        if argv[:3] == ["nmcli", "-t", "-f"] and argv[4:] == ["device"]:
            return LiveCmdResult(ok=True, rc=0, out="\n".join(self.devices) + "\n", err="")
        if argv[:3] == ["nmcli", "-t", "-f"] and argv[4:] == ["device", "show"]:
            return LiveCmdResult(ok=True, rc=0, out="\n".join(self.device_show) + "\n", err="")
        if argv[:3] == ["nmcli", "-t", "-f"] and argv[4:] == ["connection", "show"]:
            return LiveCmdResult(ok=True, rc=0, out="\n".join(self.connections) + "\n", err="")
        if argv[:3] == ["nmcli", "-t", "-f"] and argv[4:] == ["device", "wifi", "list"]:
            return LiveCmdResult(ok=True, rc=0, out="\n".join(self.wifi_list) + "\n", err="")

        if argv[:3] == ["nmcli", "-t", "-f"] and len(argv) == 7 and argv[4:6] == ["connection", "show"] and argv[6] not in self.conn_details:
            pass
        if argv[:3] == ["nmcli", "-t", "-f"] and len(argv) == 8 and argv[4:7] == ["connection", "show", "uuid"]:
            uuid = argv[7]
            if uuid not in self.conn_details:
                return LiveCmdResult(ok=False, rc=10, out="", err=f"Error: {uuid} - no such connection profile.")
            fields = argv[3].split(",")
            det = self.conn_details[uuid]
            lines = [f"{f}:{det.get(f, '')}" for f in fields]
            return LiveCmdResult(ok=True, rc=0, out="\n".join(lines) + "\n", err="")

        if argv[:3] == ["nmcli", "radio", "wifi"] and len(argv) == 4:
            if not self.ignore_writes:
                parts = self.general.strip().split(":")
                parts[3] = "enabled" if argv[3] == "on" else "disabled"
                self.general = ":".join(parts) + "\n"
            return LiveCmdResult(ok=True, rc=0, out="", err="")

        if argv == ["nmcli", "device", "wifi", "rescan"]:
            return LiveCmdResult(ok=True, rc=0, out="", err="")

        if argv[:4] == ["nmcli", "connection", "up", "uuid"] and len(argv) == 5:
            uuid = argv[4]
            if not self.ignore_writes and not self.never_activate:
                self.connections = [
                    (c[:-3] + ":yes") if c.startswith(uuid + ":") else c
                    for c in self.connections
                ]
            return LiveCmdResult(ok=True, rc=0, out="Connection successfully activated\n", err="")

        if argv[:3] == ["nmcli", "device", "disconnect"] and len(argv) == 4:
            dev = argv[3]
            if not self.ignore_writes:
                self.devices = [
                    f"{dev}:wifi:disconnected::" if d.startswith(dev + ":") else d
                    for d in self.devices
                ]
            return LiveCmdResult(ok=True, rc=0, out="", err="")

        if argv[:4] == ["nmcli", "device", "wifi", "connect"]:
            ssid = argv[4]
            if "passwd-file" in argv:
                pw_path = argv[argv.index("passwd-file") + 1]
                with open(pw_path, "r", encoding="utf-8") as f:
                    self.seen_passwd_file_contents.append(f.read())
            if not self.ignore_writes:
                esc = ssid.replace("\\", "\\\\").replace(":", "\\:")
                self.wifi_list = [
                    (w[:-1] + "*") if w.startswith(esc + ":") else w
                    for w in self.wifi_list
                ]
            return LiveCmdResult(ok=True, rc=0, out="Device successfully activated\n", err="")

        if argv[:4] == ["nmcli", "connection", "delete", "uuid"] and len(argv) == 5:
            uuid = argv[4]
            if not self.ignore_writes:
                self.connections = [c for c in self.connections if not c.startswith(uuid + ":")]
                self.conn_details.pop(uuid, None)
            return LiveCmdResult(ok=True, rc=0, out="", err="")

        if argv[:4] == ["nmcli", "connection", "modify", "uuid"] and len(argv) >= 7:
            uuid = argv[4]
            if uuid not in self.conn_details:
                return LiveCmdResult(ok=False, rc=10, out="", err="No such connection")
            if not self.ignore_writes:
                kv = argv[5:]
                for i in range(0, len(kv), 2):
                    self.conn_details[uuid][kv[i]] = kv[i + 1]
            return LiveCmdResult(ok=True, rc=0, out="", err="")

        return LiveCmdResult(ok=False, rc=1, out="", err=f"Unexpected command: {argv!r}")


class TestNetworkIsolationAndHelpers(IsolatedTestCase):
    """Tests for isolation guard, nmcli -t unescaping, UUID and IP validation."""

    def test_isolation_guard_blocks_unmocked_nmcli(self) -> None:
        with self.assertRaises(AssertionError):
            get_network_state()
        with self.assertRaises(AssertionError):
            run_live_cmd(["nmcli", "general", "status"])

    def test_split_nmcli_terse_line_unescapes_colons_and_backslashes(self) -> None:
        self.assertEqual(
            split_nmcli_terse_line(r"My\:Home\\Net 5G:75:WPA2:*"),
            ["My:Home\\Net 5G", "75", "WPA2", "*"],
        )
        self.assertEqual(
            split_nmcli_terse_line(r"00\:11\:22\:33\:44\:55:1500"),
            ["00:11:22:33:44:55", "1500"],
        )

    def test_uuid_and_ip_validation(self) -> None:
        self.assertEqual(
            validate_uuid("373F29E9-13EC-310B-A026-E07187E48386"),
            "373f29e9-13ec-310b-a026-e07187e48386",
        )
        for bad in ("not-a-uuid", "373f29e9; rm -rf /", "", 123):
            with self.assertRaises(ValueError):
                validate_uuid(bad)

        self.assertEqual(validate_ip_list("auto"), [])
        self.assertEqual(validate_ip_list("1.1.1.1, 8.8.8.8"), ["1.1.1.1", "8.8.8.8"])
        with self.assertRaises(ValueError):
            validate_ip_list("999.999.1.1")


class TestNetworkStateScenarios(IsolatedTestCase):
    """Tests for state parsing across dual/single/disabled/down/malformed/vanished scenarios."""

    def test_dual_connected_hides_lo_p2p_and_dedupes_wifi(self) -> None:
        st = get_network_state(runner=FakeNmcliRunner("dual"))
        self.assertTrue(st["available"])
        self.assertTrue(st["has_wifi_device"])
        self.assertEqual([d["name"] for d in st["devices"]], ["enp62s0", "wlp0s20f3"])
        self.assertEqual([d["name"] for d in st["debug_devices"]], ["lo", "p2p-dev-wlp0s20f3"])
        self.assertEqual(st["devices"][1]["mac"], "88:F4:DA:1B:CB:41")
        self.assertFalse(st["safety"]["wifi_off_would_cut_session"])
        self.assertTrue(all(not c["would_cut_current_session"] for c in st["connections"]))

        # Deduplicated SSIDs: EWAKWI-FI_5G appears once with signal 54 (stronger than 32)
        ewak = [w for w in st["wifi_networks"] if w["ssid"] == "EWAKWI-FI_5G"]
        self.assertEqual(len(ewak), 1)
        self.assertEqual(ewak[0]["signal"], 54)
        self.assertTrue(ewak[0]["in_use"])

        # Escaped SSID parsed cleanly
        escaped = [w for w in st["wifi_networks"] if w["ssid"] == "My:Home\\Net 5G"]
        self.assertEqual(len(escaped), 1)

        # Known Wi-Fi flag matches saved profile
        ge = [w for w in st["wifi_networks"] if w["ssid"] == "GalaxyEyes"]
        self.assertEqual(len(ge), 1)
        self.assertTrue(ge[0]["known"])

        # Hidden SSIDs handled without crash
        hidden = [w for w in st["wifi_networks"] if w["hidden"]]
        self.assertEqual(len(hidden), 2)

    def test_wifi_only_sets_would_cut_current_session(self) -> None:
        st = get_network_state(runner=FakeNmcliRunner("wifi_only"))
        self.assertTrue(st["safety"]["wifi_off_would_cut_session"])
        self.assertTrue(st["devices"][0]["would_cut_current_session"])
        wlp_conn = next(c for c in st["connections"] if c["name"] == "EWAKWI-FI_5G")
        self.assertTrue(wlp_conn["would_cut_current_session"])

    def test_ethernet_only_and_wifi_disabled(self) -> None:
        st_eth = get_network_state(runner=FakeNmcliRunner("ethernet_only"))
        self.assertFalse(st_eth["has_wifi_device"])
        self.assertEqual(st_eth["wifi_networks"], [])

        st_dis = get_network_state(runner=FakeNmcliRunner("wifi_disabled"))
        self.assertFalse(st_dis["general"]["wifi_enabled"])
        self.assertEqual(st_dis["wifi_networks"], [])

    def test_nm_down_malformed_timeout_and_vanished_device(self) -> None:
        r_down = FakeNmcliRunner()
        r_down.fail_cmd[(
            "nmcli", "-t", "-f", "STATE,CONNECTIVITY,WIFI-HW,WIFI,WWAN-HW,WWAN,NETWORKING", "general", "status"
        )] = LiveCmdResult(ok=False, rc=1, out="", err="NetworkManager is not running")
        st_down = get_network_state(runner=r_down)
        self.assertFalse(st_down["available"])
        self.assertIn("not running", st_down["error"])

        r_bad = FakeNmcliRunner()
        r_bad.general = "broken\n"
        self.assertFalse(get_network_state(runner=r_bad)["available"])

        r_to = FakeNmcliRunner()
        r_to.fail_cmd[(
            "nmcli", "-t", "-f", "STATE,CONNECTIVITY,WIFI-HW,WIFI,WWAN-HW,WWAN,NETWORKING", "general", "status"
        )] = LiveCmdResult(ok=False, rc=-1, out="", err="timed out", timed_out=True)
        self.assertFalse(get_network_state(runner=r_to)["available"])

        # Device vanishes between `device` and `device show`
        r_van = FakeNmcliRunner()
        r_van.device_show = []
        st_van = get_network_state(runner=r_van)
        self.assertTrue(st_van["available"])


class TestNetworkOpsAndPasswordSafety(IsolatedTestCase):
    """Tests for network ops, password-never-in-argv, readback, and CLI."""

    def test_password_never_in_argv_or_payload_or_errors(self) -> None:
        secret = "SuperSecretPassphrase!123"
        runner = FakeNmcliRunner("dual")
        res = connect_new_wifi(
            "My:Home\\Net 5G",
            security="WPA2",
            password=secret,
            runner=runner,
            sleep_fn=lambda _: None,
        )
        self.assertTrue(res["ok"])
        for call_argv in runner.calls:
            for arg in call_argv:
                self.assertNotIn(secret, arg)
        self.assertNotIn(secret, json.dumps(res))
        self.assertEqual(len(runner.seen_passwd_file_contents), 1)
        self.assertIn(secret, runner.seen_passwd_file_contents[0])

        # Also check error path never echoes password
        runner_err = FakeNmcliRunner("dual")
        runner_err.fail_cmd = {}
        orig_call = runner_err.__call__

        def fail_wifi_with_secret(argv, timeout=5.0):
            if argv[:4] == ["nmcli", "device", "wifi", "connect"]:
                return LiveCmdResult(ok=False, rc=4, out="", err=f"Bad secret {secret}")
            return orig_call(argv, timeout=timeout)

        res_err = connect_new_wifi(
            "My:Home\\Net 5G",
            security="WPA2",
            password=secret,
            runner=fail_wifi_with_secret,
            sleep_fn=lambda _: None,
        )
        self.assertFalse(res_err["ok"])
        self.assertNotIn(secret, json.dumps(res_err))

    def test_disconnect_confirm_guard_and_connect_timeout_and_profile_edits(self) -> None:
        # Disconnect blocked without confirm when would_cut_current_session
        r_wifi = FakeNmcliRunner("wifi_only")
        res_blk = disconnect("wlp0s20f3", confirm=False, runner=r_wifi)
        self.assertFalse(res_blk["ok"])
        self.assertTrue(res_blk["requires_confirm"])
        self.assertFalse(any(c[:3] == ["nmcli", "device", "disconnect"] for c in r_wifi.calls))

        res_ok = disconnect("wlp0s20f3", confirm=True, runner=r_wifi)
        self.assertTrue(res_ok["ok"])

        # Connect timeout reported honestly
        r_to = FakeNmcliRunner("dual")
        r_to.never_activate = True
        res_to = connect_saved(
            "eb23a063-94aa-4482-8a9b-d9fb8e3bfe34",
            wait_timeout=0.01,
            sleep_fn=lambda _: None,
            runner=r_to,
        )
        self.assertFalse(res_to["ok"])
        self.assertTrue(res_to["timed_out"])

        # Autoconnect, metered, dns, forget, unknown UUID, readback mismatch
        r_ed = FakeNmcliRunner("dual")
        uid = "eb23a063-94aa-4482-8a9b-d9fb8e3bfe34"
        self.assertTrue(set_autoconnect(uid, False, runner=r_ed)["ok"])
        self.assertTrue(set_metered(uid, "yes", runner=r_ed)["ok"])
        self.assertTrue(set_ipv4_dns(uid, "1.1.1.1,8.8.8.8", runner=r_ed)["ok"])
        self.assertTrue(set_ipv4_dns(uid, "auto", runner=r_ed)["ok"])
        self.assertTrue(set_wifi_enabled(False, runner=r_ed)["ok"])
        self.assertTrue(set_wifi_enabled(True, runner=r_ed)["ok"])
        self.assertTrue(rescan(runner=r_ed)["ok"])
        self.assertTrue(forget(uid, runner=r_ed)["ok"])

        # Unknown UUID fails without write
        self.assertFalse(forget("00000000-0000-0000-0000-000000000000", runner=r_ed)["ok"])

        # Readback mismatch
        r_mis = FakeNmcliRunner("dual")
        r_mis.ignore_writes = True
        res_mis = set_autoconnect(uid, False, runner=r_mis)
        self.assertFalse(res_mis["ok"])
        self.assertIn("readback mismatch", res_mis["error"].lower())

    def test_cli_settings_network(self) -> None:
        from backend.cli import main as cli_main

        runner = FakeNmcliRunner("dual")
        with mock.patch("backend.settings.network.state.run_live_cmd", side_effect=lambda argv, **kw: runner(list(argv), timeout=kw.get("timeout", 5.0))):
            with mock.patch("backend.settings.network.ops.run_live_cmd", side_effect=lambda argv, **kw: runner(list(argv), timeout=kw.get("timeout", 5.0))):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cli_main(["settings", "network", "state", "--json"])
                self.assertEqual(rc, 0)
                self.assertTrue(json.loads(buf.getvalue())["available"])

                buf2 = io.StringIO()
                with redirect_stdout(buf2):
                    rc2 = cli_main(["settings", "network", "metered", "eb23a063-94aa-4482-8a9b-d9fb8e3bfe34", "yes", "--json"])
                self.assertEqual(rc2, 0)
                self.assertTrue(json.loads(buf2.getvalue())["ok"])
