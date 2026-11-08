"""Phase 3b-4 Test Suite: Sidecar persistence, locking, migration, atomicity, and undo integration."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

from backend.cli import main, run_scan_pipeline
from backend.describe.sidecar_store import (
    SidecarCollisionError,
    SidecarStoreError,
    delete_override,
    list_orphans,
    migrate_override,
    save_override,
)
from backend.editor.apply import apply_edit, resolve_insert_op, resolve_replace_op
from backend.editor.backups import (
    create_backup,
    list_backups,
    restore_backup,
)
from backend.models.types import BindRecord, DisabledBindRecord, DispatcherInfo


class TestPhase3b4SidecarStore(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.sidecar_path = os.path.join(self.temp_dir, "descriptions.json")
        self.backup_dir = os.path.join(self.temp_dir, "backups")
        os.environ["HKS_BACKUP_DIR"] = self.backup_dir
        os.environ["HKS_SIDECAR"] = self.sidecar_path

    def tearDown(self) -> None:
        os.environ.pop("HKS_BACKUP_DIR", None)
        os.environ.pop("HKS_SIDECAR", None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sidecar_roundtrip_save_and_get(self) -> None:
        match = {
            "modifiers": ["SUPER"],
            "key": "Q",
            "submap": "",
            "dispatcher": "killactive",
        }
        res = save_override(
            self.sidecar_path,
            match,
            description="Close focused window",
            category="Windows",
            backup_dir=self.backup_dir,
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["description"], "Close focused window")
        self.assertEqual(res["category"], "Windows")

        # Verify file on disk is valid 2-space indented JSON
        with open(self.sidecar_path, "r", encoding="utf-8") as f:
            content = f.read()
        data = json.loads(content)
        self.assertEqual(data["version"], 1)
        self.assertEqual(len(data["overrides"]), 1)
        self.assertEqual(data["overrides"][0]["description"], "Close focused window")
        self.assertEqual(data["overrides"][0]["category"], "Windows")

    def test_unknown_fields_and_comments_preserved(self) -> None:
        initial = {
            "_schema_note": "Custom comment",
            "version": 1,
            "overrides": [
                {
                    "_author": "delata",
                    "match": {
                        "modifiers": ["SUPER"],
                        "key": "Return",
                        "submap": "",
                    },
                    "description": "Terminal",
                    "category": "Apps",
                }
            ],
        }
        with open(self.sidecar_path, "w", encoding="utf-8") as f:
            json.dump(initial, f, indent=2)

        # Update description on the existing entry
        save_override(
            self.sidecar_path,
            {"modifiers": ["SUPER"], "key": "Return", "submap": ""},
            description="Alacritty Terminal",
            backup_dir=self.backup_dir,
        )

        with open(self.sidecar_path, "r", encoding="utf-8") as f:
            data = json.loads(f.read())

        self.assertEqual(data["_schema_note"], "Custom comment")
        self.assertEqual(len(data["overrides"]), 1)
        self.assertEqual(data["overrides"][0]["_author"], "delata")
        self.assertEqual(data["overrides"][0]["description"], "Alacritty Terminal")

    def test_validation_limits(self) -> None:
        match = {"modifiers": ["SUPER"], "key": "A"}

        # Description > 200 chars
        with self.assertRaises(SidecarStoreError) as ctx:
            save_override(self.sidecar_path, match, description="x" * 201)
        self.assertIn("200 characters", str(ctx.exception))

        # Control characters / newlines
        with self.assertRaises(SidecarStoreError) as ctx:
            save_override(self.sidecar_path, match, description="line1\nline2")
        self.assertIn("control characters", str(ctx.exception))

        # Unknown category
        with self.assertRaises(SidecarStoreError) as ctx:
            save_override(self.sidecar_path, match, description="test", category="NonExistentCat")
        self.assertIn("Invalid category", str(ctx.exception))

        # Missing both description and category
        with self.assertRaises(SidecarStoreError) as ctx:
            save_override(self.sidecar_path, match, description=None, category=None)
        self.assertIn("at least one", str(ctx.exception))

    def test_corrupt_file_refusal(self) -> None:
        with open(self.sidecar_path, "w", encoding="utf-8") as f:
            f.write("{\n  corrupt_json: [invalid\n")

        with self.assertRaises(SidecarStoreError) as ctx:
            save_override(self.sidecar_path, {"modifiers": ["SUPER"], "key": "Q"}, description="test")
        self.assertIn("Refusing to overwrite", str(ctx.exception))

        # Ensure corrupt file on disk was preserved untouched
        with open(self.sidecar_path, "r", encoding="utf-8") as f:
            self.assertIn("corrupt_json", f.read())

    def test_migration_success_and_collision(self) -> None:
        # Create initial override
        save_override(
            self.sidecar_path,
            {"modifiers": ["SUPER"], "key": "Return"},
            description="Terminal",
            category="Apps",
            backup_dir=self.backup_dir,
        )

        # Successful migration to Super+T
        mig_res = migrate_override(
            self.sidecar_path,
            {"modifiers": ["SUPER"], "key": "Return"},
            {"modifiers": ["SUPER"], "key": "T"},
            backup_dir=self.backup_dir,
        )
        self.assertTrue(mig_res["migrated"])
        self.assertFalse(mig_res["collision"])

        # Add another override on Super+Return
        save_override(
            self.sidecar_path,
            {"modifiers": ["SUPER"], "key": "Return"},
            description="Secondary Terminal",
            backup_dir=self.backup_dir,
        )

        # Attempt to migrate Super+T back to Super+Return -> collision!
        col_res = migrate_override(
            self.sidecar_path,
            {"modifiers": ["SUPER"], "key": "T"},
            {"modifiers": ["SUPER"], "key": "Return"},
            backup_dir=self.backup_dir,
        )
        self.assertFalse(col_res["migrated"])
        self.assertTrue(col_res["collision"])
        self.assertEqual(col_res["existing"]["description"], "Secondary Terminal")

    def test_lock_contention_multithreading(self) -> None:
        errors: list[Exception] = []

        def worker(key_char: str) -> None:
            try:
                for _ in range(5):
                    save_override(
                        self.sidecar_path,
                        {"modifiers": ["SUPER"], "key": key_char},
                        description=f"App {key_char}",
                        category="Apps",
                        backup_dir=self.backup_dir,
                    )
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=worker, args=("A",))
        t2 = threading.Thread(target=worker, args=("B",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(errors), 0, f"Thread errors: {errors}")
        with open(self.sidecar_path, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
        self.assertEqual(len(data["overrides"]), 2)

    def test_orphans_vs_disabled_binds(self) -> None:
        active_bind = types.SimpleNamespace(
            id="bind_active_1",
            modifiers=["SUPER"],
            key="Q",
            submap="",
            dispatcher=types.SimpleNamespace(path="killactive"),
        )
        disabled_bind = DisabledBindRecord(
            id="bind_dis_1",
            file="hyprland.lua",
            line=20,
            original_text="-- HKS-DISABLED: hl.bind('SUPER', 'E', hl.dsp.exec_cmd, 'thunar')",
            key_hint="SUPER, E",
            description_hint=None,
        )

        # Override 1: matches active bind
        save_override(self.sidecar_path, {"modifiers": ["SUPER"], "key": "Q"}, description="Close window")
        # Override 2: matches disabled bind
        save_override(self.sidecar_path, {"modifiers": ["SUPER"], "key": "E"}, description="File Manager")
        # Override 3: matches neither -> orphan!
        save_override(self.sidecar_path, {"modifiers": ["SUPER"], "key": "Z"}, description="Orphaned App")

        orphans = list_orphans(self.sidecar_path, [active_bind], [disabled_bind])
        self.assertEqual(len(orphans), 1)
        self.assertEqual(orphans[0]["match"]["key"], "Z")
        self.assertEqual(orphans[0]["description"], "Orphaned App")


class TestPhase3b4UndoAndCLI(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.config_dir = os.path.join(self.temp_dir, "hypr")
        os.makedirs(self.config_dir, exist_ok=True)
        self.entrypoint = os.path.join(self.config_dir, "hyprland.lua")
        self.hks_dir = os.path.join(self.temp_dir, "hks")
        os.makedirs(self.hks_dir, exist_ok=True)
        self.sidecar_path = os.path.join(self.hks_dir, "descriptions.json")
        self.backup_dir = os.path.join(self.temp_dir, "backups")
        os.environ["HKS_BACKUP_DIR"] = self.backup_dir
        os.environ["HKS_SIDECAR"] = self.sidecar_path

        with open(self.entrypoint, "w", encoding="utf-8") as f:
            f.write(
                'local mainMod = "SUPER"\n'
                'hl.bind(mainMod .. " + Q", hl.dsp.window.close())\n'
                'hl.bind(mainMod .. " + Return", hl.dsp.exec_cmd("kitty"))\n'
            )

    def tearDown(self) -> None:
        os.environ.pop("HKS_BACKUP_DIR", None)
        os.environ.pop("HKS_SIDECAR", None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_replace_with_migration_and_undo(self) -> None:
        # 1. Create sidecar override for Super+Return
        save_override(
            self.sidecar_path,
            {"modifiers": ["SUPER"], "key": "Return"},
            description="Kitty Terminal",
            category="Apps",
            backup_dir=self.backup_dir,
        )
        with open(self.sidecar_path, "r", encoding="utf-8") as f:
            sidecar_before = f.read()
        with open(self.entrypoint, "r", encoding="utf-8") as f:
            config_before = f.read()

        # 2. Run CLI replace from Return to T with migration
        # First get bind ID
        doc, _ = run_scan_pipeline(config_dir=self.config_dir, entrypoint=self.entrypoint, no_live=True, no_sidecar=True)
        return_bind = next(b for b in doc.binds if b.key == "Return")
        target_id = return_bind.id

        # Dry run preview check
        exit_code = main([
            "edit", "replace",
            "--id", target_id,
            "--mods", "SUPER",
            "--key", "T",
            "--preserve-dispatcher",
            "--dry-run",
            "--json",
            "--config-dir", self.config_dir,
            "--entrypoint", self.entrypoint,
            "--no-live",
        ])
        self.assertEqual(exit_code, 0)

        # Apply replace
        exit_code = main([
            "edit", "replace",
            "--id", target_id,
            "--mods", "SUPER",
            "--key", "T",
            "--preserve-dispatcher",
            "--apply",
            "--json",
            "--config-dir", self.config_dir,
            "--entrypoint", self.entrypoint,
            "--no-live",
        ])
        self.assertEqual(exit_code, 0)

        # Check that config has Super+T and sidecar migrated to T
        with open(self.entrypoint, "r", encoding="utf-8") as f:
            config_after = f.read()
        self.assertTrue('mainMod .. " + T"' in config_after or '"T"' in config_after)

        with open(self.sidecar_path, "r", encoding="utf-8") as f:
            sc_after = json.loads(f.read())
        self.assertEqual(sc_after["overrides"][0]["match"]["key"], "T")

        # 3. Restore from backup (Undo)
        backups = list_backups(backup_dir=self.backup_dir)
        self.assertTrue(len(backups) >= 1)
        latest_record = backups[-1]
        self.assertIsNotNone(latest_record.sidecar_backup_path)

        restore_backup(latest_record, force=True, backup_dir=self.backup_dir)

        # Assert BOTH files are byte-for-byte restored to before state
        with open(self.entrypoint, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), config_before)
        with open(self.sidecar_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), sidecar_before)

    def test_description_only_edit_flow(self) -> None:
        doc, _ = run_scan_pipeline(config_dir=self.config_dir, entrypoint=self.entrypoint, no_live=True, no_sidecar=True)
        q_bind = next(b for b in doc.binds if b.key == "Q")
        bind_id = q_bind.id

        code_dry = main([
            "edit",
            "--id", bind_id,
            "--description", "Close focused window",
            "--category", "Windows",
            "--dry-run",
            "--json",
            "--config-dir", self.config_dir,
            "--entrypoint", self.entrypoint,
            "--no-live",
        ])
        self.assertEqual(code_dry, 0)

        # Apply description-only
        code_apply = main([
            "edit",
            "--id", bind_id,
            "--description", "Close focused window",
            "--category", "Windows",
            "--apply",
            "--json",
            "--config-dir", self.config_dir,
            "--entrypoint", self.entrypoint,
            "--no-live",
        ])
        self.assertEqual(code_apply, 0)

        with open(self.sidecar_path, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
        self.assertEqual(len(data["overrides"]), 1)
        self.assertEqual(data["overrides"][0]["description"], "Close focused window")

    def test_sidecar_cli_subcommands(self) -> None:
        doc, _ = run_scan_pipeline(config_dir=self.config_dir, entrypoint=self.entrypoint, no_live=True, no_sidecar=True)
        q_bind = next(b for b in doc.binds if b.key == "Q")
        bind_id = q_bind.id

        # sidecar set
        c1 = main([
            "sidecar", "set",
            "--id", bind_id,
            "--desc", "Close",
            "--cat", "Windows",
            "--config-dir", self.config_dir,
            "--entrypoint", self.entrypoint,
            "--no-live",
            "--json",
        ])
        self.assertEqual(c1, 0)

        # sidecar get
        c2 = main([
            "sidecar", "get",
            "--id", bind_id,
            "--config-dir", self.config_dir,
            "--entrypoint", self.entrypoint,
            "--no-live",
            "--json",
        ])
        self.assertEqual(c2, 0)

        # sidecar clear
        c3 = main([
            "sidecar", "clear",
            "--id", bind_id,
            "--config-dir", self.config_dir,
            "--entrypoint", self.entrypoint,
            "--no-live",
            "--json",
        ])
        self.assertEqual(c3, 0)

        # verify cleared
        with open(self.sidecar_path, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
        self.assertEqual(len(data.get("overrides", [])), 0)

    def test_prefer_mainmod_flag_on_add(self) -> None:
        exit_code = main([
            "edit", "add",
            "--mods", "SUPER",
            "--key", "B",
            "--dispatcher", "exec_cmd",
            "--args", "firefox",
            "--prefer-mainmod",
            "--apply",
            "--json",
            "--config-dir", self.config_dir,
            "--entrypoint", self.entrypoint,
            "--no-live",
        ])
        self.assertEqual(exit_code, 0)

        with open(self.entrypoint, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('mainMod .. " + B"', content)


if __name__ == "__main__":
    unittest.main()
