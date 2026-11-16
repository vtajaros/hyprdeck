"""Tests for S18 Settings Backups backend: legacy ID resolution, diff, and safe restore."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from backend.core.revert_guard import RevertGuardHandle, save_active_handle
from backend.editor.backups import (
    BackupRecord,
    _write_index,
    create_backup,
    restore_backup,
)
from backend.settings.backups_ops import (
    diff_backup,
    list_enriched_backups,
    safe_restore_backup,
)


def _ok_proc(stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["mock"], returncode=0, stdout=stdout, stderr="")


def _ok_hyprland(*_a, **_kw) -> subprocess.CompletedProcess[str]:
    return _ok_proc("Config parsing result:\nconfig ok\n")


def _fail_proc(stderr: str = "boom") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["mock"], returncode=1, stdout="", stderr=stderr)


class TestBackupsSettingsBackend(unittest.TestCase):
    def test_legacy_path_resolution_by_id_without_rewriting_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = os.path.join(tmp, "cfg")
            bdir = os.path.join(tmp, "backups")
            os.makedirs(cfg_dir, exist_ok=True)
            os.makedirs(bdir, exist_ok=True)

            target = os.path.join(cfg_dir, "qt6ct.conf")
            with open(target, "wb") as f:
                f.write(b"[Appearance]\nstyle=kvantum\n")

            bak_id = "qt6ct.conf.20261116-000001-deadbeef"
            bak_bytes = b"[Appearance]\nstyle=Fusion\n"
            bak_sha = hashlib.sha256(bak_bytes).hexdigest()
            with open(os.path.join(bdir, bak_id), "wb") as f:
                f.write(bak_bytes)

            legacy_path = f"/home/nonexistent/.local/share/hks/backups/{bak_id}"
            rec = BackupRecord(
                id=bak_id,
                original_path=target,
                backup_path=legacy_path,
                sha256=bak_sha,
                created_at="2026-11-16T00:00:01Z",
            )
            index_path = os.path.join(bdir, "backups.json")
            _write_index(index_path, [rec])
            with open(index_path, "rb") as f:
                before_index = f.read()

            enriched = list_enriched_backups(backup_dir=bdir)
            self.assertEqual(len(enriched), 1)
            self.assertTrue(enriched[0]["available"])
            self.assertEqual(enriched[0]["size"], len(bak_bytes))
            self.assertFalse(enriched[0]["is_current"])
            self.assertEqual(enriched[0]["reason"], "edit")

            restore_backup(bak_id, force=True, backup_dir=bdir)
            with open(target, "rb") as f:
                self.assertEqual(f.read(), bak_bytes)
            with open(index_path, "rb") as f:
                self.assertEqual(f.read(), before_index)

    def test_diff_truncation_and_large_file_stats_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = os.path.join(tmp, "cfg")
            bdir = os.path.join(tmp, "backups")
            os.makedirs(cfg_dir, exist_ok=True)

            target = os.path.join(cfg_dir, "settings.ini")
            old_lines = "\n".join(f"key_{i}=old" for i in range(500)) + "\n"
            with open(target, "w", encoding="utf-8") as f:
                f.write(old_lines)
            rec = create_backup(target, backup_dir=bdir, config_dir=cfg_dir)

            new_lines = "\n".join(f"key_{i}=new" for i in range(500)) + "\n"
            with open(target, "w", encoding="utf-8") as f:
                f.write(new_lines)

            d = diff_backup(rec.id, backup_dir=bdir)
            self.assertTrue(d["ok"])
            self.assertFalse(d["identical"])
            self.assertFalse(d["stats_only"])
            self.assertTrue(d["truncated"])
            self.assertLessEqual(len(d["diff"].splitlines()), 400)
            self.assertGreater(d["added_lines"], 0)
            self.assertGreater(d["removed_lines"], 0)

            # > 1 MiB stats-only guard
            big_target = os.path.join(cfg_dir, "big.conf")
            with open(big_target, "wb") as f:
                f.write(b"a\n" * (600 * 1024))
            big_rec = create_backup(big_target, backup_dir=bdir, config_dir=cfg_dir)
            with open(big_target, "wb") as f:
                f.write(b"b\n" * (600 * 1024))
            big_diff = diff_backup(big_rec.id, backup_dir=bdir)
            self.assertTrue(big_diff["ok"])
            self.assertTrue(big_diff["stats_only"])
            self.assertTrue(big_diff["truncated"])
            self.assertEqual(big_diff["diff"], "")

    def test_safe_restore_blocks_on_active_revert_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = os.path.join(tmp, "cfg")
            bdir = os.path.join(tmp, "backups")
            sdir = os.path.join(tmp, "state")
            os.makedirs(cfg_dir, exist_ok=True)
            target = os.path.join(cfg_dir, "qt6ct.conf")
            with open(target, "w", encoding="utf-8") as f:
                f.write("a=1\n")
            rec = create_backup(target, backup_dir=bdir, config_dir=cfg_dir)

            save_active_handle(
                RevertGuardHandle(
                    plan_path=os.path.join(sdir, "plan.json"),
                    confirm_path=os.path.join(sdir, "confirm"),
                    log_path=os.path.join(sdir, "log"),
                    pid=999999,
                    plan={},
                ),
                deadline_epoch=9999999999.0,
                timeout_seconds=15.0,
                state_dir=sdir,
            )

            res = safe_restore_backup(rec.id, apply=True, backup_dir=bdir, state_dir=sdir)
            self.assertFalse(res["ok"])
            self.assertEqual(res.get("blocked_by"), "revert_guard")

    def test_safe_restore_lua_validation_rollback_and_undo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = os.path.join(tmp, "cfg")
            bdir = os.path.join(tmp, "backups")
            sdir = os.path.join(tmp, "state")
            os.makedirs(cfg_dir, exist_ok=True)
            target = os.path.join(cfg_dir, "hyprland.lua")
            with open(target, "w", encoding="utf-8") as f:
                f.write("hypr.bind('SUPER', 'Return', 'exec', 'kitty')\n")
            rec = create_backup(target, backup_dir=bdir, config_dir=cfg_dir)

            with open(target, "w", encoding="utf-8") as f:
                f.write("hypr.bind('SUPER', 'Q', 'killactive')\n")

            # Candidate validation failure aborts before writing
            bad = safe_restore_backup(
                rec.id,
                apply=True,
                backup_dir=bdir,
                state_dir=sdir,
                config_dir=cfg_dir,
                entrypoint=target,
                hyprland_runner=lambda *a, **kw: _fail_proc("syntax error"),
                sleep_fn=lambda _s: None,
            )
            self.assertFalse(bad["ok"])
            self.assertFalse(bad["applied"])
            with open(target, encoding="utf-8") as f:
                self.assertIn("SUPER', 'Q'", f.read())

            # Reload failure triggers auto-rollback
            rb = safe_restore_backup(
                rec.id,
                apply=True,
                backup_dir=bdir,
                state_dir=sdir,
                config_dir=cfg_dir,
                entrypoint=target,
                hyprland_runner=_ok_hyprland,
                reload_runner=lambda argv, **kw: (
                    _fail_proc("reload failed") if argv[:2] == ["hyprctl", "reload"] else _ok_proc()
                ),
                sleep_fn=lambda _s: None,
            )
            self.assertFalse(rb["ok"])
            self.assertTrue(rb["rolled_back"])
            with open(target, encoding="utf-8") as f:
                self.assertIn("SUPER', 'Q'", f.read())

            # Success creates pre-restore snapshot and supports one-click undo
            ok_res = safe_restore_backup(
                rec.id,
                apply=True,
                backup_dir=bdir,
                state_dir=sdir,
                config_dir=cfg_dir,
                entrypoint=target,
                hyprland_runner=_ok_hyprland,
                reload_runner=lambda argv, **kw: _ok_proc(),
                sleep_fn=lambda _s: None,
            )
            self.assertTrue(ok_res["ok"])
            self.assertTrue(ok_res["applied"])
            snap_id = ok_res["snapshot_id"]
            self.assertIsNotNone(snap_id)
            with open(target, encoding="utf-8") as f:
                self.assertIn("kitty", f.read())

            # Verify pre-restore reason
            items = list_enriched_backups(backup_dir=bdir)
            snap_items = [x for x in items if x["id"] == snap_id]
            self.assertEqual(len(snap_items), 1)
            self.assertEqual(snap_items[0]["reason"], "pre-restore")

            # One-click undo via snapshot_id
            undo_res = safe_restore_backup(
                snap_id,
                apply=True,
                backup_dir=bdir,
                state_dir=sdir,
                config_dir=cfg_dir,
                entrypoint=target,
                hyprland_runner=_ok_hyprland,
                reload_runner=lambda argv, **kw: _ok_proc(),
                sleep_fn=lambda _s: None,
            )
            self.assertTrue(undo_res["ok"])
            with open(target, encoding="utf-8") as f:
                self.assertIn("SUPER', 'Q'", f.read())

    def test_hypridle_and_cli_settings_backups_handlers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = os.path.join(tmp, "cfg")
            bdir = os.path.join(tmp, "backups")
            sdir = os.path.join(tmp, "state")
            os.makedirs(cfg_dir, exist_ok=True)
            idle = os.path.join(cfg_dir, "hypridle.conf")
            with open(idle, "w", encoding="utf-8") as f:
                f.write("listener {\n  timeout = 300\n}\n")
            rec = create_backup(idle, backup_dir=bdir, config_dir=cfg_dir)
            with open(idle, "w", encoding="utf-8") as f:
                f.write("listener {\n  timeout = 600\n}\n")

            cmds: list[list[str]] = []
            res = safe_restore_backup(
                rec.id,
                apply=True,
                backup_dir=bdir,
                state_dir=sdir,
                live_cmd_runner=lambda argv, **kw: (cmds.append(list(argv)), _ok_proc("1234\n"))[1],
                spawn_fn=lambda argv: (cmds.append(list(argv)), 1234)[1],
                sleep_fn=lambda _s: None,
            )
            self.assertTrue(res["ok"])
            self.assertEqual(res["reload_status"], "hypridle restarted")
            self.assertEqual(cmds, [["pkill", "-x", "hypridle"], ["hypridle"], ["pgrep", "-x", "hypridle"]])

            from backend import cli

            with patch.dict(os.environ, {"HYPRDECK_BACKUP_DIR": bdir}, clear=False):
                out = io.StringIO()
                with patch("sys.stdout", out):
                    rc = cli.main(["settings", "backups", "list", "--json"])
                self.assertEqual(rc, 0)
                parsed = json.loads(out.getvalue())
                self.assertTrue(parsed["ok"])
                self.assertGreaterEqual(parsed["count"], 2)

                out_diff = io.StringIO()
                with patch("sys.stdout", out_diff):
                    rc_d = cli.main(["backups", "diff", "--id", rec.id, "--json"])
                self.assertEqual(rc_d, 0)
                parsed_d = json.loads(out_diff.getvalue())
                self.assertTrue(parsed_d["ok"])
                self.assertTrue(parsed_d["identical"])


if __name__ == "__main__":
    unittest.main()
