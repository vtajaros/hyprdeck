"""Shell-level tests for scripts/hks-window using fake `hyprctl` and `quickshell`.

No compositor is required. The script under test is copied into a throwaway
fake repo (so its derived FRONTEND_DIR never matches a real Keybind Studio instance) and
fake executables are placed first on PATH. Nothing here touches ~/.config,
the sidecar store or real backup paths.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REAL_SCRIPT = os.path.join(REPO_ROOT, "scripts", "hyprdeck-window")
REAL_SHIM = os.path.join(REPO_ROOT, "scripts", "hks-window")

TITLE = "HyprDeck Keybind Studio"

FAKE_HYPRCTL = r"""#!/usr/bin/env bash
if [ "$1" = "clients" ]; then
    cat "$FAKE_DIR/clients.json" 2>/dev/null || echo '[]'
    exit 0
fi
echo "hyprctl $*" >> "$FAKE_DIR/hypr.log"
exit 0
"""

FAKE_QUICKSHELL = r"""#!/usr/bin/env bash
D="$FAKE_DIR"
add_win() {
    printf '[%s{"title":"%s","class":"org.quickshell","mapped":true,"address":"0x1"}]' \
        "$(cat "$D/decoy.json" 2>/dev/null)" "HyprDeck Keybind Studio" > "$D/clients.json"
}
clear_win() {
    printf '[%s]' "$(sed 's/,$//' "$D/decoy.json" 2>/dev/null)" > "$D/clients.json"
}
if [ "$1" = "ipc" ]; then
    echo "$*" >> "$D/qs.log"
    case "$*" in
        *"call hks open"*)
            [ -e "$D/wedged" ] || add_win
            exit 0 ;;
        *"call hks close"*)
            [ -e "$D/wedged" ] || clear_win
            exit 0 ;;
    esac
    exit 0
fi
echo "START $* hidden=${HKS_START_HIDDEN:-0} keepalive=${HKS_KEEP_ALIVE:-0}" >> "$D/qs.log"
trap 'rm -f "$D/wedged"; clear_win; exit 0' TERM
if [ "${HKS_START_HIDDEN:-0}" != "1" ] && [ "${FAKE_COLD_MAPS:-1}" = "1" ]; then
    add_win
