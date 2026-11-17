"""Tests for Default Applications (XDG MIME associations) backend."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.cli import build_arg_parser
from backend.settings.default_apps.ops import set_default_app
from backend.settings.default_apps.state import get_default_apps_state


class TestDefaultAppsBackend(unittest.TestCase):
    def _setup_xdg_fixture(self, root: Path) -> dict[str, str]:
        cfg_dir = root / "config"
        data_home = root / "local_share"
        sys_data = root / "usr_share"
        (cfg_dir).mkdir(parents=True)
        (data_home / "applications").mkdir(parents=True)
        (sys_data / "applications").mkdir(parents=True)

        (sys_data / "applications" / "firefox.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=Firefox\nExec=firefox %u\nMimeType=text/html;x-scheme-handler/http;x-scheme-handler/https;\n",
            encoding="utf-8",
        )
        (sys_data / "applications" / "evince.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=Document Viewer\nExec=evince %U\nMimeType=application/pdf;\n",
            encoding="utf-8",
        )
        (sys_data / "applications" / "zathura.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=Zathura\nExec=zathura %U\nMimeType=application/pdf;\n",
            encoding="utf-8",
        )
        (cfg_dir / "mimeapps.list").write_text(
            "[Default Applications]\n"
            "application/pdf=evince.desktop\n"
            "x-scheme-handler/http=firefox.desktop\n\n"
            "[Added Associations]\n"
            "application/pdf=evince.desktop;zathura.desktop;\n",
            encoding="utf-8",
        )
        return {
            "HOME": str(root),
            "XDG_CONFIG_HOME": str(cfg_dir),
            "XDG_DATA_HOME": str(data_home),
            "XDG_DATA_DIRS": str(sys_data),
        }

    def test_state_reads_defaults_and_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = self._setup_xdg_fixture(Path(tmp))
            st = get_default_apps_state(env=env, query_runner=lambda _mt: "")
            self.assertTrue(st["available"])
            by_mime = {a["mime_type"]: a for a in st["associations"]}
            pdf = by_mime["application/pdf"]
            self.assertEqual(pdf["default_desktop_id"], "evince.desktop")
            self.assertEqual(pdf["default_app_name"], "Document Viewer")
            cand_ids = [c["desktop_id"] for c in pdf["candidates"]]
            self.assertEqual(cand_ids, ["evince.desktop", "zathura.desktop"])
            self.assertGreaterEqual(st["summary"]["installed_apps"], 3)

    def test_set_default_app_validation_and_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = self._setup_xdg_fixture(Path(tmp))
            bad_mime = set_default_app("not a mime", "evince.desktop", env=env)
            self.assertFalse(bad_mime["ok"])

            missing = set_default_app("application/pdf", "nonexistent.desktop", env=env)
            self.assertFalse(missing["ok"])

            dry = set_default_app("application/pdf", "zathura.desktop", dry_run=True, env=env)
            self.assertTrue(dry["ok"])
            self.assertTrue(dry["dry_run"])
            self.assertEqual(dry["app_name"], "Zathura")

            calls: list[list[str]] = []

            def fake_runner(argv: list[str]) -> tuple[int, str, str]:
                calls.append(argv)
                return (0, "", "")

            applied = set_default_app(
                "application/pdf",
                "zathura.desktop",
                dry_run=False,
                env=env,
                runner=fake_runner,
            )
            self.assertTrue(applied["ok"])
            self.assertEqual(calls, [["xdg-mime", "default", "zathura.desktop", "application/pdf"]])

    def test_cli_parser_accepts_settings_apps(self) -> None:
        parser = build_arg_parser()
        args_state = parser.parse_args(["settings", "apps", "state", "--json"])
        self.assertEqual(args_state.settings_action, "apps")
        self.assertEqual(args_state.apps_action, "state")

        args_set = parser.parse_args(
            ["settings", "apps", "set", "--mime", "application/pdf", "--desktop", "zathura.desktop", "--apply", "--json"]
        )
        self.assertEqual(args_set.apps_action, "set")
        self.assertEqual(args_set.mime_type, "application/pdf")
        self.assertEqual(args_set.desktop_id, "zathura.desktop")
        self.assertTrue(args_set.apply)


if __name__ == "__main__":
    unittest.main()
