"""Unit tests for Phase 2b-0 conflict detection in HyprDeck."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from backend.cli import main, run_scan_pipeline
from backend.conflicts import detect_conflicts
from backend.discovery import discover_config
from backend.models.types import (
    BindRecord,
    DispatcherInfo,
    default_flags,
)
from backend.parser.hyprlang_parser import parse_hyprlang_config
from backend.parser.lua_normalizer import parse_lua_config
from backend.validation import assert_valid_scan_dict

FIXTURES_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "fixtures"))
LUA_FIXTURE_DIR = os.path.join(FIXTURES_ROOT, "lua_user_like")
HYPRLANG_FIXTURE_DIR = os.path.join(FIXTURES_ROOT, "hyprlang_user_like")


def _make_dummy_bind(
    bind_id: str,
    key: str,
    modifiers: list[str],
    modmask: int,
    dsp_path: str,
    arg_summary: str = "",
    submap: str = "",
    release: bool = False,
    long_press: bool = False,
    source_file: str = "hyprland.conf",
    source_line: int = 10,
) -> BindRecord:
    flags = default_flags()
    flags["release"] = release
    flags["long_press"] = long_press
    return BindRecord(
        id=bind_id,
        language="hyprlang",
        bind_type="bind",
        declared_via=None,
        modifiers=modifiers,
        modifiers_raw=" ".join(modifiers),
        modmask=modmask,
        key=key,
        key_kind="keysym",
        keys_raw=key,
        flags=flags,
        flags_extra={},
        description=None,
        dispatcher=DispatcherInfo(path=dsp_path, args=[], arg_summary=arg_summary),
        submap=submap,
        source_file=source_file,
        source_line=source_line,
        original_line=f"bind = {modmask}, {key}, {dsp_path}",
        original_line_number=source_line,
        generated=False,
        occurrence=0,
        occurrences_at_site=1,
        trace=[],
        parse_status="ok",
        conflict_ids=[],
    )


class TestConflictDetection(unittest.TestCase):
    def test_synthetic_multiple_actions(self) -> None:
        b1 = _make_dummy_bind("b1", "Tab", ["ALT"], 8, "cyclenext")
        b2 = _make_dummy_bind("b2", "Tab", ["ALT"], 8, "bringactivetotop")
        conflicts = detect_conflicts([b1, b2])

        self.assertEqual(len(conflicts), 1)
        c = conflicts[0]
        self.assertEqual(c.id, "conflict-1")
        self.assertEqual(c.kind, "multiple_actions")
        self.assertEqual(c.severity, "info")
        self.assertEqual(c.key, "Tab")
        self.assertEqual(c.modifiers, ["ALT"])
        self.assertEqual(c.submap, "")
        self.assertEqual(c.bind_ids, ["b1", "b2"])
        self.assertEqual(b1.conflict_ids, ["conflict-1"])
        self.assertEqual(b2.conflict_ids, ["conflict-1"])

    def test_synthetic_duplicate(self) -> None:
        b1 = _make_dummy_bind("b1", "Return", ["SUPER"], 64, "exec", "kitty")
        b2 = _make_dummy_bind("b2", "Return", ["SUPER"], 64, "exec", "kitty")
        conflicts = detect_conflicts([b1, b2])

        self.assertEqual(len(conflicts), 1)
        c = conflicts[0]
        self.assertEqual(c.id, "conflict-1")
        self.assertEqual(c.kind, "duplicate")
        self.assertEqual(c.severity, "warning")
        self.assertEqual(c.bind_ids, ["b1", "b2"])

    def test_synthetic_mixed_duplicate_and_distinct_worst_severity_wins(self) -> None:
        b1 = _make_dummy_bind("b1", "Return", ["SUPER"], 64, "exec", "kitty")
        b2 = _make_dummy_bind("b2", "Return", ["SUPER"], 64, "exec", "kitty")
        b3 = _make_dummy_bind("b3", "Return", ["SUPER"], 64, "exec", "alacritty")
        conflicts = detect_conflicts([b1, b2, b3])

        self.assertEqual(len(conflicts), 1)
        c = conflicts[0]
        self.assertEqual(c.kind, "duplicate")
        self.assertEqual(c.severity, "warning")
        self.assertEqual(c.bind_ids, ["b1", "b2", "b3"])

    def test_press_vs_release_no_conflict(self) -> None:
        b1 = _make_dummy_bind("b1", "A", ["SUPER"], 64, "exec", "press_cmd", release=False)
        b2 = _make_dummy_bind("b2", "A", ["SUPER"], 64, "exec", "release_cmd", release=True)
        conflicts = detect_conflicts([b1, b2])
        self.assertEqual(conflicts, [])
        self.assertEqual(b1.conflict_ids, [])
        self.assertEqual(b2.conflict_ids, [])

    def test_long_press_vs_press_no_conflict(self) -> None:
        b1 = _make_dummy_bind("b1", "B", ["SUPER"], 64, "exec", "normal", long_press=False)
        b2 = _make_dummy_bind("b2", "B", ["SUPER"], 64, "exec", "long", long_press=True)
        conflicts = detect_conflicts([b1, b2])
        self.assertEqual(conflicts, [])

    def test_different_modmask_or_submap_no_conflict(self) -> None:
        b1 = _make_dummy_bind("b1", "C", ["SUPER"], 64, "exec", "cmd1")
        b2 = _make_dummy_bind("b2", "C", ["SUPER", "SHIFT"], 65, "exec", "cmd1")
        b3 = _make_dummy_bind("b3", "C", ["SUPER"], 64, "exec", "cmd1", submap="resize")
        conflicts = detect_conflicts([b1, b2, b3])
        self.assertEqual(conflicts, [])

    def test_key_case_insensitivity(self) -> None:
        b1 = _make_dummy_bind("b1", "Tab", ["ALT"], 8, "cyclenext")
        b2 = _make_dummy_bind("b2", "tab", ["ALT"], 8, "bringactivetotop")
        conflicts = detect_conflicts([b1, b2])
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].bind_ids, ["b1", "b2"])

    def test_lua_user_like_conflicts(self) -> None:
        doc, rc = run_scan_pipeline(
            config_dir=LUA_FIXTURE_DIR,
            no_live=True,
            no_sidecar=True,
        )
        self.assertEqual(rc, 0)
        self.assertTrue(doc.complete)
        self.assertEqual(doc.stats.conflicts.total, 2)
        self.assertEqual(doc.stats.conflicts.duplicate, 0)
        self.assertEqual(doc.stats.conflicts.multiple_actions, 2)
        self.assertEqual(len(doc.conflicts), 2)

        c1 = doc.conflicts[0]
        self.assertEqual(c1.id, "conflict-1")
        self.assertEqual(c1.kind, "multiple_actions")
        self.assertEqual(c1.severity, "info")
        self.assertEqual(c1.modifiers, ["ALT"])
        self.assertEqual(c1.key, "Tab")
        self.assertEqual(len(c1.bind_ids), 2)

        c2 = doc.conflicts[1]
        self.assertEqual(c2.id, "conflict-2")
        self.assertEqual(c2.kind, "multiple_actions")
        self.assertEqual(c2.severity, "info")
        self.assertEqual(c2.modifiers, ["ALT", "SHIFT"])
        self.assertEqual(c2.key, "Tab")
        self.assertEqual(len(c2.bind_ids), 2)

        assert_valid_scan_dict(doc.to_dict())

    def test_hyprlang_parity_and_schema_validation(self) -> None:
        doc_lua, rc_lua = run_scan_pipeline(
            config_dir=LUA_FIXTURE_DIR,
            no_live=True,
            no_sidecar=True,
        )
        self.assertEqual(rc_lua, 0)

        doc_hypr, rc_hypr = run_scan_pipeline(
            config_dir=HYPRLANG_FIXTURE_DIR,
            no_live=True,
            no_sidecar=True,
        )
        self.assertEqual(rc_hypr, 0)

        self.assertEqual(doc_lua.stats.conflicts.total, doc_hypr.stats.conflicts.total)
        self.assertEqual(doc_lua.stats.conflicts.duplicate, doc_hypr.stats.conflicts.duplicate)
        self.assertEqual(
            doc_lua.stats.conflicts.multiple_actions,
            doc_hypr.stats.conflicts.multiple_actions,
        )
        self.assertEqual(len(doc_lua.conflicts), len(doc_hypr.conflicts))

        for c_lua, c_hypr in zip(doc_lua.conflicts, doc_hypr.conflicts):
            self.assertEqual(c_lua.id, c_hypr.id)
            self.assertEqual(c_lua.kind, c_hypr.kind)
            self.assertEqual(c_lua.severity, c_hypr.severity)
            self.assertEqual(c_lua.key.lower(), c_hypr.key.lower())
            self.assertEqual(set(c_lua.modifiers), set(c_hypr.modifiers))
            self.assertEqual(len(c_lua.bind_ids), len(c_hypr.bind_ids))

        assert_valid_scan_dict(doc_lua.to_dict())
        assert_valid_scan_dict(doc_hypr.to_dict())


class TestConflictsCLI(unittest.TestCase):
    def test_cli_conflicts_table_output(self) -> None:
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = main(
                [
                    "conflicts",
                    "--config-dir",
                    LUA_FIXTURE_DIR,
                    "--no-live",
                    "--no-sidecar",
                ]
            )
        self.assertEqual(rc, 0)
        output = out_buf.getvalue()
        self.assertIn("Conflicts: 2 total (0 duplicate, 2 multiple_actions)", output)
        self.assertIn("ID", output)
        self.assertIn("SEVERITY", output)
        self.assertIn("KIND", output)
        self.assertIn("SHORTCUT", output)
        self.assertIn("BINDS", output)
        self.assertIn("SOURCES", output)
        self.assertIn("conflict-1", output)
        self.assertIn("ALT + Tab", output)
        self.assertIn("conflict-2", output)
        self.assertIn("ALT + SHIFT + Tab", output)
        self.assertIn("multiple_actions", output)

    def test_cli_conflicts_none_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = os.path.join(tmpdir, "hyprland.conf")
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write("bind = SUPER, Return, exec, kitty\n")

            out_buf = io.StringIO()
            with redirect_stdout(out_buf), redirect_stderr(io.StringIO()):
                rc = main(
                    [
                        "conflicts",
                        "--config-dir",
                        tmpdir,
                        "--no-live",
                        "--no-sidecar",
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertEqual(out_buf.getvalue().strip(), "No conflicts found.")

    def test_cli_conflicts_error_exit(self) -> None:
        with tempfile.TemporaryDirectory() as empty_dir:
            err_buf = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err_buf):
                rc = main(
                    [
                        "conflicts",
                        "--config-dir",
                        empty_dir,
                        "--no-live",
                    ]
                )
            self.assertEqual(rc, 2)
            self.assertNotIn("Traceback", err_buf.getvalue())
            self.assertIn("hks: error:", err_buf.getvalue())


if __name__ == "__main__":
    unittest.main()
