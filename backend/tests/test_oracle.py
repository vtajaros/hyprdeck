"""Unit tests for the Oracle comparator and CLI subcommands (using canned fixtures only)."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from backend.cli import main, run_scan_pipeline
from backend.discovery import discover_config
from backend.parser.lua_normalizer import parse_lua_config
from backend.validation import (
    assert_valid_scan_dict,
    compare_with_oracle,
    extract_parser_short_dispatcher,
)

FIXTURE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "fixtures", "lua_user_like")
)


def _build_canned_live_binds_from_fixture() -> list[dict]:
    """Generate canned `hyprctl binds -j` entries corresponding to the Lua fixture."""
    disc = discover_config(config_dir=FIXTURE_DIR, no_live=True)
    binds, _, _, _, _ = parse_lua_config(
        entrypoint=disc.environment.entrypoint,
        config_dir=disc.environment.config_dir,
    )
    canned: list[dict] = []
    for idx, b in enumerate(binds):
        short_dsp = extract_parser_short_dispatcher(b.dispatcher.path)
        canned.append(
            {
                "locked": b.flags["locked"],
                "mouse": b.flags["mouse"],
                "release": b.flags["release"],
                "repeat": b.flags["repeating"],
                "longPress": b.flags["long_press"],
                "non_consuming": b.flags["non_consuming"],
                "has_description": b.description is not None,
                "modmask": b.modmask,
                "submap": b.submap,
                "key": b.key,
                "keycode": 0,
                "catch_all": False,
                "description": b.description or "",
                "dispatcher": f"HL.Dispatcher({short_dsp})",
                "arg": f"0x7f0000{idx:04x}",  # opaque Lua handle in live hyprctl
            }
        )
    return canned


class TestOracleAndCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.canned_live = _build_canned_live_binds_from_fixture()

    def test_oracle_match_case(self) -> None:
        doc, exit_code = run_scan_pipeline(
            config_dir=FIXTURE_DIR,
            no_live=True,
            with_oracle=True,
            live_binds_override=self.canned_live,
        )
        self.assertEqual(exit_code, 0)
        self.assertIsNotNone(doc.oracle)
        assert doc.oracle is not None
        self.assertTrue(doc.oracle["matched"])
        self.assertTrue(doc.oracle["count_match"])
        self.assertTrue(doc.oracle["order_match"])
        self.assertEqual(doc.oracle["missing_in_parser"], [])
        self.assertEqual(doc.oracle["extra_in_parser"], [])
        assert_valid_scan_dict(doc.to_dict())

    def test_oracle_mismatch_case(self) -> None:
        tampered = list(self.canned_live[:-1])
        tampered.append(
            {
                "locked": False,
                "mouse": False,
                "release": False,
                "repeat": False,
                "non_consuming": False,
                "modmask": 64,
                "submap": "",
                "key": "F12",
                "dispatcher": "HL.Dispatcher(exec_cmd)",
                "arg": "0xdeadbeef",
            }
        )
        doc, exit_code = run_scan_pipeline(
            config_dir=FIXTURE_DIR,
            no_live=True,
            with_oracle=True,
            live_binds_override=tampered,
        )
        self.assertEqual(exit_code, 1)
        assert doc.oracle is not None
        self.assertFalse(doc.oracle["matched"])
        self.assertTrue(doc.oracle["count_match"])
        self.assertEqual(len(doc.oracle["missing_in_parser"]), 1)
        self.assertEqual(doc.oracle["missing_in_parser"][0]["key"], "f12")
        self.assertEqual(len(doc.oracle["extra_in_parser"]), 1)
        self.assertEqual(doc.oracle["extra_in_parser"][0]["key"], "mouse:273")
        assert_valid_scan_dict(doc.to_dict())

    def test_cli_scan_and_summary_and_clean_error_exit(self) -> None:
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = main(["scan", "--config-dir", FIXTURE_DIR, "--no-live", "--compact"])
        self.assertEqual(rc, 0)
        parsed = json.loads(out_buf.getvalue().strip())
        assert_valid_scan_dict(parsed)
        self.assertEqual(parsed["stats"]["total_binds"], 69)

        out_sum = io.StringIO()
        with redirect_stdout(out_sum), redirect_stderr(err_buf):
            rc_sum = main(["summary", "--config-dir", FIXTURE_DIR, "--no-live"])
        self.assertEqual(rc_sum, 0)
        self.assertIn("SHORTCUT", out_sum.getvalue())

        # Empty directory => clean exit code 2 without traceback
        with tempfile.TemporaryDirectory() as empty_dir:
            err_clean = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err_clean):
                rc_err = main(["scan", "--config-dir", empty_dir, "--no-live"])
            self.assertEqual(rc_err, 2)
            self.assertNotIn("Traceback", err_clean.getvalue())
            self.assertIn("hks: error:", err_clean.getvalue())


if __name__ == "__main__":
    unittest.main()
