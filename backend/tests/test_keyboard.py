"""One-behavior unit tests for backend.settings.keyboard (no real hks-window or hyprctl)."""

from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stdout
from unittest import mock

from backend.core.constants import ENV_WINDOW_SCRIPT
from backend.core.live_cmd import LiveCmdResult
from backend.tests.isolation import IsolatedTestCase


class FakeKeyboardRunner:
    """In-memory fake runner for hyprctl, pgrep, and hks-window."""

    def __init__(self, *, clients: list[dict] | None = None, pgrep_ok: bool = True) -> None:
        self.clients = clients if clients is not None else []
        self.pgrep_ok = pgrep_ok
        self.hyprctl_ok = True
        self.hyprctl_raw_override: str | None = None
        self.open_rc = 0
        self.open_timed_out = False
        self.open_err = ""
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], timeout: float = 5.0) -> LiveCmdResult:
        self.calls.append(list(argv))
        if argv == ["hyprctl", "clients", "-j"]:
            if not self.hyprctl_ok:
                return LiveCmdResult(ok=False, rc=127, out="", err="hyprctl not found")
            out = self.hyprctl_raw_override if self.hyprctl_raw_override is not None else json.dumps(self.clients)
            return LiveCmdResult(ok=True, rc=0, out=out, err="")
        if len(argv) >= 2 and argv[0] == "pgrep":
            return LiveCmdResult(ok=self.pgrep_ok, rc=0 if self.pgrep_ok else 1, out="1234\n" if self.pgrep_ok else "", err="")
        if argv and os.path.basename(argv[0]) in ("hyprdeck-window", "hks-window"):
            if self.open_timed_out:
                return LiveCmdResult(ok=False, rc=-1, out="", err="timed out", timed_out=True)
            if self.open_rc != 0:
                return LiveCmdResult(ok=False, rc=self.open_rc, out="", err=self.open_err or "failed")
            self.clients = [{"class": "org.quickshell", "title": "HyprDeck Keybind Studio", "mapped": True}]
            return LiveCmdResult(ok=True, rc=0, out="", err="")
        return LiveCmdResult(ok=False, rc=1, out="", err=f"Unexpected command: {argv!r}")


