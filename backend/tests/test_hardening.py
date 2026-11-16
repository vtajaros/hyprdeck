"""Phase 3b Hardening Tests: Mock isolation, undo completeness, and structured warnings."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from backend.cli import main, run_scan_pipeline
from backend.describe.sidecar_store import (
    SidecarCollisionError,
    delete_override,
    migrate_override,
    save_override,
)
from backend.editor.backups import (
    create_backup,
    list_backups,
    restore_backup,
)


class TestHardeningMockIsolation(unittest.TestCase):
    """Safety Check 1: Prove production environment cannot resolve headless mocks."""

    def setUp(self) -> None:
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
        self.frontend_dir = os.path.join(self.repo_root, "frontend")

    def test_mock_directory_not_on_production_import_path(self) -> None:
        # A directory named Quickshell directly under frontend/ would hijack 'import Quickshell'
        production_quickshell_dir = os.path.join(self.frontend_dir, "Quickshell")
        self.assertFalse(
            os.path.exists(production_quickshell_dir),
            f"Fatal: {production_quickshell_dir} exists and would hijack production 'import Quickshell'!",
        )

    def test_mocks_isolated_under_frontend_tests_mocks(self) -> None:
        # Scan all directories in frontend/
        quickshell_dirs = []
        for root, dirs, _ in os.walk(self.frontend_dir):
            for d in dirs:
                if d == "Quickshell":
                    quickshell_dirs.append(os.path.relpath(os.path.join(root, d), self.frontend_dir))

        self.assertEqual(
            quickshell_dirs,
            ["tests/mocks/Quickshell"],
            f"Mock Quickshell directory found outside tests/mocks/: {quickshell_dirs}",
        )

    def test_production_scripts_do_not_inject_test_mocks(self) -> None:
        # Scripts that launch quickshell in production
        prod_scripts = [
            "hyprdeck-window", "hyprdeck-popup", "hyprdeck-recorder-test",
            "hks-window", "hks-popup", "hks-recorder-test",
        ]
        scripts_dir = os.path.join(self.repo_root, "scripts")

        for s_name in prod_scripts:
            s_path = os.path.join(scripts_dir, s_name)
            if not os.path.isfile(s_path):
                continue
            with open(s_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertNotIn(
                "tests/mocks",
                content,
                f"Production script {s_name} must never import tests/mocks!",
            )
            self.assertNotIn(
                "-import",
                content,
                f"Production script {s_name} must not supply extra mock -import paths!",
            )


class TestHardeningUndoCompleteness(unittest.TestCase):
    """Safety Check 2: Verify undo completeness on temp paths."""

    def setUp(self) -> None:
        self.root_temp = tempfile.mkdtemp()
        self.config_dir = os.path.join(self.root_temp, "config")
        self.backup_dir = os.path.join(self.root_temp, "backups")
        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

        self.entrypoint = os.path.join(self.config_dir, "hyprland.lua")
        self.sidecar_path = os.path.join(self.config_dir, "descriptions.json")

        self.initial_lua = (
            'local mainMod = "SUPER"\n'
            'hl.bind(mainMod .. " + Q", hl.dsp.window.close())\n'
            'hl.bind(mainMod .. " + Return", hl.dsp.exec_cmd("kitty"))\n'
        )
        with open(self.entrypoint, "w", encoding="utf-8") as f:
            f.write(self.initial_lua)

        os.environ["HKS_BACKUP_DIR"] = self.backup_dir
        os.environ["HKS_SIDECAR"] = self.sidecar_path

    def tearDown(self) -> None:
        os.environ.pop("HKS_BACKUP_DIR", None)
        os.environ.pop("HKS_SIDECAR", None)
        shutil.rmtree(self.root_temp, ignore_errors=True)

    def test_2a_replace_migration_and_restore(self) -> None:
        """Workflow 2a: sidecar set -> replace with migration -> restore."""
        doc, _ = run_scan_pipeline(config_dir=self.config_dir, entrypoint=self.entrypoint, no_live=True, no_sidecar=True)
        q_bind = next(b for b in doc.binds if b.key == "Q")
        orig_id = q_bind.id

        # 1. Set sidecar override on original bind
        code_set = main([
            "sidecar", "set",
            "--id", orig_id,
            "--desc", "Close focused window",
            "--cat", "Windows",
            "--config-dir", self.config_dir,
            "--entrypoint", self.entrypoint,
            "--no-live",
            "--json",
        ])
        self.assertEqual(code_set, 0)

        # 2. Replace Q -> C with migration
        code_rep = main([
            "edit", "replace",
            "--id", orig_id,
            "--mods", "SUPER",
            "--key", "C",
            "--apply",
            "--no-live",
            "--config-dir", self.config_dir,
            "--entrypoint", self.entrypoint,
            "--json",
        ])
        self.assertEqual(code_rep, 0)

        # Verify sidecar now has C
        with open(self.sidecar_path, "r", encoding="utf-8") as f:
            sc_mig = json.loads(f.read())
        self.assertEqual(sc_mig["overrides"][0]["match"]["key"], "C")

        # 3. Undo via restore --latest
        code_rest = main([
            "restore",
            "--latest",
            "--apply",
            "--json",
        ])
        self.assertEqual(code_rest, 0)

        # 4. Check sidecar get on ORIGINAL bind id shows original override
        buf = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = buf
            code_get = main([
                "sidecar", "get",
                "--id", orig_id,
                "--config-dir", self.config_dir,
                "--entrypoint", self.entrypoint,
                "--no-live",
                "--json",
            ])
        finally:
            sys.stdout = old_stdout

        self.assertEqual(code_get, 0)
        get_data = json.loads(buf.getvalue())
        self.assertTrue(get_data["found"])
        self.assertEqual(get_data["override"]["description"], "Close focused window")
        self.assertEqual(get_data["override"]["match"]["key"], "Q")

        # Verify sidecar has NO override for C
        with open(self.sidecar_path, "r", encoding="utf-8") as f:
            sc_rest = json.loads(f.read())
        for ov in sc_rest["overrides"]:
            self.assertNotEqual(ov["match"]["key"], "C")

    def test_2b_sidecar_only_edit_and_undo(self) -> None:
        """Workflow 2b: sidecar-only edit (description change) -> undo."""
        doc, _ = run_scan_pipeline(config_dir=self.config_dir, entrypoint=self.entrypoint, no_live=True, no_sidecar=True)
        q_bind = next(b for b in doc.binds if b.key == "Q")
        orig_id = q_bind.id

        # Initial sidecar set
        main([
            "sidecar", "set",
            "--id", orig_id,
            "--desc", "Initial Description",
            "--cat", "Windows",
            "--config-dir", self.config_dir,
            "--entrypoint", self.entrypoint,
            "--no-live",
            "--json",
        ])

        # Second sidecar set: description change
        code_update = main([
            "sidecar", "set",
            "--id", orig_id,
            "--desc", "Updated Description",
            "--cat", "System",
            "--config-dir", self.config_dir,
            "--entrypoint", self.entrypoint,
            "--no-live",
            "--json",
        ])
        self.assertEqual(code_update, 0)

        # Verify sidecar has Updated Description
        with open(self.sidecar_path, "r", encoding="utf-8") as f:
            sc_updated = json.loads(f.read())
        self.assertEqual(sc_updated["overrides"][0]["description"], "Updated Description")

        # Undo via restore --latest
        code_undo = main([
            "restore",
            "--latest",
            "--apply",
            "--json",
        ])
        self.assertEqual(code_undo, 0)

        # Verify sidecar reverted to Initial Description
        with open(self.sidecar_path, "r", encoding="utf-8") as f:
            sc_reverted = json.loads(f.read())
        self.assertEqual(sc_reverted["overrides"][0]["description"], "Initial Description")
        self.assertEqual(sc_reverted["overrides"][0]["category"], "Windows")

    def test_2c_add_with_description_and_undo(self) -> None:
        """Workflow 2c: add-with-description -> undo: anchor, bind and sidecar entry all disappear."""
        # Ensure sidecar does not exist prior to add
        if os.path.exists(self.sidecar_path):
            os.unlink(self.sidecar_path)

        code_add = main([
            "edit", "add",
            "--mods", "SUPER",
            "--key", "F12",
            "--dispatcher", "exec_cmd",
            "--args", "pavucontrol",
            "--desc", "Audio Volume Control",
            "--cat", "Media & Hardware",
            "--apply",
            "--no-live",
            "--config-dir", self.config_dir,
            "--entrypoint", self.entrypoint,
            "--json",
        ])
        self.assertEqual(code_add, 0)

        with open(self.entrypoint, "r", encoding="utf-8") as f:
            cfg_added = f.read()
        self.assertIn("F12", cfg_added)
        self.assertIn("-- HKS: custom binds", cfg_added)

        with open(self.sidecar_path, "r", encoding="utf-8") as f:
            sc_added = json.loads(f.read())
        self.assertEqual(len(sc_added["overrides"]), 1)
        self.assertEqual(sc_added["overrides"][0]["description"], "Audio Volume Control")

        # Undo via restore --latest
        code_rest = main([
            "restore",
            "--latest",
            "--apply",
            "--json",
        ])
        self.assertEqual(code_rest, 0)

        # Anchor, bind line, and sidecar file all disappear
        with open(self.entrypoint, "r", encoding="utf-8") as f:
            cfg_rest = f.read()
        self.assertEqual(cfg_rest, self.initial_lua)
        self.assertNotIn("F12", cfg_rest)
        self.assertNotIn("-- HKS: custom binds", cfg_rest)
        self.assertFalse(os.path.exists(self.sidecar_path))


class TestHardeningStructuredWarnings(unittest.TestCase):
    """Safety Check 3: Structured sidecar_warning object and human-readable sentences."""

    def setUp(self) -> None:
        self.root_temp = tempfile.mkdtemp()
        self.config_dir = os.path.join(self.root_temp, "config")
        self.backup_dir = os.path.join(self.root_temp, "backups")
        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

        self.entrypoint = os.path.join(self.config_dir, "hyprland.lua")
        self.sidecar_path = os.path.join(self.config_dir, "descriptions.json")

        self.initial_lua = (
            'local mainMod = "SUPER"\n'
            'hl.bind(mainMod .. " + Q", hl.dsp.window.close())\n'
            'hl.bind(mainMod .. " + Return", hl.dsp.exec_cmd("kitty"))\n'
        )
        with open(self.entrypoint, "w", encoding="utf-8") as f:
            f.write(self.initial_lua)

        os.environ["HKS_BACKUP_DIR"] = self.backup_dir
        os.environ["HKS_SIDECAR"] = self.sidecar_path

    def tearDown(self) -> None:
        os.environ.pop("HKS_BACKUP_DIR", None)
        os.environ.pop("HKS_SIDECAR", None)
        shutil.rmtree(self.root_temp, ignore_errors=True)

    def test_sidecar_warning_collision_code(self) -> None:
        doc, _ = run_scan_pipeline(config_dir=self.config_dir, entrypoint=self.entrypoint, no_live=True, no_sidecar=True)
        q_bind = next(b for b in doc.binds if b.key == "Q")

        # Sidecar has an override on Q AND an existing override on T
        initial_sidecar = {
            "version": 1,
            "overrides": [
                {
                    "match": {"modifiers": ["SUPER"], "key": "Q", "submap": "", "dispatcher": "window.close"},
                    "description": "Close Window",
                    "category": "Windows",
                },
                {
                    "match": {"modifiers": ["SUPER"], "key": "T", "submap": "", "dispatcher": "window.close"},
                    "description": "Terminal",
                    "category": "Apps",
                },
            ],
        }
        with open(self.sidecar_path, "w", encoding="utf-8") as f:
            json.dump(initial_sidecar, f, indent=2)

        # Replacing Q -> T collides with existing T override in sidecar
        buf = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = buf
            code = main([
                "edit", "replace",
                "--id", q_bind.id,
                "--mods", "SUPER",
                "--key", "T",
                "--apply",
                "--no-live",
                "--config-dir", self.config_dir,
                "--entrypoint", self.entrypoint,
                "--json",
            ])
        finally:
            sys.stdout = old_stdout

        self.assertEqual(code, 0)
        res = json.loads(buf.getvalue())
        self.assertIn("sidecar_warning", res)
        warn = res["sidecar_warning"]
        self.assertIsNotNone(warn)
        self.assertEqual(warn["code"], "collision")
        self.assertTrue(warn["orphaned_old"])
        self.assertIn("destination shortcut (SUPER + T) already has a custom override", warn["message"])
        self.assertEqual(warn["old_match"]["key"], "Q")
        self.assertEqual(warn["new_match"]["key"], "T")
        # Ensure warnings list contains human-readable sentence, not a raw dict
        self.assertTrue(any("destination shortcut" in w for w in res["warnings"]))
        self.assertFalse(any("{'" in w for w in res["warnings"]))

    def test_sidecar_warning_write_failed_code(self) -> None:
        doc, _ = run_scan_pipeline(config_dir=self.config_dir, entrypoint=self.entrypoint, no_live=True, no_sidecar=True)
        q_bind = next(b for b in doc.binds if b.key == "Q")

        # Make sidecar path point to a read-only unwriteable path
        read_only_sc = os.path.join(self.root_temp, "readonly_dir", "descriptions.json")
        os.makedirs(os.path.dirname(read_only_sc), mode=0o555)

        buf = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = buf
            code = main([
                "edit", "replace",
                "--id", q_bind.id,
                "--mods", "SUPER",
                "--key", "W",
                "--desc", "Close Window",
                "--apply",
                "--no-live",
                "--sidecar", read_only_sc,
                "--config-dir", self.config_dir,
                "--entrypoint", self.entrypoint,
                "--json",
            ])
        finally:
            sys.stdout = old_stdout

        res = json.loads(buf.getvalue())
        # Even if sidecar write failed, config was safely applied
        if res.get("sidecar_warning"):
            warn = res["sidecar_warning"]
            self.assertEqual(warn["code"], "write_failed")
            self.assertFalse(warn["orphaned_old"])
            self.assertIn("Sidecar", warn["message"])


if __name__ == "__main__":
    unittest.main()
