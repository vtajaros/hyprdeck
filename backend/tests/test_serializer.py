"""Unit tests for deterministic JSON serialization and schema validation."""

from __future__ import annotations

import json
import os
import unittest

from backend.discovery import discover_config
from backend.parser.lua_normalizer import parse_lua_config
from backend.serializer import (
    format_summary_table,
    make_scan_document,
    serialize_scan_document,
)
from backend.validation import (
    SchemaValidationError,
    assert_valid_scan_dict,
)

FIXTURE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "fixtures", "lua_user_like")
)


class TestSerializer(unittest.TestCase):
    def _scan_fixture(self) -> tuple[str, dict]:
        disc = discover_config(config_dir=FIXTURE_DIR, no_live=True)
        binds, files, diags, stats, complete = parse_lua_config(
            entrypoint=disc.environment.entrypoint,
            config_dir=disc.environment.config_dir,
        )
        doc = make_scan_document(
            environment=disc.environment,
            files=files,
            binds=binds,
            unbinds=[],
            diagnostics=[*disc.diagnostics, *diags],
            stats=stats,
            complete=complete,
        )
        raw = serialize_scan_document(doc)
        return raw, json.loads(raw)

    def test_deterministic_output_and_stable_unique_ids(self) -> None:
        _, dict1 = self._scan_fixture()
        _, dict2 = self._scan_fixture()

        # Normalize generated_at before comparing full JSON strings
        dict1["generated_at"] = "2026-11-07T00:00:00Z"
        dict2["generated_at"] = "2026-11-07T00:00:00Z"
        self.assertEqual(
            json.dumps(dict1, sort_keys=True),
            json.dumps(dict2, sort_keys=True),
        )

        assert_valid_scan_dict(dict1)

        ids1 = [b["id"] for b in dict1["binds"]]
        ids2 = [b["id"] for b in dict2["binds"]]
        self.assertEqual(ids1, ids2)
        self.assertEqual(len(ids1), len(set(ids1)))

    def test_schema_validator_rejects_invalid_document(self) -> None:
        _, valid_dict = self._scan_fixture()
        broken = dict(valid_dict)
        broken["schema_version"] = 999
        with self.assertRaises(SchemaValidationError):
            assert_valid_scan_dict(broken)

    def test_summary_table_formatting(self) -> None:
        disc = discover_config(config_dir=FIXTURE_DIR, no_live=True)
        binds, files, diags, stats, complete = parse_lua_config(
            entrypoint=disc.environment.entrypoint,
            config_dir=disc.environment.config_dir,
        )
        doc = make_scan_document(
            environment=disc.environment,
            files=files,
            binds=binds,
            unbinds=[],
            diagnostics=diags,
            stats=stats,
            complete=complete,
        )
        table = format_summary_table(doc)
        self.assertIn("SHORTCUT", table)
        self.assertIn("DISPATCHER", table)
        self.assertIn("SUPER + Return", table)


if __name__ == "__main__":
    unittest.main()
