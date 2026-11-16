"""Unit tests for HyprDeck Phase 3b-2."""

from __future__ import annotations

import io
import json
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from backend.cli import main, run_scan_pipeline
from backend.conflicts import check_candidate_conflict, normalize_key
from backend.discovery.config_discovery import probe_hyprctl_binds
from backend.editor import (
    apply_edit,
    enter_submap,
    get_catalog,
    get_dispatcher_by_id,
    leave_submap,
    render_from_catalog,
    resolve_replace_op,
)
from backend.editor.codegen import generate_hyprlang_bind, generate_lua_bind
from backend.editor.recorder_submap import (
    DUMMY_KEY_CANDIDATES,
    HYPRDECK_RECORD_SUBMAP,
    get_free_dummy_key,
)
from backend.models.types import BindRecord, DispatcherInfo
from backend.validation.oracle import compare_with_oracle


def _make_dummy_bind(
    bind_id: str,
    mods: list[str],
    key: str,
    modmask: int,
    dsp: str = "exec_cmd",
    args: str | None = None,
    original_line: str = "",
    submap: str = "",
) -> BindRecord:
    return BindRecord(
        id=bind_id,
        language="lua",
        bind_type="bind",
        declared_via="bind",
        modifiers=mods,
        modifiers_raw=" + ".join(mods),
        modmask=modmask,
        key=key,
        key_kind="keysym",
        keys_raw=" + ".join(mods + [key]),
        flags={},
        flags_extra={},
        description=None,
        dispatcher=DispatcherInfo(
            path=dsp,
            args=[args] if args else [],
            arg_summary=args or "",
        ),
        submap=submap,
        source_file="/tmp/dummy/hyprland.lua",
        source_line=10,
        original_line=original_line,
        original_line_number=10,
        generated=False,
        occurrence=0,
        occurrences_at_site=1,
        trace=[],
        parse_status="ok",
        args_raw=args or "",
    )


class TestPhase3b2Part0Recorder(unittest.TestCase):
    """Test recorder submap improvements (dynamic free key, reload re-registration, oracle filtering)."""

    def test_get_free_dummy_key_avoids_bound_keys(self) -> None:
        canned_binds = [
            {"key": "XF86Tools", "submap": ""},
            {"key": "XF86Launch5", "submap": ""},
        ]
        mock_runner = MagicMock()
        mock_runner.return_value = subprocess.CompletedProcess(
            args=["hyprctl", "binds", "-j"],
            returncode=0,
            stdout=json.dumps(canned_binds),
            stderr="",
        )
        free_key = get_free_dummy_key(mock_runner)
        self.assertNotIn(free_key, ["XF86Tools", "XF86Launch5"])
        self.assertEqual(free_key, "XF86Launch6")

    def test_enter_re_registers_dummy_submap_every_time(self) -> None:
        calls = []

        def mock_runner(cmd, **kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        res1 = enter_submap(language="lua", runner=mock_runner, dummy_key="XF86Launch7")
        self.assertTrue(res1["ok"])
        self.assertTrue(any("hl.define_submap" in c[2] for c in calls if c[:2] == ["hyprctl", "eval"]))

        # Call enter again (e.g. after reload)
        calls.clear()
        res2 = enter_submap(language="lua", runner=mock_runner, dummy_key="XF86Launch7")
        self.assertTrue(res2["ok"])
        self.assertTrue(any("hl.define_submap" in c[2] for c in calls if c[:2] == ["hyprctl", "eval"]))

    def test_leave_unbinds_only_hks_record_keys(self) -> None:
        canned_binds = [
            {"key": "XF86Tools", "submap": ""},  # User bind in default submap
            {"key": "XF86Launch7", "submap": HYPRDECK_RECORD_SUBMAP},  # Dummy recorder bind
        ]
        calls = []

        def mock_runner(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["hyprctl", "submap"]:
                # First call returns stuck in hks_record, second returns default
                sub = HYPRDECK_RECORD_SUBMAP if len([c for c in calls if c == ["hyprctl", "submap"]]) <= 1 else "default"
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=sub, stderr="")
            if cmd == ["hyprctl", "binds", "-j"]:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=json.dumps(canned_binds), stderr="")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        res = leave_submap(language="lua", runner=mock_runner)
        self.assertTrue(res["ok"])
        unbind_cmds = [c[2] for c in calls if c[:2] == ["hyprctl", "repl"]]
        self.assertIn('hl.unbind("XF86Launch7")', unbind_cmds)
        # Verify user's default XF86Tools was NOT unbound
        self.assertNotIn('hl.unbind("XF86Tools")', unbind_cmds)

    def test_oracle_and_discovery_ignore_hks_record_binds(self) -> None:
        parser_bind = _make_dummy_bind("b1", ["SUPER"], "Q", 64, dsp="exec_cmd", args="firefox")
        live_binds = [
            {
                "modmask": 64,
                "key": "Q",
                "dispatcher": "HL.Dispatcher(exec_cmd)",
                "arg": "firefox",
                "submap": "",
            },
            {
                "modmask": 0,
                "key": "XF86Tools",
                "dispatcher": "HL.Dispatcher(submap)",
                "arg": "reset",
                "submap": "hks_record",
            },
        ]
        report = compare_with_oracle([parser_bind], live_binds)
        self.assertTrue(report.matched)
        self.assertEqual(report.live_count, 1)


