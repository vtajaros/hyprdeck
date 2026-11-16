"""System theme state probing (wallpaper, GTK, icons, cursor, Qt6ct, and consistency conflicts)."""

from __future__ import annotations

import os
import re
from typing import Any, Mapping

from backend.core.constants import ENV_THEMES_HOME
from backend.core.live_cmd import DEFAULT_LIVE_CMD_TIMEOUT_SECONDS, LiveRunner, run_live_cmd

_AWWW_IMAGE_RE = re.compile(r"currently displaying:\s*image:\s*(.+?)\s*$")
_HYPR_GTK_ENV_RE = re.compile(r'hl\.env\(\s*["\']GTK_THEME["\']\s*,\s*["\']([^"\']*)["\']\s*\)')

_QT6_PLUGIN_STYLE_MAP = {
    "breeze6": "Breeze",
    "darkly6": "Darkly",
    "oxygen6": "Oxygen",
    "libqt6ct-style": "qt6ct-style",
}
_QT_BUILTIN_STYLES = ("Fusion", "Windows")


def resolve_themes_paths(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Resolve theme config paths honoring HKS_THEMES_HOME for test isolation."""
    environ = env if env is not None else os.environ
    override = environ.get(ENV_THEMES_HOME, "").strip()
    home = os.path.abspath(os.path.expanduser(override)) if override else (
        os.path.abspath(os.path.expanduser(environ.get("HOME", "").strip() or "~"))
    )
    return {
        "home": home,
        "gtk3_ini": os.path.join(home, ".config", "gtk-3.0", "settings.ini"),
        "gtk4_ini": os.path.join(home, ".config", "gtk-4.0", "settings.ini"),
        "qt6ct_conf": os.path.join(home, ".config", "qt6ct", "qt6ct.conf"),
        "qt6ct_colors_dir": os.path.join(home, ".config", "qt6ct", "colors"),
        "cache_wallpaper": os.path.join(home, ".cache", "current_wallpaper"),
        "wallpaper_carousel": os.path.join(home, ".local", "bin", "wallpaper-carousel"),
        "hyprland_lua": os.path.join(home, ".config", "hypr", "hyprland.lua"),
        "user_themes_dir": os.path.join(home, ".themes"),
        "user_local_themes_dir": os.path.join(home, ".local", "share", "themes"),
        "user_icons_dir": os.path.join(home, ".icons"),
        "user_local_icons_dir": os.path.join(home, ".local", "share", "icons"),
    }


def parse_ini_key(raw: str, section: str, key: str) -> str | None:
    """Read a key from a specific [section] in an INI/conf file (supports `k=v` and `k = v`)."""
    in_section = False
    target_sec = section.strip()
    for line in (raw or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = (stripped[1:-1].strip() == target_sec)
            continue
        if not in_section or "=" not in stripped:
            continue
        k, v = stripped.split("=", 1)
        if k.strip() == key:
            return v.strip()
    return None


def _read_text_safe(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _gsettings_get(
    key: str,
    *,
    runner: LiveRunner | None,
    timeout: float,
) -> str | None:
    res = run_live_cmd(
        ["gsettings", "get", "org.gnome.desktop.interface", key],
        timeout=timeout,
        runner=runner,
    )
    if not res.ok:
        return None
    val = res.out.strip()
    if len(val) >= 2 and val[0] == "'" and val[-1] == "'":
        return val[1:-1]
    return val


def discover_gtk_themes(paths: Mapping[str, str]) -> list[str]:
    """Discover installed GTK themes from system and user theme directories."""
    found: set[str] = set()
    roots = (
        "/usr/share/themes",
        paths["user_themes_dir"],
        paths["user_local_themes_dir"],
    )
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            for entry in os.listdir(root):
                if entry.startswith("."):
                    continue
                full = os.path.join(root, entry)
                if os.path.isdir(full):
                    found.add(entry)
        except OSError:
            continue
    return sorted(found, key=str.lower)


def discover_icon_and_cursor_themes(paths: Mapping[str, str]) -> tuple[list[str], list[str]]:
    """Discover installed icon themes and cursor-capable themes (containing a `cursors/` subdir)."""
    icons: set[str] = set()
    cursors: set[str] = set()
    roots = (
        "/usr/share/icons",
        paths["user_icons_dir"],
        paths["user_local_icons_dir"],
    )
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            for entry in os.listdir(root):
                if entry.startswith("."):
                    continue
                full = os.path.join(root, entry)
                if not os.path.isdir(full):
                    continue
                if os.path.isfile(os.path.join(full, "index.theme")) and entry not in ("hicolor", "locolor", "default"):
                    icons.add(entry)
                if os.path.isdir(os.path.join(full, "cursors")):
                    cursors.add(entry)
        except OSError:
            continue
    return sorted(icons, key=str.lower), sorted(cursors, key=str.lower)


def discover_qt_styles(plugin_dirs: tuple[str, ...] | None = None) -> list[str]:
    """Discover available Qt6 widget styles by scanning Qt6 style plugin directories."""
    dirs = list(plugin_dirs) if plugin_dirs is not None else [
        "/usr/lib/qt6/plugins/styles",
        "/usr/lib64/qt6/plugins/styles",
    ]
    styles: set[str] = set(_QT_BUILTIN_STYLES)
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        try:
            for entry in os.listdir(d):
                if not entry.endswith(".so"):
                    continue
                stem = entry[:-3]
                styles.add(_QT6_PLUGIN_STYLE_MAP.get(stem, stem))
        except OSError:
            continue
    return sorted(styles, key=str.lower)


def discover_qt_color_schemes(colors_dir: str) -> list[dict[str, str]]:
    """Discover *.colors files in qt6ct colors directory."""
    if not os.path.isdir(colors_dir):
        return []
    schemes: list[dict[str, str]] = []
    try:
        for entry in sorted(os.listdir(colors_dir), key=str.lower):
            if entry.endswith(".colors"):
                full = os.path.join(colors_dir, entry)
                if os.path.isfile(full):
                    schemes.append({"name": entry[:-7], "path": full})
    except OSError:
        return []
    return schemes


def probe_wallpaper(
    cache_wallpaper_path: str,
    *,
    runner: LiveRunner | None,
    timeout: float,
) -> dict[str, Any]:
    """Read current wallpaper path from `awww query`, falling back to ~/.cache/current_wallpaper."""
    res = run_live_cmd(["awww", "query"], timeout=timeout, runner=runner)
    if res.ok and res.out:
        for line in res.out.splitlines():
            m = _AWWW_IMAGE_RE.search(line)
            if m:
                wp_path = m.group(1).strip()
                return {
                    "path": wp_path,
                    "exists": os.path.isfile(wp_path),
                    "source": "awww",
                }

    if os.path.lexists(cache_wallpaper_path):
        resolved = os.path.realpath(cache_wallpaper_path)
        return {
            "path": resolved,
            "exists": os.path.isfile(resolved),
            "source": "cache_symlink",
        }

    return {"path": "", "exists": False, "source": "none"}


def _read_hyprland_gtk_env_line(hyprland_lua_path: str) -> str:
    raw = _read_text_safe(hyprland_lua_path)
    if not raw:
        return ""
    for line in raw.splitlines():
        if _HYPR_GTK_ENV_RE.search(line) and not line.lstrip().startswith("--"):
            return line.strip()
    return ""


def compute_theme_conflicts(
    *,
    gtk: Mapping[str, Any],
    icons: Mapping[str, Any],
    cursor: Mapping[str, Any],
    qt: Mapping[str, Any],
    hyprland_lua_path: str,
) -> list[dict[str, Any]]:
    """Detect theme consistency conflicts and provide actionable fix hints."""
    conflicts: list[dict[str, Any]] = []

    env_gtk = str(gtk.get("env_theme") or "").strip()
    if env_gtk:
        exact_line = _read_hyprland_gtk_env_line(hyprland_lua_path)
        hint_line = exact_line or f'hl.env("GTK_THEME", "{env_gtk}")'
        conflicts.append(
            {
                "id": "gtk_theme_env_override",
                "severity": "warning",
                "explanation": (
                    f"Environment variable GTK_THEME={env_gtk!r} overrides gsettings and GTK settings.ini for all apps."
                ),
                "fix_hint": (
                    f"Remove or comment out `{hint_line}` in hyprland.lua, then log out and log back in."
                ),
                "copy_text": hint_line,
            }
        )

    gtk_vals = {
        v for v in (gtk.get("gsettings_theme"), gtk.get("gtk3_theme"), gtk.get("gtk4_theme"))
        if v
    }
    if len(gtk_vals) > 1:
        conflicts.append(
            {
                "id": "gtk_theme_mismatch",
                "severity": "warning",
                "explanation": (
                    f"GTK theme differs across gsettings ({gtk.get('gsettings_theme')}), "
                    f"GTK3 ({gtk.get('gtk3_theme')}), and GTK4 ({gtk.get('gtk4_theme')})."
                ),
                "fix_hint": "Apply a GTK theme from this page to sync gsettings, gtk-3.0, and gtk-4.0.",
                "copy_text": "",
            }
        )

    cur_themes = {
        v for v in (
            cursor.get("gsettings_theme"),
            cursor.get("gtk4_theme"),
            cursor.get("gtk3_theme"),
            cursor.get("env_theme"),
        )
        if v
    }
    cur_sizes = {
        v for v in (
            cursor.get("gsettings_size"),
            cursor.get("gtk4_size"),
            cursor.get("env_xcursor_size"),
            cursor.get("env_hyprcursor_size"),
        )
        if v is not None
    }
    if len(cur_themes) > 1 or len(cur_sizes) > 1:
        conflicts.append(
            {
                "id": "cursor_mismatch",
                "severity": "warning",
                "explanation": "Cursor theme or size differs across gsettings, GTK ini, and XCURSOR/HYPRCURSOR env.",
                "fix_hint": "Apply cursor theme/size from this page and ensure hyprland.lua XCURSOR_* env matches.",
                "copy_text": "",
            }
        )

    active_icon = icons.get("gsettings_theme") or icons.get("gtk3_theme") or icons.get("gtk4_theme") or ""
    if active_icon and active_icon != "Papirus-Dynamic":
        conflicts.append(
            {
                "id": "icon_theme_non_dynamic",
                "severity": "warning",
                "explanation": (
                    f"Icon theme is {active_icon!r}; matugen-icons-sync will reset it to 'Papirus-Dynamic' on the next wallpaper change."
                ),
                "fix_hint": "Select 'Papirus-Dynamic' (recommended) to keep icons synced with wallpaper.",
                "copy_text": "",
            }
        )

    qt_icon = str(qt.get("icon_theme") or "").strip()
    if active_icon and qt_icon and qt_icon != active_icon:
        conflicts.append(
            {
                "id": "qt_gtk_icon_mismatch",
                "severity": "info",
                "explanation": f"Qt6ct icon theme ({qt_icon!r}) differs from GTK icon theme ({active_icon!r}).",
                "fix_hint": "Update Qt6ct icon theme below if you want Qt and GTK apps to share icons.",
                "copy_text": "",
            }
        )

    return conflicts


def get_themes_state(
    *,
    runner: LiveRunner | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
    qt_plugin_dirs: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Read complete system theme state (wallpaper, GTK, icons, cursor, Qt6ct, conflicts)."""
    environ = env if env is not None else os.environ
    paths = resolve_themes_paths(environ)

    ini3_raw = _read_text_safe(paths["gtk3_ini"]) or ""
    ini4_raw = _read_text_safe(paths["gtk4_ini"]) or ""
    qt_raw = _read_text_safe(paths["qt6ct_conf"]) or ""

    gs_gtk = _gsettings_get("gtk-theme", runner=runner, timeout=timeout)
    gs_icon = _gsettings_get("icon-theme", runner=runner, timeout=timeout)
    gs_cursor = _gsettings_get("cursor-theme", runner=runner, timeout=timeout)
    gs_cursor_size_raw = _gsettings_get("cursor-size", runner=runner, timeout=timeout)
    gs_color_scheme = _gsettings_get("color-scheme", runner=runner, timeout=timeout)

    gs_cursor_size: int | None = None
    if gs_cursor_size_raw and gs_cursor_size_raw.isdigit():
        gs_cursor_size = int(gs_cursor_size_raw)

    gtk3_theme = parse_ini_key(ini3_raw, "Settings", "gtk-theme-name")
    gtk4_theme = parse_ini_key(ini4_raw, "Settings", "gtk-theme-name")
    gtk3_icon = parse_ini_key(ini3_raw, "Settings", "gtk-icon-theme-name")
    gtk4_icon = parse_ini_key(ini4_raw, "Settings", "gtk-icon-theme-name")
    gtk3_cursor = parse_ini_key(ini3_raw, "Settings", "gtk-cursor-theme-name")
    gtk4_cursor = parse_ini_key(ini4_raw, "Settings", "gtk-cursor-theme-name")
    gtk4_cursor_size_raw = parse_ini_key(ini4_raw, "Settings", "gtk-cursor-theme-size")
    gtk4_cursor_size = int(gtk4_cursor_size_raw) if (gtk4_cursor_size_raw and gtk4_cursor_size_raw.isdigit()) else None

    env_gtk_theme = environ.get("GTK_THEME", "").strip() or None
    env_xcursor_theme = environ.get("XCURSOR_THEME", "").strip() or None
    env_xcursor_size_raw = environ.get("XCURSOR_SIZE", "").strip()
    env_xcursor_size = int(env_xcursor_size_raw) if env_xcursor_size_raw.isdigit() else None
    env_hyprcursor_size_raw = environ.get("HYPRCURSOR_SIZE", "").strip()
    env_hyprcursor_size = int(env_hyprcursor_size_raw) if env_hyprcursor_size_raw.isdigit() else None

    installed_gtk = discover_gtk_themes(paths)
    installed_icons, installed_cursors = discover_icon_and_cursor_themes(paths)
    installed_qt_styles = discover_qt_styles(qt_plugin_dirs)
    installed_qt_schemes = discover_qt_color_schemes(paths["qt6ct_colors_dir"])

    qt_style = parse_ini_key(qt_raw, "Appearance", "style")
    qt_icon = parse_ini_key(qt_raw, "Appearance", "icon_theme")
    qt_scheme = parse_ini_key(qt_raw, "Appearance", "color_scheme_path")

    gtk_section = {
        "gsettings_theme": gs_gtk,
        "gtk3_theme": gtk3_theme,
        "gtk4_theme": gtk4_theme,
        "env_theme": env_gtk_theme,
        "effective_theme": env_gtk_theme or gs_gtk or gtk3_theme or gtk4_theme or "",
        "installed": installed_gtk,
    }
    icons_section = {
        "gsettings_theme": gs_icon,
        "gtk3_theme": gtk3_icon,
        "gtk4_theme": gtk4_icon,
        "qt6ct_theme": qt_icon,
        "is_dynamic": (gs_icon == "Papirus-Dynamic"),
        "installed": installed_icons,
    }
    cursor_section = {
        "gsettings_theme": gs_cursor,
        "gtk3_theme": gtk3_cursor,
        "gtk4_theme": gtk4_cursor,
        "env_theme": env_xcursor_theme,
        "size": gs_cursor_size or gtk4_cursor_size or env_xcursor_size or 24,
        "gsettings_size": gs_cursor_size,
        "gtk4_size": gtk4_cursor_size,
        "env_xcursor_size": env_xcursor_size,
        "env_hyprcursor_size": env_hyprcursor_size,
        "installed": installed_cursors,
    }
    qt_section = {
        "style": qt_style,
        "icon_theme": qt_icon,
        "color_scheme_path": qt_scheme,
        "platform_theme_env": environ.get("QT_QPA_PLATFORMTHEME", "").strip() or None,
        "installed_styles": installed_qt_styles,
        "installed_color_schemes": installed_qt_schemes,
    }

    wallpaper = probe_wallpaper(paths["cache_wallpaper"], runner=runner, timeout=timeout)
    conflicts = compute_theme_conflicts(
        gtk=gtk_section,
        icons=icons_section,
        cursor=cursor_section,
        qt=qt_section,
        hyprland_lua_path=paths["hyprland_lua"],
    )

    return {
        "available": True,
        "wallpaper": wallpaper,
        "gtk": gtk_section,
        "icons": icons_section,
        "cursor": cursor_section,
        "qt": qt_section,
        "color_scheme": gs_color_scheme or "prefer-dark",
        "conflicts": conflicts,
        "error": None,
    }
