"""System theme state and safe mutation operations (GTK, icons, cursor, Qt6ct, wallpaper)."""

from backend.settings.themes.ops import (
    MAX_CURSOR_SIZE,
    MIN_CURSOR_SIZE,
    edit_ini_key,
    open_wallpaper_picker,
    set_cursor,
    set_gtk_theme,
    set_icon_theme,
    set_qt,
    validate_cursor_size,
    validate_theme_name,
)
from backend.settings.themes.state import (
    compute_theme_conflicts,
    discover_gtk_themes,
    discover_icon_and_cursor_themes,
    discover_qt_color_schemes,
    discover_qt_styles,
    get_themes_state,
    parse_ini_key,
    probe_wallpaper,
    resolve_themes_paths,
)

__all__ = [
    "MAX_CURSOR_SIZE",
    "MIN_CURSOR_SIZE",
    "compute_theme_conflicts",
    "discover_gtk_themes",
    "discover_icon_and_cursor_themes",
    "discover_qt_color_schemes",
    "discover_qt_styles",
    "edit_ini_key",
    "get_themes_state",
    "open_wallpaper_picker",
    "parse_ini_key",
    "probe_wallpaper",
    "resolve_themes_paths",
    "set_cursor",
    "set_gtk_theme",
    "set_icon_theme",
    "set_qt",
    "validate_cursor_size",
    "validate_theme_name",
]