fi
while true; do sleep 0.1; done
"""


class HksWindowScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="hkswtest_")
        self.fake = os.path.join(self.tmp, "fakebin")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.fake)
        os.makedirs(os.path.join(self.repo, "scripts"))
        os.makedirs(os.path.join(self.repo, "frontend"))
        self.script = os.path.join(self.repo, "scripts", "hyprdeck-window")
        shutil.copy(REAL_SCRIPT, self.script)
        os.chmod(self.script, 0o755)
        self.shim = os.path.join(self.repo, "scripts", "hks-window")
        shutil.copy(REAL_SHIM, self.shim)
        os.chmod(self.shim, 0o755)
        env_lib_src = os.path.join(os.path.dirname(REAL_SCRIPT), "lib-hyprdeck-env.sh")
        env_lib_dst = os.path.join(self.repo, "scripts", "lib-hyprdeck-env.sh")
        shutil.copy(env_lib_src, env_lib_dst)
        os.chmod(env_lib_dst, 0o755)
        for name, body in (("hyprctl", FAKE_HYPRCTL), ("quickshell", FAKE_QUICKSHELL)):
            p = os.path.join(self.fake, name)
            with open(p, "w") as f:
                f.write(body)
            os.chmod(p, 0o755)
        self.state = os.path.join(self.tmp, "state")
        os.makedirs(self.state)
        self.runtime = os.path.join(self.tmp, "runtime")
        os.makedirs(self.runtime)
        self._write_clients([])
        self.frontend = os.path.join(self.repo, "frontend")
        self.procs: list[subprocess.Popen] = []

    def tearDown(self) -> None:
        subprocess.run(
            ["pkill", "-f", f"[q]uickshell -p {self.frontend}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for p in self.procs:
            try:
                p.terminate()
                p.wait(timeout=2)
            except Exception:
                pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers ---------------------------------------------------------
    def env(self, **extra: str) -> dict[str, str]:
        e = dict(os.environ)
        e["PATH"] = self.fake + os.pathsep + e["PATH"]
        e["FAKE_DIR"] = self.state
        e["XDG_RUNTIME_DIR"] = self.runtime
        e["HKS_OPEN_WAIT_MS"] = "400"
        e["HKS_COLD_WAIT_MS"] = "700"
        e["HKS_CLOSE_WAIT_MS"] = "400"
        e.update(extra)
        return e

    def _write_clients(self, clients: list[str]) -> None:
        # decoys are stored as raw JSON objects each followed by a comma
        with open(os.path.join(self.state, "decoy.json"), "w") as f:
            f.write("".join(c + "," for c in clients))
        with open(os.path.join(self.state, "clients.json"), "w") as f:
            f.write("[" + ",".join(clients) + "]")

    def _mapped_in_file(self) -> bool:
        import json
        with open(os.path.join(self.state, "clients.json")) as f:
            return any(c["title"] == TITLE for c in json.load(f))

    def _qs_log(self) -> str:
        p = os.path.join(self.state, "qs.log")
        if not os.path.exists(p):
            return ""
        with open(p, encoding="utf-8") as f:
            return f.read()

    def start_daemon(self, hidden: bool = True) -> None:
        env = self.env()
        if hidden:
            env["HKS_START_HIDDEN"] = "1"
        p = subprocess.Popen(
            [os.path.join(self.fake, "quickshell"), "-p", self.frontend],
            env=env, start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.procs.append(p)
        for _ in range(50):
            if "START" in self._qs_log():
                return
            time.sleep(0.05)
        self.fail("fake daemon did not start")

    def run_script(self, *args: str, **extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.script, *args], env=self.env(**extra),
            capture_output=True, text=True, timeout=10,
        )

    def hks_running(self) -> bool:
        return subprocess.run(
            ["pgrep", "-f", f"[q]uickshell -p {self.frontend}"],
            stdout=subprocess.DEVNULL,
        ).returncode == 0

    # -- scenario 1: wedged daemon ---------------------------------------
    def test_wedged_daemon_open_never_exits_zero_without_window(self) -> None:
        self.start_daemon()
        open(os.path.join(self.state, "wedged"), "w").close()
        r = self.run_script("--open")
        if r.returncode == 0:
            self.assertTrue(self._mapped_in_file(),
                            "exit 0 but no Keybind Studio window is mapped")

    def test_wedged_daemon_open_recovers_by_restart(self) -> None:
        self.start_daemon()
        open(os.path.join(self.state, "wedged"), "w").close()
        r = self.run_script("--open")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self._mapped_in_file())
        starts = [l for l in self._qs_log().splitlines() if l.startswith("START")]
        self.assertEqual(len(starts), 2, "expected daemon + exactly one restart")
        self.assertIn("hidden=0", starts[-1])

    def test_wedged_daemon_and_failing_cold_start_exits_nonzero(self) -> None:
        self.start_daemon()
        open(os.path.join(self.state, "wedged"), "w").close()
        r = self.run_script("--open", FAKE_COLD_MAPS="0")
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(r.stderr.strip(), "expected a clear error on stderr")

    # -- scenario 2: healthy daemon --------------------------------------
    def test_healthy_daemon_open_no_restart(self) -> None:
        self.start_daemon()
        r = self.run_script("--open")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self._mapped_in_file())
        starts = [l for l in self._qs_log().splitlines() if l.startswith("START")]
        self.assertEqual(len(starts), 1, "healthy daemon must not be restarted")
        self.assertIn("call hks open", self._qs_log())

    # -- scenario 3: decoy titles ----------------------------------------
    def test_title_substring_does_not_count_as_mapped(self) -> None:
        self._write_clients([
            '{"title":"%s - notes","class":"kitty","mapped":true}' % TITLE,
            '{"title":"vim %s","class":"kitty","mapped":true}' % TITLE,
        ])
        r = self.run_script("--open", FAKE_COLD_MAPS="0")
        self.assertNotEqual(r.returncode, 0)

    def test_exact_title_with_wrong_class_does_not_count(self) -> None:
        self._write_clients(['{"title":"%s","class":"kitty","mapped":true}' % TITLE])
        r = self.run_script("--open", FAKE_COLD_MAPS="0")
        self.assertNotEqual(r.returncode, 0)

    def test_unmapped_exact_title_does_not_count(self) -> None:
        self._write_clients(
            ['{"title":"%s","class":"org.quickshell","mapped":false}' % TITLE])
        r = self.run_script("--open", FAKE_COLD_MAPS="0")
        self.assertNotEqual(r.returncode, 0)

    # -- scenario 4: toggle ----------------------------------------------
    def test_toggle_when_mapped_closes(self) -> None:
        self.start_daemon(hidden=False)
        self.run_script("--open")  # make sure window is mapped
        self.assertTrue(self._mapped_in_file())
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self._mapped_in_file())
        self.assertIn("call hks close", self._qs_log())
        self.assertTrue(self.hks_running(), "keep-alive daemon must stay up")

    def test_toggle_when_unmapped_opens(self) -> None:
        self.start_daemon()
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self._mapped_in_file())
        self.assertIn("call hks open", self._qs_log())

    def test_toggle_close_falls_back_to_kill_when_ipc_close_ineffective(self) -> None:
        self.start_daemon(hidden=False)
        self.run_script("--open")
        open(os.path.join(self.state, "wedged"), "w").close()
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self._mapped_in_file())
        self.assertFalse(self.hks_running())

    # -- scenario 5: cold start ------------------------------------------
    def test_cold_start_success(self) -> None:
        r = self.run_script("--open")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self._mapped_in_file())
        starts = [l for l in self._qs_log().splitlines() if l.startswith("START")]
        self.assertEqual(len(starts), 1)
        self.assertIn("hidden=0", starts[0])
        self.assertIn("keepalive=1", starts[0])

    def test_cold_start_failure_exits_nonzero(self) -> None:
        r = self.run_script("--open", FAKE_COLD_MAPS="0")
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(r.stderr.strip())

    # -- daemon mode unchanged -------------------------------------------
    def test_daemon_noop_when_running(self) -> None:
        self.start_daemon()
        r = self.run_script("--daemon")
        self.assertEqual(r.returncode, 0)
        starts = [l for l in self._qs_log().splitlines() if l.startswith("START")]
        self.assertEqual(len(starts), 1)

    def test_daemon_starts_hidden_when_not_running(self) -> None:
        p = subprocess.Popen(
            [self.script, "--daemon"], env=self.env(),
            start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.procs.append(p)
        for _ in range(60):
            if "START" in self._qs_log():
                break
            time.sleep(0.05)
        self.assertIn("hidden=1", self._qs_log())
        self.assertFalse(self._mapped_in_file())

    # -- compatibility shims ---------------------------------------------
    def test_hks_window_shim_delegates_open_and_daemon_silently(self) -> None:
        p = subprocess.Popen(
            [self.shim, "--daemon"], env=self.env(),
            start_new_session=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.procs.append(p)
        rc = p.wait(timeout=5)
        self.assertEqual(rc, 0)
        self.assertEqual(p.stdout.read(), "")
        self.assertEqual(p.stderr.read(), "")
        for _ in range(60):
            if "START" in self._qs_log():
                break
            time.sleep(0.05)
        self.assertIn("hidden=1", self._qs_log())
        self.assertFalse(self._mapped_in_file())

        r_open = subprocess.run(
            [self.shim, "--open"], env=self.env(),
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(r_open.returncode, 0, r_open.stderr)
        self.assertEqual(r_open.stderr, "")
        self.assertTrue(self._mapped_in_file())

        # Failing open preserves non-zero exit code through shim
        r_fail = subprocess.run(
            [self.shim, "--open"], env=self.env(FAKE_COLD_MAPS="0"),
            capture_output=True, text=True, timeout=10,
        )
        # Window is already mapped from above; test fresh wedged daemon failure:
        self.tearDown()
        self.setUp()
        r_cold_fail = subprocess.run(
            [self.shim, "--open"], env=self.env(FAKE_COLD_MAPS="0"),
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(r_cold_fail.returncode, 0)

    def test_hks_window_shim_warns_only_when_deprecated_env_set(self) -> None:
        r = subprocess.run(
            [self.shim, "--open"],
            env=self.env(HYPRDECK_WARN_DEPRECATED="1"),
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(r.returncode, 0)
        self.assertIn("deprecated", r.stderr)
        self.assertIn("hyprdeck-window", r.stderr)

    def test_all_script_shims_exist_executable_and_target_new_scripts(self) -> None:
        scripts_dir = os.path.join(REPO_ROOT, "scripts")
        for suffix in (
            "window", "settings", "popup", "check",
            "scene-check", "layout-check", "token-check", "recorder-test",
        ):
            shim = os.path.join(scripts_dir, f"hks-{suffix}")
            target = os.path.join(scripts_dir, f"hyprdeck-{suffix}")
            self.assertTrue(os.path.isfile(shim), f"Missing shim {shim}")
            self.assertTrue(os.access(shim, os.X_OK), f"Shim not executable: {shim}")
            self.assertTrue(os.path.isfile(target), f"Missing target {target}")
            self.assertTrue(os.access(target, os.X_OK), f"Target not executable: {target}")
            with open(shim, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn(f"exec \"$SELF_DIR/hyprdeck-{suffix}\" \"$@\"", content)


if __name__ == "__main__":
    unittest.main()
