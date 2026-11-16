"""One-behavior unit tests for backend.settings.power, scripts/hks-power-helper, and system info."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import os
import stat
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest import mock

from backend.core.constants import ENV_HYPRIDLE_PATH, ENV_POWER_SYSFS_ROOT
from backend.core.live_cmd import LiveCmdResult, run_live_cmd
from backend.tests.isolation import IsolatedTestCase

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HELPER_PATH = os.path.join(_REPO_ROOT, "scripts", "hks-power-helper")
_FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "power_sample.json",
)


def _load_fixture() -> dict:
    with open(_FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_helper_module():
    loader = importlib.machinery.SourceFileLoader("hks_power_helper_mod", _HELPER_PATH)
    spec = importlib.util.spec_from_loader("hks_power_helper_mod", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class FakePowerRunner:
    """In-memory fake runner for upower, pgrep, pkill, pkexec, systemd-analyze, and sysinfo cmds."""

    def __init__(self, fixture: dict | None = None, *, sysfs_root: str = "") -> None:
        self.fx = fixture if fixture is not None else _load_fixture()
        self.sysfs_root = sysfs_root
        self.calls: list[list[str]] = []
        self.pkexec_rc: int = 0
        self.pkexec_err: str = ""
        self.pkexec_partial_cpu1: bool = False
        self.hypridle_running: bool = True
        self.pgrep_after_restart: bool = True
        self.restart_count: int = 0
        self.upower_fail: bool = False
        self.lscpu_fail: bool = False
        self.lspci_override: str | None = None

    def __call__(self, argv: list[str], timeout: float = 5.0) -> LiveCmdResult:
        self.calls.append(list(argv))
        if argv[:2] == ["upower", "-i"]:
            if self.upower_fail:
                return LiveCmdResult(ok=False, rc=1, out="", err="upower failed")
            return LiveCmdResult(ok=True, rc=0, out=self.fx["upower_i"], err="")
        if argv == ["pgrep", "-x", "hypridle"]:
            ok = self.pgrep_after_restart if self.restart_count > 0 else self.hypridle_running
            return LiveCmdResult(ok=ok, rc=0 if ok else 1, out="1234\n" if ok else "", err="")
        if argv == ["pkill", "-x", "hypridle"]:
            self.hypridle_running = False
            return LiveCmdResult(ok=True, rc=0, out="", err="")
        if argv[:3] == ["systemd-analyze", "cat-config", "systemd/logind.conf"]:
            return LiveCmdResult(ok=True, rc=0, out=self.fx["logind_cat"], err="")
        if argv[0] == "pkexec":
            if self.pkexec_rc != 0:
                return LiveCmdResult(ok=False, rc=self.pkexec_rc, out="", err=self.pkexec_err)
            if len(argv) >= 4 and self.sysfs_root:
                action, val = argv[2], argv[3]
                if action == "epp":
                    for name in sorted(os.listdir(os.path.join(self.sysfs_root, "devices", "system", "cpu"))):
                        if not name.startswith("cpu") or not name[3:].isdigit():
                            continue
                        p = os.path.join(self.sysfs_root, "devices", "system", "cpu", name, "cpufreq", "energy_performance_preference")
                        if os.path.isfile(p):
                            if self.pkexec_partial_cpu1 and name == "cpu1":
                                continue
                            with open(p, "w", encoding="utf-8") as f:
                                f.write(val + "\n")
                    return LiveCmdResult(ok=True, rc=0, out="", err="")
                if action == "turbo":
                    p = os.path.join(self.sysfs_root, "devices", "system", "cpu", "intel_pstate", "no_turbo")
                    with open(p, "w", encoding="utf-8") as f:
                        f.write(("0\n" if val == "on" else "1\n"))
                    return LiveCmdResult(ok=True, rc=0, out="", err="")
            return LiveCmdResult(ok=True, rc=0, out="", err="")
        if argv == ["hostnamectl"]:
            return LiveCmdResult(ok=True, rc=0, out=self.fx["hostnamectl"], err="")
        if argv == ["uname", "-r"]:
            return LiveCmdResult(ok=True, rc=0, out="7.2.14-arch1-1\n", err="")
        if argv == ["lscpu"]:
            if self.lscpu_fail:
                return LiveCmdResult(ok=False, rc=1, out="", err="lscpu failed")
            return LiveCmdResult(ok=True, rc=0, out=self.fx["lscpu"], err="")
        if argv == ["free", "-b"]:
            return LiveCmdResult(ok=True, rc=0, out=self.fx["free_b"], err="")
        if argv == ["df", "-B1", "/"]:
            return LiveCmdResult(ok=True, rc=0, out=self.fx["df_b1"], err="")
        if argv == ["lspci"]:
            out = self.lspci_override if self.lspci_override is not None else self.fx["lspci"]
            return LiveCmdResult(ok=True, rc=0, out=out, err="")
        if argv == ["uptime", "-p"]:
            return LiveCmdResult(ok=True, rc=0, out="up 2 hours, 29 minutes\n", err="")
        if argv == ["hyprctl", "version"]:
            return LiveCmdResult(ok=True, rc=0, out=self.fx["hyprctl_version"], err="")
        if argv == ["quickshell", "--version"]:
            return LiveCmdResult(ok=True, rc=0, out=self.fx["quickshell_version"], err="")
        return LiveCmdResult(ok=False, rc=1, out="", err=f"Unexpected command: {argv!r}")


class _PowerTestBase(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.fx = _load_fixture()
        self.sysfs_root = os.path.join(self._isolated_root, "sys")
        hypr_dir = os.path.join(self._isolated_root, "hypr_cfg")
        os.makedirs(hypr_dir, exist_ok=True)
        self.hypridle_path = os.path.join(hypr_dir, "hypridle.conf")
        self.os_release_path = os.path.join(self._isolated_root, "os-release")
        self.proc_uptime_path = os.path.join(self._isolated_root, "proc_uptime")
        self.etc_hostname_path = os.path.join(self._isolated_root, "etc_hostname")

        os.environ[ENV_POWER_SYSFS_ROOT] = self.sysfs_root
        os.environ[ENV_HYPRIDLE_PATH] = self.hypridle_path

        self._populate_fake_sysfs()
        with open(self.hypridle_path, "w", encoding="utf-8") as f:
            f.write(self.fx["hypridle_conf"])
        os.chmod(self.hypridle_path, 0o600)
        with open(self.os_release_path, "w", encoding="utf-8") as f:
            f.write(self.fx["os_release"])
        with open(self.proc_uptime_path, "w", encoding="utf-8") as f:
            f.write("8979.15 99990.32\n")
        with open(self.etc_hostname_path, "w", encoding="utf-8") as f:
            f.write("arch-del\n")

    def _populate_fake_sysfs(self) -> None:
        for cpu in ("cpu0", "cpu1"):
            cdir = os.path.join(self.sysfs_root, "devices", "system", "cpu", cpu, "cpufreq")
            os.makedirs(cdir, exist_ok=True)
            files = {
                "scaling_driver": "intel_pstate\n",
                "scaling_governor": "powersave\n",
                "scaling_available_governors": "performance powersave\n",
                "energy_performance_preference": "balance_performance\n",
                "energy_performance_available_preferences": "default performance balance_performance balance_power power \n",
            }
            for k, v in files.items():
                with open(os.path.join(cdir, k), "w", encoding="utf-8") as f:
                    f.write(v)

        ip_dir = os.path.join(self.sysfs_root, "devices", "system", "cpu", "intel_pstate")
        os.makedirs(ip_dir, exist_ok=True)
        with open(os.path.join(ip_dir, "no_turbo"), "w", encoding="utf-8") as f:
            f.write("0\n")

        bat_dir = os.path.join(self.sysfs_root, "class", "power_supply", "BAT1")
        acad_dir = os.path.join(self.sysfs_root, "class", "power_supply", "ACAD")
        os.makedirs(bat_dir, exist_ok=True)
        os.makedirs(acad_dir, exist_ok=True)
        with open(os.path.join(bat_dir, "uevent"), "w", encoding="utf-8") as f:
            f.write(self.fx["bat1_uevent"])
        with open(os.path.join(acad_dir, "online"), "w", encoding="utf-8") as f:
            f.write("1\n")

        pwr_dir = os.path.join(self.sysfs_root, "power")
        os.makedirs(pwr_dir, exist_ok=True)
        with open(os.path.join(pwr_dir, "mem_sleep"), "w", encoding="utf-8") as f:
            f.write("s2idle [deep]\n")

        dmi_dir = os.path.join(self.sysfs_root, "class", "dmi", "id")
        os.makedirs(dmi_dir, exist_ok=True)
        with open(os.path.join(dmi_dir, "sys_vendor"), "w", encoding="utf-8") as f:
            f.write("Acer\n")
        with open(os.path.join(dmi_dir, "product_name"), "w", encoding="utf-8") as f:
            f.write("TravelMate P216-51\n")


class TestPowerIsolation(_PowerTestBase):
    def test_isolation_guard_blocks_unmocked_power_commands(self) -> None:
        for cmd in (["upower", "-i", "/org/freedesktop/UPower/devices/battery_BAT1"], ["pkexec", "/bin/true"], ["pgrep", "-x", "hypridle"]):
            with self.assertRaises(AssertionError):
                run_live_cmd(cmd)

    def test_isolation_guard_blocks_unmocked_spawner_and_never_reaches_real_popen(self) -> None:
        import backend.settings.power.ops as pwr_ops

        runner = FakePowerRunner(self.fx, sysfs_root=self.sysfs_root)
        # Without injected spawner -> isolation guard raises AssertionError before Popen
        with mock.patch("subprocess.Popen", side_effect=AssertionError("real Popen reached")):
            with self.assertRaises(AssertionError) as ctx:
                pwr_ops.set_idle_timeouts({"lock": 480}, runner=runner, backup_dir=self.backup_dir)
            self.assertIn("default_detached_spawner", str(ctx.exception))

        # With injected spawner -> real Popen is never reached
        spawned: list[list[str]] = []
        with mock.patch("subprocess.Popen", side_effect=AssertionError("real Popen reached")):
            res = pwr_ops.set_idle_timeouts(
                {"lock": 540},
                runner=runner,
                spawner=lambda argv: (spawned.append(list(argv)), setattr(runner, "restart_count", runner.restart_count + 1)),
                backup_dir=self.backup_dir,
            )
        self.assertTrue(res["ok"])
        self.assertEqual(spawned, [["hypridle"]])


class TestHypridleParserAndOps(_PowerTestBase):
    def test_hypridle_roundtrip_byte_identical(self) -> None:
        import backend.settings.power.ops as pwr_ops

        raw = self.fx["hypridle_conf"]
        self.assertEqual(pwr_ops.rewrite_hypridle_timeouts(raw, {"dim": 300, "lock": 600, "dpms": 900}), raw)

    def test_hypridle_single_line_change_touches_only_that_line(self) -> None:
        import backend.settings.power.ops as pwr_ops

        raw = self.fx["hypridle_conf"]
        edited = pwr_ops.rewrite_hypridle_timeouts(raw, {"lock": 450})
        diffs = [(a, b) for a, b in zip(raw.splitlines(), edited.splitlines()) if a != b]
        self.assertEqual(diffs, [("    timeout = 600", "    timeout = 450")])

    def test_hypridle_comments_preserved(self) -> None:
        import backend.settings.power.ops as pwr_ops

        raw = self.fx["hypridle_conf"]
        edited = pwr_ops.rewrite_hypridle_timeouts(raw, {"dim": 180})
        self.assertIn("# Dim display after 5 minutes (300s - matches Battery DimDisplayIdleTimeoutSec=300)", edited)
        self.assertIn("# Lock screen after 10 minutes (600s)", edited)
        self.assertIn("# Turn off display after 15 minutes (900s)", edited)

    def test_hypridle_ordering_rejected(self) -> None:
        import backend.settings.power.ops as pwr_ops

        raw = self.fx["hypridle_conf"]
        with self.assertRaises(ValueError):
            pwr_ops.rewrite_hypridle_timeouts(raw, {"dim": 600, "lock": 600})
        with self.assertRaises(ValueError):
            pwr_ops.rewrite_hypridle_timeouts(raw, {"lock": 950, "dpms": 900})

    def test_hypridle_non_integer_rejected(self) -> None:
        import backend.settings.power.ops as pwr_ops

        raw = self.fx["hypridle_conf"]
        for bad in ("abc", 12.5, True, ""):
            with self.assertRaises(ValueError):
                pwr_ops.rewrite_hypridle_timeouts(raw, {"dim": bad})

    def test_hypridle_out_of_range_rejected(self) -> None:
        import backend.settings.power.ops as pwr_ops

        raw = self.fx["hypridle_conf"]
        with self.assertRaises(ValueError):
            pwr_ops.rewrite_hypridle_timeouts(raw, {"dim": 29})
        with self.assertRaises(ValueError):
            pwr_ops.rewrite_hypridle_timeouts(raw, {"dpms": 86401})

    def test_hypridle_unknown_listeners_untouched(self) -> None:
        import backend.settings.power.ops as pwr_ops

        with_unknown = self.fx["hypridle_conf"] + "\n# Custom\nlistener {\n    timeout = 42\n    on-timeout = notify-send hi\n}\n"
        edited = pwr_ops.rewrite_hypridle_timeouts(with_unknown, {"lock": 450})
        self.assertIn("    timeout = 42\n    on-timeout = notify-send hi\n", edited)

    def test_hypridle_no_listener_file_handled(self) -> None:
        import backend.settings.power.ops as pwr_ops
        import backend.settings.power.state as pwr_state

        self.assertEqual(pwr_state.parse_hypridle_conf("# empty\ngeneral {\n}\n"), [])
        with self.assertRaises(ValueError):
            pwr_ops.rewrite_hypridle_timeouts("# empty\n", {"dim": 120})

    def test_hypridle_restart_failure_restores_exact_original_bytes(self) -> None:
        import backend.settings.power.ops as pwr_ops

        with open(self.hypridle_path, "rb") as f:
            orig_bytes = f.read()
        runner = FakePowerRunner(self.fx, sysfs_root=self.sysfs_root)
        runner.pgrep_after_restart = False
        res = pwr_ops.set_idle_timeouts(
            {"lock": 540},
            runner=runner,
            spawner=lambda argv: setattr(runner, "restart_count", runner.restart_count + 1),
            backup_dir=self.backup_dir,
        )
        self.assertFalse(res["ok"])
        self.assertTrue(res["rolled_back"])
        with open(self.hypridle_path, "rb") as f:
            self.assertEqual(f.read(), orig_bytes)

    def test_hypridle_readback_failure_restores_backup(self) -> None:
        import backend.settings.power.ops as pwr_ops

        with open(self.hypridle_path, "rb") as f:
            orig_bytes = f.read()
        runner = FakePowerRunner(self.fx, sysfs_root=self.sysfs_root)
        parsed = pwr_ops.parse_hypridle_conf(self.fx["hypridle_conf"])
        with mock.patch.object(pwr_ops, "parse_hypridle_conf", side_effect=[parsed, parsed, []]):
            res = pwr_ops.set_idle_timeouts(
                {"lock": 540},
                runner=runner,
                spawner=lambda argv: None,
                backup_dir=self.backup_dir,
            )
        self.assertFalse(res["ok"])
        self.assertTrue(res["rolled_back"])
        with open(self.hypridle_path, "rb") as f:
            self.assertEqual(f.read(), orig_bytes)


class TestPowerHelperAndOps(_PowerTestBase):
    def test_helper_epp_whitelist_from_available_preferences(self) -> None:
        env_helper = {**os.environ, ENV_POWER_SYSFS_ROOT: self.sysfs_root}
        p = subprocess.run([_HELPER_PATH, "epp", "balance_power"], env=env_helper, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        with open(os.path.join(self.sysfs_root, "devices", "system", "cpu", "cpu0", "cpufreq", "energy_performance_preference")) as f:
            self.assertEqual(f.read().strip(), "balance_power")
        # Narrow available_preferences -> previously valid 'power' must now be rejected
        with open(os.path.join(self.sysfs_root, "devices", "system", "cpu", "cpu0", "cpufreq", "energy_performance_available_preferences"), "w") as f:
            f.write("balance_performance balance_power\n")
        p2 = subprocess.run([_HELPER_PATH, "epp", "power"], env=env_helper, capture_output=True, text=True)
        self.assertNotEqual(p2.returncode, 0)

    def test_helper_invalid_epp_nonzero_and_no_write(self) -> None:
        env_helper = {**os.environ, ENV_POWER_SYSFS_ROOT: self.sysfs_root}
        p = subprocess.run([_HELPER_PATH, "epp", "invalid_mode"], env=env_helper, capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        for cpu in ("cpu0", "cpu1"):
            with open(os.path.join(self.sysfs_root, "devices", "system", "cpu", cpu, "cpufreq", "energy_performance_preference")) as f:
                self.assertEqual(f.read().strip(), "balance_performance")

    def test_helper_epp_writes_all_cpun(self) -> None:
        env_helper = {**os.environ, ENV_POWER_SYSFS_ROOT: self.sysfs_root}
        p = subprocess.run([_HELPER_PATH, "epp", "power"], env=env_helper, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        for cpu in ("cpu0", "cpu1"):
            with open(os.path.join(self.sysfs_root, "devices", "system", "cpu", cpu, "cpufreq", "energy_performance_preference")) as f:
                self.assertEqual(f.read().strip(), "power")

    def test_helper_turbo_on_writes_0_off_writes_1(self) -> None:
        env_helper = {**os.environ, ENV_POWER_SYSFS_ROOT: self.sysfs_root}
        self.assertEqual(subprocess.run([_HELPER_PATH, "turbo", "off"], env=env_helper).returncode, 0)
        with open(os.path.join(self.sysfs_root, "devices", "system", "cpu", "intel_pstate", "no_turbo")) as f:
            self.assertEqual(f.read().strip(), "1")
        self.assertEqual(subprocess.run([_HELPER_PATH, "turbo", "on"], env=env_helper).returncode, 0)
        with open(os.path.join(self.sysfs_root, "devices", "system", "cpu", "intel_pstate", "no_turbo")) as f:
            self.assertEqual(f.read().strip(), "0")

    def test_helper_refuses_sysfs_override_when_euid_is_0(self) -> None:
        helper_mod = _load_helper_module()
        with mock.patch("os.geteuid", return_value=0):
            with mock.patch.dict(os.environ, {ENV_POWER_SYSFS_ROOT: self.sysfs_root}):
                self.assertEqual(helper_mod._resolve_sysfs_root(), "/sys")

    def test_ops_pkexec_126_and_127_return_cancelled(self) -> None:
        import backend.settings.power.ops as pwr_ops

        for code in (126, 127):
            runner = FakePowerRunner(self.fx, sysfs_root=self.sysfs_root)
            runner.pkexec_rc = code
            res = pwr_ops.set_epp("performance", runner=runner)
            self.assertFalse(res["ok"])
            self.assertTrue(res["cancelled"])
            self.assertIn("authorization cancelled", res["error"].lower())

    def test_ops_partial_readback_mismatch_returns_error_with_before_after(self) -> None:
        import backend.settings.power.ops as pwr_ops

        runner = FakePowerRunner(self.fx, sysfs_root=self.sysfs_root)
        runner.pkexec_partial_cpu1 = True
        res = pwr_ops.set_epp("performance", runner=runner)
        self.assertFalse(res["ok"])
        self.assertIn("mismatch", res["error"].lower())
        self.assertIn("per_cpu", res["before"])
        self.assertEqual(res["after"]["per_cpu"]["cpu0"], "performance")
        self.assertEqual(res["after"]["per_cpu"]["cpu1"], "balance_performance")

    def test_ops_runner_never_receives_shell_or_string_argv(self) -> None:
        import backend.settings.power.ops as pwr_ops

        seen_kwargs: list[dict] = []
        runner = FakePowerRunner(self.fx, sysfs_root=self.sysfs_root)

        def spying_run(argv, **kwargs):
            self.assertIsInstance(argv, list)
            seen_kwargs.append(dict(kwargs))
            return runner(argv, timeout=kwargs.get("timeout", 5.0))

        with mock.patch.object(pwr_ops, "run_live_cmd", side_effect=spying_run):
            res = pwr_ops.set_epp("balance_power", runner=runner)
        self.assertTrue(res["ok"])
        for kw in seen_kwargs:
            self.assertNotIn("shell", kw)


class TestPowerDegradationAndSysInfo(_PowerTestBase):
    def test_degradation_no_upower_falls_back_cleanly(self) -> None:
        import backend.settings.power.state as pwr_state

        runner = FakePowerRunner(self.fx, sysfs_root=self.sysfs_root)
        runner.upower_fail = True
        st = pwr_state.get_power_state(runner=runner)
        self.assertTrue(st["battery"]["available"])
        self.assertEqual(st["battery"]["percentage"], 100.0)

    def test_degradation_no_intel_pstate(self) -> None:
        import backend.settings.power.state as pwr_state

        os.remove(os.path.join(self.sysfs_root, "devices", "system", "cpu", "intel_pstate", "no_turbo"))
        runner = FakePowerRunner(self.fx, sysfs_root=self.sysfs_root)
        st = pwr_state.get_power_state(runner=runner)
        self.assertTrue(st["cpu"]["available"])
        self.assertIsNone(st["cpu"]["turbo_enabled"])
        self.assertFalse(st["capabilities"]["can_write_turbo"])

    def test_degradation_no_hypridle_conf(self) -> None:
        import backend.settings.power.state as pwr_state

        runner = FakePowerRunner(self.fx, sysfs_root=self.sysfs_root)
        st = pwr_state.get_power_state(
            runner=runner,
            env={**os.environ, ENV_HYPRIDLE_PATH: os.path.join(self._isolated_root, "missing.conf")},
        )
        self.assertFalse(st["hypridle"]["available"])
        self.assertFalse(st["capabilities"]["hypridle_present"])

    def test_degradation_no_battery(self) -> None:
        import backend.settings.power.state as pwr_state

        empty_sys = os.path.join(self._isolated_root, "empty_sys")
        os.makedirs(empty_sys, exist_ok=True)
        runner = FakePowerRunner(self.fx, sysfs_root=empty_sys)
        runner.upower_fail = True
        st = pwr_state.get_power_state(runner=runner, env={**os.environ, ENV_POWER_SYSFS_ROOT: empty_sys})
        self.assertFalse(st["battery"]["available"])
        self.assertFalse(st["capabilities"]["has_battery"])

    def test_gpu_strips_pci_address_with_and_without_domain_prefix(self) -> None:
        import backend.settings.power.state as pwr_state

        runner = FakePowerRunner(self.fx, sysfs_root=self.sysfs_root)
        info = pwr_state.get_system_info(runner=runner)
        self.assertEqual(
            info["gpu"],
            "VGA compatible controller: Intel Corporation Raptor Lake-P [Iris Xe Graphics] (rev 04)",
        )

        runner.lspci_override = "00:02.0 VGA compatible controller: Intel Corporation UHD Graphics\n"
        info2 = pwr_state.get_system_info(runner=runner)
        self.assertEqual(info2["gpu"], "VGA compatible controller: Intel Corporation UHD Graphics")

    def test_system_info_privacy_no_ids_serials_mac_ip(self) -> None:
        import backend.settings.power.state as pwr_state

        runner = FakePowerRunner(self.fx, sysfs_root=self.sysfs_root)
        runner.lscpu_fail = True
        info = pwr_state.get_system_info(
            runner=runner,
            env={
                **os.environ,
                "HKS_OS_RELEASE_PATH": self.os_release_path,
                "HKS_PROC_UPTIME_PATH": self.proc_uptime_path,
                "HKS_ETC_HOSTNAME_PATH": self.etc_hostname_path,
            },
        )
        self.assertIsNone(info["cpu_model"])
        dumped = json.dumps(info)
        self.assertNotIn("f013c4b942cf4bf48d94f0a7fa3f08a3", dumped)
        self.assertNotIn("699d349eca2741b9ac7a8c7af201d005", dumped)
        self.assertNotIn("TEST-SERIAL-999", dumped)
        for forbidden_key in ("machine_id", "boot_id", "serial", "mac", "ip"):
            self.assertNotIn(forbidden_key, info)

    def test_cli_power_state_and_system_info(self) -> None:
        from backend.cli import main as cli_main

        runner = FakePowerRunner(self.fx, sysfs_root=self.sysfs_root)
        with mock.patch("backend.settings.power.state.run_live_cmd", side_effect=lambda argv, **kw: runner(list(argv), timeout=kw.get("timeout", 5.0))):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli_main(["settings", "power", "state", "--json"])
            self.assertEqual(rc, 0)
            self.assertTrue(json.loads(buf.getvalue())["available"])

            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                rc2 = cli_main(["settings", "system", "info", "--json"])
            self.assertEqual(rc2, 0)
            self.assertEqual(json.loads(buf2.getvalue())["hostname"], "arch-del")
