"""Unit tests for backend.settings.themes (no real gsettings/hyprctl/awww or real ~/.config writes)."""

from __future__ import annotations

import io
import json
import os
import stat
import unittest
from contextlib import redirect_stdout
from unittest import mock

from backend.core.constants import ENV_THEMES_HOME
from backend.core.live_cmd import LiveCmdResult, run_live_cmd
from backend.settings.themes import (
    get_themes_state,
    open_wallpaper_picker,
    parse_ini_key,
    set_cursor,
    set_gtk_theme,
    set_icon_theme,
    set_qt,
    validate_theme_name,
)
from backend.tests.isolation import IsolatedTestCase

_FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "themes_sample.json",
)


def _load_fixture() -> dict:
    with open(_FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class FakeThemeRunner:
    """In-memory fake runner for gsettings, hyprctl, and awww."""

    def __init__(self, fixture: dict | None = None) -> None:
        fx = fixture if fixture is not None else _load_fixture()
        self.gsettings: dict[str, str] = {
            "gtk-theme": "Adwaita",
            "icon-theme": "Papirus-Dynamic",
            "cursor-theme": "Pop",
            "cursor-size": "24",
            "color-scheme": "prefer-dark",
        }
        self.awww_out: str = fx["awww_query"]
        self.calls: list[list[str]] = []
        self.fail_gsettings: bool = False
        self.ignore_writes: bool = False

    def __call__(self, argv: list[str], timeout: float = 5.0) -> LiveCmdResult:
        self.calls.append(list(argv))
        if argv == ["awww", "query"]:
            return LiveCmdResult(ok=True, rc=0, out=self.awww_out, err="")
        if argv[:3] == ["gsettings", "get", "org.gnome.desktop.interface"] and len(argv) == 4:
            if self.fail_gsettings:
                return LiveCmdResult(ok=False, rc=1, out="", err="gsettings unavailable")
            k = argv[3]
            v = self.gsettings.get(k, "")
            out = v if k == "cursor-size" else f"'{v}'"
            return LiveCmdResult(ok=True, rc=0, out=out + "\n", err="")
        if argv[:3] == ["gsettings", "set", "org.gnome.desktop.interface"] and len(argv) == 5:
            if self.fail_gsettings:
                return LiveCmdResult(ok=False, rc=1, out="", err="gsettings unavailable")
            if not self.ignore_writes:
                self.gsettings[argv[3]] = argv[4]
            return LiveCmdResult(ok=True, rc=0, out="", err="")
        if argv[:2] == ["hyprctl", "setcursor"] and len(argv) == 4:
            return LiveCmdResult(ok=True, rc=0, out="ok\n", err="")
        return LiveCmdResult(ok=False, rc=1, out="", err=f"Unexpected command: {argv!r}")


class TestThemesIsolationAndState(IsolatedTestCase):
    """Tests for isolation guard, discovery, parsing, and conflict detection."""

    def setUp(self) -> None:
        super().setUp()
        self.themes_home = os.path.join(self._isolated_root, "themes_home")
        os.environ[ENV_THEMES_HOME] = self.themes_home
        self._populate_home(_load_fixture())

    def _populate_home(self, fx: dict) -> None:
        for rel, content, mode in (
            (".config/gtk-3.0/settings.ini", fx["gtk3_ini"], 0o600),
            (".config/gtk-4.0/settings.ini", fx["gtk4_ini"], 0o600),
            (".config/qt6ct/qt6ct.conf", fx["qt6ct_conf"], 0o644),
            (".config/hypr/hyprland.lua", fx["hyprland_lua"], 0o644),
        ):
            p = os.path.join(self.themes_home, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            os.chmod(p, mode)

        # Create installed themes/icons/cursors/qt colors & plugin dir
        for t in ("Adwaita", "Breeze", "Breeze-Dark"):
            os.makedirs(os.path.join(self.themes_home, ".themes", t), exist_ok=True)
        for ic in ("Papirus-Dynamic", "Papirus-Dark", "breeze-dark", "CursorOnlyIconless"):
            ic_dir = os.path.join(self.themes_home, ".local", "share", "icons", ic)
            os.makedirs(ic_dir, exist_ok=True)
            with open(os.path.join(ic_dir, "index.theme"), "w", encoding="utf-8") as f:
                f.write("[Icon Theme]\nName=" + ic + "\n")
        for cur in ("Pop", "Adwaita"):
            os.makedirs(os.path.join(self.themes_home, ".icons", cur, "cursors"), exist_ok=True)

        colors_dir = os.path.join(self.themes_home, ".config", "qt6ct", "colors")
        os.makedirs(colors_dir, exist_ok=True)
        for cs in ("BreezeDark.colors", "Darkly.colors"):
            with open(os.path.join(colors_dir, cs), "w", encoding="utf-8") as f:
                f.write("[ColorScheme]\n")

        self.qt_plugins_dir = os.path.join(self._isolated_root, "qt6_styles")
        os.makedirs(self.qt_plugins_dir, exist_ok=True)
        for so in ("breeze6.so", "darkly6.so"):
            with open(os.path.join(self.qt_plugins_dir, so), "wb") as f:
                f.write(b"")

    def test_isolation_guard_blocks_unmocked_theme_tools(self) -> None:
        for cmd in (["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"], ["hyprctl", "setcursor", "Pop", "24"], ["awww", "query"]):
            with self.assertRaises(AssertionError):
                run_live_cmd(cmd)

    def test_state_conflicts_wallpaper_and_cursor_filtering(self) -> None:
        runner = FakeThemeRunner()
        env = {
            **os.environ,
            "GTK_THEME": "Adwaita:dark",
            "XCURSOR_THEME": "Pop",
            "XCURSOR_SIZE": "24",
            "HYPRCURSOR_SIZE": "24",
            "QT_QPA_PLATFORMTHEME": "qt6ct",
        }
        st = get_themes_state(runner=runner, env=env, qt_plugin_dirs=(self.qt_plugins_dir,))
        self.assertTrue(st["available"])
        self.assertEqual(st["wallpaper"]["path"], "/mnt/BEWD/wallpaper bg/goated/wallhaven-yqkl97.jpg")
        self.assertEqual(st["wallpaper"]["source"], "awww")
        self.assertIn("Pop", st["cursor"]["installed"])
        self.assertNotIn("CursorOnlyIconless", st["cursor"]["installed"])
        self.assertIn("Breeze", st["qt"]["installed_styles"])
        self.assertIn("Darkly", st["qt"]["installed_styles"])

        conflict_ids = {c["id"]: c for c in st["conflicts"]}
        self.assertIn("gtk_theme_env_override", conflict_ids)
        self.assertIn('hl.env("GTK_THEME", "Adwaita:dark")', conflict_ids["gtk_theme_env_override"]["fix_hint"])
        self.assertIn("gtk_theme_mismatch", conflict_ids)
        self.assertIn("qt_gtk_icon_mismatch", conflict_ids)

    def test_missing_files_and_gsettings_failure_never_crash(self) -> None:
        empty_home = os.path.join(self._isolated_root, "empty_home")
        os.makedirs(empty_home, exist_ok=True)
        runner = FakeThemeRunner()
        runner.fail_gsettings = True
        st = get_themes_state(runner=runner, env={**os.environ, ENV_THEMES_HOME: empty_home})
        self.assertTrue(st["available"])
        self.assertIsNone(st["gtk"]["gsettings_theme"])


class TestThemesOpsAndMutationSafety(TestThemesIsolationAndState):
    """Tests for hostile names, INI line/mode preservation, backups, rollback, and CLI."""

    def test_hostile_names_and_unknown_themes_rejected_before_write(self) -> None:
        runner = FakeThemeRunner()
        for bad in ("Adwaita\nfoo=bar", "Adwaita=evil", "../Evil", "a/b", "Pop;rm -rf /", "", 123):
            import backend.settings.themes.ops as themes_ops
            with self.assertRaises(ValueError):
                themes_ops.validate_theme_name(bad)
            res = set_gtk_theme(bad, runner=runner)  # type: ignore[arg-type]
            self.assertFalse(res["ok"])
            self.assertEqual(runner.calls, [])

        self.assertFalse(set_cursor("CursorOnlyIconless", 24, runner=runner)["ok"])
        self.assertFalse(set_cursor("Pop", 10, runner=runner)["ok"])  # size < 16

    def test_gtk_icon_cursor_qt_preserve_unrelated_lines_and_mode_and_backup(self) -> None:
        runner = FakeThemeRunner()
        env = dict(os.environ)

        r_gtk = set_gtk_theme("Breeze", runner=runner, env=env, backup_dir=self.backup_dir)
        self.assertTrue(r_gtk["ok"])

        ini3_path = os.path.join(self.themes_home, ".config", "gtk-3.0", "settings.ini")
        ini4_path = os.path.join(self.themes_home, ".config", "gtk-4.0", "settings.ini")
        self.assertEqual(stat.S_IMODE(os.stat(ini3_path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(ini4_path).st_mode), 0o600)
        with open(ini4_path, "r", encoding="utf-8") as f:
            raw4 = f.read()
        self.assertIn("gtk-xft-dpi=122880", raw4)
        self.assertIn("gtk-sound-theme-name=ocean", raw4)
        self.assertEqual(parse_ini_key(raw4, "Settings", "gtk-theme-name"), "Breeze")

        # Icon warning when not Papirus-Dynamic
        r_ic = set_icon_theme("Papirus-Dark", runner=runner, env=env, backup_dir=self.backup_dir)
        self.assertTrue(r_ic["ok"])
        self.assertIn("matugen-icons-sync", r_ic["warning"])

        # Cursor updates both ini (adding key to gtk3 ini)
        r_cur = set_cursor("Adwaita", 32, runner=runner, env=env, backup_dir=self.backup_dir)
        self.assertTrue(r_cur["ok"])
        self.assertEqual(r_cur["apply_scope"], "live")
        with open(ini3_path, "r", encoding="utf-8") as f:
            self.assertEqual(parse_ini_key(f.read(), "Settings", "gtk-cursor-theme-name"), "Adwaita")

        # Qt update
        r_qt = set_qt(
            style="Darkly",
            icon_theme="Papirus-Dark",
            color_scheme_path="Darkly.colors",
            runner=runner,
            env=env,
            backup_dir=self.backup_dir,
            qt_plugin_dirs=(self.qt_plugins_dir,),
        )
        self.assertTrue(r_qt["ok"])
        self.assertEqual(r_qt["apply_scope"], "new_apps")
        self.assertEqual(r_qt["after"]["style"], "Darkly")

    def test_readback_mismatch_and_wallpaper_picker_spawn(self) -> None:
        import backend.settings.themes.ops as themes_ops
        runner = FakeThemeRunner()
        runner.ignore_writes = True
        res = themes_ops.set_gtk_theme("Breeze", runner=runner, backup_dir=self.backup_dir)
        self.assertFalse(res["ok"])
        self.assertIn("readback mismatch", res["error"].lower())

        carousel = os.path.join(self.themes_home, ".local", "bin", "wallpaper-carousel")
        os.makedirs(os.path.dirname(carousel), exist_ok=True)
        with open(carousel, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\n")
        spawned: list[list[str]] = []
        r_wp = open_wallpaper_picker(spawner=lambda argv: spawned.append(list(argv)))
        self.assertTrue(r_wp["ok"])
        self.assertEqual(spawned, [[carousel]])

    def test_cli_settings_themes(self) -> None:
        from backend.cli import main as cli_main

        runner = FakeThemeRunner()
        with mock.patch("backend.settings.themes.state.run_live_cmd", side_effect=lambda argv, **kw: runner(list(argv), timeout=kw.get("timeout", 5.0))):
            with mock.patch("backend.settings.themes.ops.run_live_cmd", side_effect=lambda argv, **kw: runner(list(argv), timeout=kw.get("timeout", 5.0))):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cli_main(["settings", "themes", "state", "--json"])
                self.assertEqual(rc, 0)
                self.assertTrue(json.loads(buf.getvalue())["available"])