class TestPhase3b2Part1Backend(unittest.TestCase):
    """Test dispatcher catalog, preservation, and conflict check."""

    def test_dispatcher_catalog_minimum_coverage(self) -> None:
        catalog = get_catalog()
        ids = {item["id"] for item in catalog}
        required_minimum = {
            "exec_cmd",
            "window.close",
            "togglefloating",
            "fullscreen",
            "workspace",
            "movetoworkspace",
            "movefocus",
            "movewindow",
            "resizeactive",
            "pin",
            "togglesplit",
            "submap",
            "custom",
        }
        for req in required_minimum:
            self.assertIn(req, ids, f"Missing required dispatcher {req}")

    def test_catalog_rendering_lua_and_hyprlang(self) -> None:
        # window.close
        lua_dsp, lua_arg = render_from_catalog("window.close", None, language="lua")
        self.assertEqual(lua_dsp, "window.close")
        hl_dsp, hl_arg = render_from_catalog("window.close", None, language="hyprlang")
        self.assertEqual(hl_dsp, "killactive")

        # movefocus direction
        lua_dsp, _ = render_from_catalog("movefocus", {"direction": "right"}, language="lua")
        self.assertIn('direction = "right"', lua_dsp)
        hl_dsp, hl_arg = render_from_catalog("movefocus", {"direction": "right"}, language="hyprlang")
        self.assertEqual(hl_dsp, "movefocus")
        self.assertEqual(hl_arg, "right")

    def test_dispatch_expression_preservation_variable_arg(self) -> None:
        orig = 'hl.bind(mainMod .. " + Return",         hl.dsp.exec_cmd(terminal))'
        target_b = _make_dummy_bind(
            "b_term", ["SUPER"], "Return", 64, dsp="exec_cmd", args="kitty", original_line=orig
        )
        op, _, expected = resolve_replace_op(
            bind_id="b_term",
            new_mods=["SUPER"],
            new_key="T",
            new_dispatcher=None,
            new_args=None,
            binds=[target_b],
        )
        self.assertTrue(op.dispatcher_unchanged)
        self.assertIn("hl.dsp.exec_cmd(terminal)", op.new_text or "")
        self.assertIn('mainMod .. " + T"', op.new_text or "")

    def test_dispatch_expression_preservation_options_table(self) -> None:
        orig = 'hl.bind("XF86AudioRaiseVolume",          hl.dsp.exec_cmd("quickshell ipc call osd volumeUp 5"),     { locked = true, repeating = true })'
        target_b = _make_dummy_bind(
            "b_vol", [], "XF86AudioRaiseVolume", 0, dsp="exec_cmd", args="quickshell ipc call osd volumeUp 5", original_line=orig
        )
        op, _, _ = resolve_replace_op(
            bind_id="b_vol",
            new_mods=[],
            new_key="XF86Tools",
            new_dispatcher=None,
            new_args=None,
            binds=[target_b],
        )
        self.assertTrue(op.dispatcher_unchanged)
        self.assertIn("{ locked = true, repeating = true }", op.new_text or "")
        self.assertIn('"XF86Tools"', op.new_text or "")

    def test_dispatch_expression_preservation_multiline(self) -> None:
        orig = 'hl.bind("ALT + Tab",\n    hl.dsp.window.cycle_next())'
        target_b = _make_dummy_bind(
            "b_tab", ["ALT"], "Tab", 8, dsp="window.cycle_next", args=None, original_line=orig
        )
        op, _, _ = resolve_replace_op(
            bind_id="b_tab",
            new_mods=["CTRL"],
            new_key="Tab",
            new_dispatcher=None,
            new_args=None,
            binds=[target_b],
        )
        self.assertTrue(op.dispatcher_unchanged)
        self.assertEqual(op.new_text, 'hl.bind("CTRL + Tab",\n    hl.dsp.window.cycle_next())')

    def test_dispatcher_change_regenerates_dispatcher(self) -> None:
        orig = 'hl.bind("SUPER + Q", hl.dsp.window.close())'
        target_b = _make_dummy_bind(
            "b_close", ["SUPER"], "Q", 64, dsp="window.close", args=None, original_line=orig
        )
        op, _, expected = resolve_replace_op(
            bind_id="b_close",
            new_mods=["SUPER"],
            new_key="Q",
            new_dispatcher="exec_cmd",
            new_args="firefox",
            binds=[target_b],
        )
        self.assertFalse(op.dispatcher_unchanged)
        self.assertIn('hl.dsp.exec_cmd("firefox")', op.new_text or "")

    def test_conflict_precheck_exact_and_alias(self) -> None:
        b1 = _make_dummy_bind("b1", ["SUPER"], "Return", 64, dsp="exec_cmd", args="kitty")
        b2 = _make_dummy_bind("b2", ["SUPER"], "grave", 64, dsp="exec_cmd", args="kitty")

        # enter is alias of Return
        res1 = check_candidate_conflict([b1, b2], mods="SUPER", key="enter")
        self.assertTrue(res1["has_conflicts"])
        self.assertEqual(res1["conflicts"][0]["id"], "b1")

        # ` is alias of grave
        res2 = check_candidate_conflict([b1, b2], mods="SUPER", key="`")
        self.assertTrue(res2["has_conflicts"])
        self.assertEqual(res2["conflicts"][0]["id"], "b2")

        # Exclude ID works
        res3 = check_candidate_conflict([b1, b2], mods="SUPER", key="enter", exclude_id="b1")
        self.assertFalse(res3["has_conflicts"])

    def test_conflict_precheck_disabled_bind_held(self) -> None:
        b1 = _make_dummy_bind("b1", ["ALT"], "Tab", 8, dsp="window.cycle_next")
        mock_disabled = MagicMock()
        mock_disabled.id = "d1"
        mock_disabled.key_hint = "ALT + Tab"
        mock_disabled.original_text = '-- hl.bind("ALT + Tab", hl.dsp.window.bring_to_top())'
        mock_disabled.file = "/tmp/dummy/hyprland.lua"
        mock_disabled.line = 20
        mock_disabled.description_hint = "Bring to top"

        res = check_candidate_conflict([b1], mods="ALT", key="Tab", exclude_id="b1", disabled_binds=[mock_disabled])
        self.assertFalse(res["has_conflicts"])
        self.assertTrue(res["disabled_held"])
        self.assertEqual(len(res["disabled_binds"]), 1)
        self.assertEqual(res["disabled_binds"][0]["id"], "d1")

    def test_cli_dispatchers_json(self) -> None:
        out = io.StringIO()
        with patch("sys.stdout", out):
            code = main(["dispatchers", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out.getvalue())
        self.assertTrue(data.get("ok"))
        self.assertIsInstance(data.get("dispatchers"), list)
        self.assertGreaterEqual(len(data["dispatchers"]), 12)


if __name__ == "__main__":
    unittest.main()
