"""Regression test proving pre-existing temp sidecar isolation during apply & restore."""

from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stdout

from backend.cli import main as cli_main
from backend.describe.sidecar import resolve_sidecar_path
from backend.tests.isolation import REAL_HOME, IsolatedTestCase, is_under_path


class TestSidecarPreExistingIsolation(IsolatedTestCase):
    """Ensure CLI apply & restore use only the isolated temp sidecar, never ~/.config/hks."""

    def test_preexisting_temp_sidecar_apply_and_restore_never_resolve_real_home(self) -> None:
        cfg_dir = os.path.join(self._isolated_root, "hypr")
        os.makedirs(cfg_dir, exist_ok=True)
        entrypoint = os.path.join(cfg_dir, "hyprland.lua")
        with open(entrypoint, "w", encoding="utf-8") as f:
            f.write(
                'local mainMod = "SUPER"\n'
                'hl.bind(mainMod .. " + Q", hl.dsp.window.close())\n'
            )

        # Simulate a pre-existing sidecar inside the isolated temp root
        os.makedirs(os.path.dirname(self.sidecar_path), exist_ok=True)
        with open(self.sidecar_path, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "overrides": []}, f)

        resolved_sc = resolve_sidecar_path(env=os.environ)
        self.assertEqual(os.path.realpath(resolved_sc), os.path.realpath(self.sidecar_path))
        self.assertFalse(is_under_path(resolved_sc, os.path.join(REAL_HOME, ".config", "hks")))

        buf_add = io.StringIO()
        with redirect_stdout(buf_add):
            rc_add = cli_main([
                "edit", "add",
                "--mods", "SUPER",
                "--key", "S",
                "--dispatcher", "exec_cmd",
                "--args", "kitty",
                "--config-dir", cfg_dir,
                "--desc", "Temp isolated bind",
                "--no-live",
                "--apply",
                "--json",
            ])
        self.assertEqual(rc_add, 0)
        add_out = json.loads(buf_add.getvalue())
        self.assertTrue(add_out["applied"])

        buf_res = io.StringIO()
        with redirect_stdout(buf_res):
            rc_res = cli_main([
                "restore",
                "--latest",
                "--apply",
                "--json",
            ])
        self.assertEqual(rc_res, 0)
        res_out = json.loads(buf_res.getvalue())
        self.assertTrue(res_out["applied"])