class _KeyboardTestBase(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.fake_script = os.path.join(self._isolated_root, "hyprdeck-window")
        with open(self.fake_script, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(self.fake_script, 0o755)
        os.environ[ENV_WINDOW_SCRIPT] = self.fake_script


class TestKeyboardIsolation(_KeyboardTestBase):
    def test_isolation_guard_blocks_unmocked_hks_window_and_hyprctl(self) -> None:
        import backend.settings.keyboard.ops as kb_ops
        import backend.settings.keyboard.state as kb_state

        with self.assertRaises(AssertionError):
            kb_state.probe_hks_window_open()
        with self.assertRaises(AssertionError):
            kb_ops.open_hks(script_path=self.fake_script)


class TestKeyboardState(_KeyboardTestBase):
    def test_state_script_present_and_executable(self) -> None:
        import backend.settings.keyboard.state as kb_state

        st = kb_state.get_keyboard_state(script_path=self.fake_script, runner=FakeKeyboardRunner())
        self.assertTrue(st["available"])
        self.assertEqual(st["script_path"], self.fake_script)

    def test_state_script_absent_or_non_executable(self) -> None:
        import backend.settings.keyboard.state as kb_state

        missing = os.path.join(self._isolated_root, "missing-hks-window")
        st_miss = kb_state.get_keyboard_state(script_path=missing, runner=FakeKeyboardRunner())
        self.assertFalse(st_miss["available"])

        os.chmod(self.fake_script, 0o644)
        st_noexec = kb_state.get_keyboard_state(script_path=self.fake_script, runner=FakeKeyboardRunner())
        self.assertFalse(st_noexec["available"])

    def test_state_window_open_from_hyprctl_json(self) -> None:
        import backend.settings.keyboard.state as kb_state

        runner = FakeKeyboardRunner(
            clients=[{"class": "org.quickshell", "title": "HyprDeck Keybind Studio", "mapped": True}],
            pgrep_ok=True,
        )
        st = kb_state.get_keyboard_state(script_path=self.fake_script, runner=runner)
        self.assertTrue(st["hks_window_open"])
        self.assertTrue(st["hks_running"])

    def test_state_window_not_open_from_hyprctl_json(self) -> None:
        import backend.settings.keyboard.state as kb_state

        runner = FakeKeyboardRunner(
            clients=[{"class": "kitty", "title": "HyprDeck Keybind Studio", "mapped": True}],
            pgrep_ok=False,
        )
        st = kb_state.get_keyboard_state(script_path=self.fake_script, runner=runner)
        self.assertFalse(st["hks_window_open"])
        self.assertFalse(st["hks_running"])

    def test_state_malformed_hyprctl_json_tolerated(self) -> None:
        import backend.settings.keyboard.state as kb_state

        runner = FakeKeyboardRunner()
        runner.hyprctl_raw_override = "{not json"
        st = kb_state.get_keyboard_state(script_path=self.fake_script, runner=runner)
        self.assertIsNone(st["hks_window_open"])

    def test_state_hyprctl_missing_tolerated(self) -> None:
        import backend.settings.keyboard.state as kb_state

        runner = FakeKeyboardRunner()
        runner.hyprctl_ok = False
        st = kb_state.get_keyboard_state(script_path=self.fake_script, runner=runner)
        self.assertIsNone(st["hks_window_open"])


class TestKeyboardOpsAndCLI(_KeyboardTestBase):
    def test_open_hks_success_and_exact_argv(self) -> None:
        import backend.settings.keyboard.ops as kb_ops

        runner = FakeKeyboardRunner()
        res = kb_ops.open_hks(script_path=self.fake_script, runner=runner)
        self.assertTrue(res["ok"])
        self.assertIsNone(res["error"])
        self.assertTrue(res["window_open_after"])
        self.assertEqual(runner.calls[0], [self.fake_script, "--open"])

    def test_open_hks_nonzero_rc_returns_error(self) -> None:
        import backend.settings.keyboard.ops as kb_ops

        runner = FakeKeyboardRunner()
        runner.open_rc = 1
        runner.open_err = "window did not map"
        res = kb_ops.open_hks(script_path=self.fake_script, runner=runner)
        self.assertFalse(res["ok"])
        self.assertIn("window did not map", res["error"])
        self.assertFalse(res["window_open_after"])

    def test_open_hks_missing_script_returns_error_without_running(self) -> None:
        import backend.settings.keyboard.ops as kb_ops

        runner = FakeKeyboardRunner()
        missing = os.path.join(self._isolated_root, "missing-hks-window")
        res = kb_ops.open_hks(script_path=missing, runner=runner)
        self.assertFalse(res["ok"])
        self.assertIn("missing", res["error"].lower())
        self.assertEqual(runner.calls, [])

    def test_open_hks_timeout_returns_clear_message(self) -> None:
        import backend.settings.keyboard.ops as kb_ops

        runner = FakeKeyboardRunner()
        runner.open_timed_out = True
        res = kb_ops.open_hks(script_path=self.fake_script, runner=runner)
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "HKS window did not appear")

    def test_open_hks_runner_never_gets_shell_or_string_argv(self) -> None:
        import backend.settings.keyboard.ops as kb_ops

        runner = FakeKeyboardRunner()
        seen_kwargs: list[dict] = []

        def spying_run(argv, **kwargs):
            self.assertIsInstance(argv, list)
            seen_kwargs.append(dict(kwargs))
            return runner(argv, timeout=kwargs.get("timeout", 8.0))

        with mock.patch.object(kb_ops, "run_live_cmd", side_effect=spying_run):
            res = kb_ops.open_hks(script_path=self.fake_script, runner=runner)
        self.assertTrue(res["ok"])
        for kw in seen_kwargs:
            self.assertNotIn("shell", kw)

    def test_cli_keyboard_state_and_open(self) -> None:
        from backend.cli import main as cli_main

        runner = FakeKeyboardRunner(
            clients=[{"class": "org.quickshell", "title": "HyprDeck Keybind Studio", "mapped": True}],
            pgrep_ok=True,
        )
        with mock.patch("backend.settings.keyboard.state.run_live_cmd", side_effect=lambda argv, **kw: runner(list(argv), timeout=kw.get("timeout", 5.0))):
            with mock.patch("backend.settings.keyboard.ops.run_live_cmd", side_effect=lambda argv, **kw: runner(list(argv), timeout=kw.get("timeout", 8.0))):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cli_main(["settings", "keyboard", "state", "--json"])
                self.assertEqual(rc, 0)
                self.assertTrue(json.loads(buf.getvalue())["hks_window_open"])

                buf2 = io.StringIO()
                with redirect_stdout(buf2):
                    rc2 = cli_main(["settings", "keyboard", "open", "--json"])
                self.assertEqual(rc2, 0)
                self.assertTrue(json.loads(buf2.getvalue())["ok"])
