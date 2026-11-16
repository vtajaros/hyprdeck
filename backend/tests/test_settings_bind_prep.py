"""Isolated unit test for preparing the SUPER+S HyprDeck Settings bind via edit add."""

from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stdout

from backend.cli import main as cli_main
from backend.tests.isolation import IsolatedTestCase


class TestSuperSSettingsBindPrep(IsolatedTestCase):
    """Verify SUPER+S HyprDeck Settings bind generation in an isolated temp config root."""

    def test_add_super_s_settings_bind_preserves_shift_s_and_records_sidecar(self) -> None:
        cfg_dir = os.path.join(self._isolated_root, "hypr")
        os.makedirs(cfg_dir, exist_ok=True)
        entrypoint = os.path.join(cfg_dir, "hyprland.lua")
        with open(entrypoint, "w", encoding="utf-8") as f:
            f.write(
                'local mainMod = "SUPER"\n'
                "hl.bind(mainMod .. ' + SHIFT + S', hl.dsp.exec_cmd('grim -g \"$(slurp)\" - | wl-copy'))\n"
            )

        sidecar_path = os.path.join(self._isolated_root, "descriptions.json")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_main([
                "edit", "add",
                "--mods", "SUPER",
                "--key", "S",
                "--dispatcher-id", "exec_cmd",
                "--args", "/home/delata/Shared/Projects/hyprdeck/scripts/hks-settings --open",
                "--prefer-mainmod",
                "--desc", "Open HyprDeck Settings",
                "--sidecar", sidecar_path,
                "--config-dir", cfg_dir,
                "--no-live",
                "--apply",
                "--json",
            ])

        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["applied"])
        self.assertEqual(payload["bind_comparison"]["added_count"], 1)
        self.assertEqual(payload["bind_comparison"]["removed_count"], 0)
        self.assertFalse(payload["has_conflicts"])

        with open(entrypoint, "r", encoding="utf-8") as f:
            updated = f.read()
        self.assertIn(
            'hl.bind(mainMod .. " + S", hl.dsp.exec_cmd("/home/delata/Shared/Projects/hyprdeck/scripts/hks-settings --open"))',
            updated,
        )
        self.assertIn("SHIFT + S", updated)

        with open(sidecar_path, "r", encoding="utf-8") as f:
            sidecar = json.load(f)
        self.assertEqual(len(sidecar["overrides"]), 1)
        self.assertEqual(sidecar["overrides"][0]["description"], "Open HyprDeck Settings")
        self.assertEqual(sidecar["overrides"][0]["match"]["key"], "S")
        self.assertEqual(sidecar["overrides"][0]["match"]["modifiers"], ["SUPER"])
