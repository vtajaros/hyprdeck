"""System theme mutation operations with validation, backup, atomic write, and readback."""

from __future__ import annotations

import os
import re
import subprocess
from typing import Any, Callable, Mapping

from backend.core.live_cmd import DEFAULT_LIVE_CMD_TIMEOUT_SECONDS, LiveRunner, run_live_cmd
from backend.editor.backups import (
    BackupError,
    atomic_write_bytes,
    create_backup,
    restore_backup,
)
from backend.settings.themes.state import (
    discover_gtk_themes,
    discover_icon_and_cursor_themes,
    discover_qt_color_schemes,
    discover_qt_styles,
    get_themes_state,
    parse_ini_key,
    resolve_themes_paths,
)

MIN_CURSOR_SIZE = 16
MAX_CURSOR_SIZE = 64
_HOSTILE_CHARS_RE = re.compile(r"[\x00-\x1f\x7f=/\\;|&$`<>(){}*?'\"`]")


def _fail(error: str, before: Any = None, after: Any = None, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "before": before, "after": after, "error": error}
    out.update(extra)
    return out


def validate_theme_name(name: Any) -> str:
    """Reject empty, path-traversal, INI-injection, or shell-metacharacter theme names."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Theme name must be a non-empty string.")
    cleaned = name.strip()
    if ".." in cleaned or _HOSTILE_CHARS_RE.search(cleaned):
        raise ValueError(f"Unsafe or invalid theme name: {name!r}.")
    return cleaned


def validate_cursor_size(size: Any) -> int:
    if isinstance(size, bool) or size is None:
        raise ValueError(f"Cursor size must be an integer between {MIN_CURSOR_SIZE} and {MAX_CURSOR_SIZE}.")
    try:
        n = int(size)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Cursor size must be an integer, got {size!r}.") from exc
    if n < MIN_CURSOR_SIZE or n > MAX_CURSOR_SIZE:
        raise ValueError(f"Cursor size must be between {MIN_CURSOR_SIZE} and {MAX_CURSOR_SIZE}, got {n}.")
    return n


def edit_ini_key(raw: str, section: str, key: str, value: str) -> str:
    """Update or insert `key` in `[section]` while preserving all other lines, order, and trailing newline."""
    had_trailing_nl = raw.endswith("\n") if raw else True
    lines = raw.splitlines() if raw else []
    target_sec = section.strip()
    in_section = False
    sec_found = False
    sec_end_idx = len(lines)
    replaced = False

    out_lines: list[str] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_section and not replaced:
                # Insert at end of section (before blank lines trailing the section)
                insert_at = len(out_lines)
                while insert_at > 0 and out_lines[insert_at - 1].strip() == "":
                    insert_at -= 1
                out_lines.insert(insert_at, f"{key}={value}")
                replaced = True
            in_section = (stripped[1:-1].strip() == target_sec)
            if in_section:
                sec_found = True
            out_lines.append(line)
            continue

        if in_section and not replaced and stripped and not stripped.startswith(("#", ";")) and "=" in line:
            lhs, _ = line.split("=", 1)
            if lhs.strip() == key:
                # Preserve spacing style (`k = v` vs `k=v`)
                sep = " = " if (" = " in line[: len(lhs) + 3]) else "="
                out_lines.append(f"{lhs.rstrip()}{sep}{value}")
                replaced = True
                continue

        out_lines.append(line)

    if not replaced:
        if sec_found:
            insert_at = len(out_lines)
            while insert_at > 0 and out_lines[insert_at - 1].strip() == "":
                insert_at -= 1
            out_lines.insert(insert_at, f"{key}={value}")
        else:
            if out_lines and out_lines[-1].strip() != "":
                out_lines.append("")
            out_lines.append(f"[{target_sec}]")
            out_lines.append(f"{key}={value}")

    result = "\n".join(out_lines)
    if had_trailing_nl:
        result += "\n"
    return result


def _write_ini_with_backup(
    path: str,
    section: str,
    updates: dict[str, str],
    *,
    default_mode: int = 0o600,
    backup_dir: str | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[bool, str | None]:
    """Backup (if exists), atomically update INI keys, and readback-verify with rollback."""
    env_dict = dict(env) if env is not None else None
    existed = os.path.isfile(path)
    record = None
    raw = ""

    if existed:
        try:
            record = create_backup(path, backup_dir=backup_dir, env=env_dict)
        except BackupError as exc:
            return False, f"Backup failed for {path}: {exc}"
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()

    updated = raw
    for k, v in updates.items():
        updated = edit_ini_key(updated, section, k, v)

    try:
        atomic_write_bytes(
            path,
            updated.encode("utf-8"),
            mode_source=path if existed else None,
        )
        if not existed:
            os.chmod(path, default_mode)
    except OSError as exc:
        if record is not None:
            try:
                restore_backup(record, backup_dir=backup_dir, force=True, env=env_dict)
            except BackupError:
                pass
        return False, f"Write failed for {path}: {exc}"

    # Readback verify
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            verify_raw = f.read()
        for k, v in updates.items():
            got = parse_ini_key(verify_raw, section, k)
            if got != v:
                raise ValueError(f"INI readback mismatch for [{section}] {k}: expected {v!r}, got {got!r}")
    except Exception as exc:
        if record is not None:
            try:
                restore_backup(record, backup_dir=backup_dir, force=True, env=env_dict)
            except BackupError:
                pass
        return False, str(exc)

    return True, None


def _gsettings_set(
    key: str,
    value: str,
    *,
    runner: LiveRunner | None,
    timeout: float,
) -> tuple[bool, str | None]:
    res = run_live_cmd(
        ["gsettings", "set", "org.gnome.desktop.interface", key, value],
        timeout=timeout,
        runner=runner,
    )
    if not res.ok:
        return False, res.err.strip() or f"gsettings set {key} failed (rc={res.rc})"
    return True, None


def set_gtk_theme(
    name: str,
    *,
    runner: LiveRunner | None = None,
    env: Mapping[str, str] | None = None,
    backup_dir: str | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    try:
        clean = validate_theme_name(name)
    except ValueError as exc:
        return _fail(str(exc))

    environ = env if env is not None else os.environ
    paths = resolve_themes_paths(environ)
    installed = discover_gtk_themes(paths)
    if clean not in installed:
        return _fail(f"Unknown GTK theme: {clean!r}. Installed: {installed}")

    before_state = get_themes_state(runner=runner, env=environ, timeout=timeout)
    before_gtk = before_state["gtk"]

    ok_gs, err_gs = _gsettings_set("gtk-theme", clean, runner=runner, timeout=timeout)
    if not ok_gs:
        return _fail(err_gs or "gsettings failed", before=before_gtk)

    for ini_path in (paths["gtk3_ini"], paths["gtk4_ini"]):
        ok_ini, err_ini = _write_ini_with_backup(
            ini_path, "Settings", {"gtk-theme-name": clean},
            default_mode=0o600, backup_dir=backup_dir, env=environ,
        )
        if not ok_ini:
            return _fail(err_ini or f"Failed updating {ini_path}", before=before_gtk)

    after_state = get_themes_state(runner=runner, env=environ, timeout=timeout)
    after_gtk = after_state["gtk"]
    if after_gtk.get("gsettings_theme") != clean:
        return _fail(
            f"gsettings readback mismatch: expected {clean!r}, got {after_gtk.get('gsettings_theme')!r}.",
            before=before_gtk, after=after_gtk,
        )

    scope = "next_login" if after_gtk.get("env_theme") else "new_apps"
    return {
        "ok": True,
        "before": before_gtk,
        "after": after_gtk,
        "apply_scope": scope,
        "error": None,
    }


def set_icon_theme(
    name: str,
    *,
    runner: LiveRunner | None = None,
    env: Mapping[str, str] | None = None,
    backup_dir: str | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    try:
        clean = validate_theme_name(name)
    except ValueError as exc:
        return _fail(str(exc))

    environ = env if env is not None else os.environ
    paths = resolve_themes_paths(environ)
    installed_icons, _ = discover_icon_and_cursor_themes(paths)
    if clean not in installed_icons:
        return _fail(f"Unknown icon theme: {clean!r}.")

    before_state = get_themes_state(runner=runner, env=environ, timeout=timeout)
    before_icons = before_state["icons"]

    ok_gs, err_gs = _gsettings_set("icon-theme", clean, runner=runner, timeout=timeout)
    if not ok_gs:
        return _fail(err_gs or "gsettings failed", before=before_icons)

    for ini_path in (paths["gtk3_ini"], paths["gtk4_ini"]):
        ok_ini, err_ini = _write_ini_with_backup(
            ini_path, "Settings", {"gtk-icon-theme-name": clean},
            default_mode=0o600, backup_dir=backup_dir, env=environ,
        )
        if not ok_ini:
            return _fail(err_ini or f"Failed updating {ini_path}", before=before_icons)

    after_state = get_themes_state(runner=runner, env=environ, timeout=timeout)
    after_icons = after_state["icons"]
    if after_icons.get("gsettings_theme") != clean:
        return _fail(
            f"Icon readback mismatch: expected {clean!r}, got {after_icons.get('gsettings_theme')!r}.",
            before=before_icons, after=after_icons,
        )

    warning = (
        None if clean == "Papirus-Dynamic"
        else f"matugen-icons-sync will revert icon theme to 'Papirus-Dynamic' on the next wallpaper change."
    )
    return {
        "ok": True,
        "before": before_icons,
        "after": after_icons,
        "apply_scope": "new_apps",
        "warning": warning,
        "error": None,
    }


def set_cursor(
    name: str,
    size: int | None = None,
    *,
    runner: LiveRunner | None = None,
    env: Mapping[str, str] | None = None,
    backup_dir: str | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    try:
        clean = validate_theme_name(name)
        target_size = validate_cursor_size(size) if size is not None else None
    except ValueError as exc:
        return _fail(str(exc))

    environ = env if env is not None else os.environ
    paths = resolve_themes_paths(environ)
    _, installed_cursors = discover_icon_and_cursor_themes(paths)
    if clean not in installed_cursors:
        return _fail(f"Unknown or non-cursor theme: {clean!r}.")

    before_state = get_themes_state(runner=runner, env=environ, timeout=timeout)
    before_cursor = before_state["cursor"]
    if target_size is None:
        target_size = int(before_cursor.get("size") or 24)

    hypr_res = run_live_cmd(
        ["hyprctl", "setcursor", clean, str(target_size)],
        timeout=timeout,
        runner=runner,
    )
    if not hypr_res.ok:
        return _fail(
            hypr_res.err.strip() or f"hyprctl setcursor failed (rc={hypr_res.rc})",
            before=before_cursor,
        )

    ok_gs, err_gs = _gsettings_set("cursor-theme", clean, runner=runner, timeout=timeout)
    if not ok_gs:
        return _fail(err_gs or "gsettings cursor-theme failed", before=before_cursor)
    ok_gs_sz, err_gs_sz = _gsettings_set("cursor-size", str(target_size), runner=runner, timeout=timeout)
    if not ok_gs_sz:
        return _fail(err_gs_sz or "gsettings cursor-size failed", before=before_cursor)

    ini_updates = {
        "gtk-cursor-theme-name": clean,
        "gtk-cursor-theme-size": str(target_size),
    }
    for ini_path in (paths["gtk3_ini"], paths["gtk4_ini"]):
        ok_ini, err_ini = _write_ini_with_backup(
            ini_path, "Settings", ini_updates,
            default_mode=0o600, backup_dir=backup_dir, env=environ,
        )
        if not ok_ini:
            return _fail(err_ini or f"Failed updating {ini_path}", before=before_cursor)

    after_state = get_themes_state(runner=runner, env=environ, timeout=timeout)
    after_cursor = after_state["cursor"]
    if after_cursor.get("gsettings_theme") != clean or after_cursor.get("gtk4_theme") != clean:
        return _fail(
            f"Cursor readback mismatch: expected {clean!r}, got gsettings={after_cursor.get('gsettings_theme')!r}, gtk4={after_cursor.get('gtk4_theme')!r}.",
            before=before_cursor, after=after_cursor,
        )

    return {
        "ok": True,
        "before": before_cursor,
        "after": after_cursor,
        "apply_scope": "live",
        "error": None,
    }


def set_qt(
    *,
    style: str | None = None,
    icon_theme: str | None = None,
    color_scheme_path: str | None = None,
    runner: LiveRunner | None = None,
    env: Mapping[str, str] | None = None,
    backup_dir: str | None = None,
    qt_plugin_dirs: tuple[str, ...] | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if style is None and icon_theme is None and color_scheme_path is None:
        return _fail("At least one of style, icon_theme, or color_scheme_path must be specified.")

    environ = env if env is not None else os.environ
    paths = resolve_themes_paths(environ)
    updates: dict[str, str] = {}

    if style is not None:
        try:
            clean_style = validate_theme_name(style)
        except ValueError as exc:
            return _fail(str(exc))
        installed_styles = discover_qt_styles(qt_plugin_dirs)
        if clean_style not in installed_styles:
            return _fail(f"Unknown Qt style: {clean_style!r}. Installed: {installed_styles}")
        updates["style"] = clean_style

    if icon_theme is not None:
        try:
            clean_icon = validate_theme_name(icon_theme)
        except ValueError as exc:
            return _fail(str(exc))
        installed_icons, _ = discover_icon_and_cursor_themes(paths)
        if clean_icon not in installed_icons:
            return _fail(f"Unknown icon theme: {clean_icon!r}.")
        updates["icon_theme"] = clean_icon

    if color_scheme_path is not None:
        schemes = discover_qt_color_schemes(paths["qt6ct_colors_dir"])
        valid_paths = {s["path"]: s["path"] for s in schemes}
        valid_names = {s["name"]: s["path"] for s in schemes}
        valid_files = {os.path.basename(s["path"]): s["path"] for s in schemes}
        cand = str(color_scheme_path).strip()
        resolved_scheme = valid_paths.get(cand) or valid_names.get(cand) or valid_files.get(cand)
        if not resolved_scheme:
            return _fail(f"Unknown Qt6ct color scheme: {color_scheme_path!r}.")
        updates["color_scheme_path"] = resolved_scheme

    before_state = get_themes_state(runner=runner, env=environ, timeout=timeout, qt_plugin_dirs=qt_plugin_dirs)
    before_qt = before_state["qt"]

    ok_qt, err_qt = _write_ini_with_backup(
        paths["qt6ct_conf"], "Appearance", updates,
        default_mode=0o644, backup_dir=backup_dir, env=environ,
    )
    if not ok_qt:
        return _fail(err_qt or "Failed updating qt6ct.conf", before=before_qt)

    after_state = get_themes_state(runner=runner, env=environ, timeout=timeout, qt_plugin_dirs=qt_plugin_dirs)
    after_qt = after_state["qt"]
    return {
        "ok": True,
        "before": before_qt,
        "after": after_qt,
        "apply_scope": "new_apps",
        "error": None,
    }


def open_wallpaper_picker(
    *,
    env: Mapping[str, str] | None = None,
    spawner: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Launch ~/.local/bin/wallpaper-carousel detached (argv, never shell=True)."""
    environ = env if env is not None else os.environ
    paths = resolve_themes_paths(environ)
    carousel = paths["wallpaper_carousel"]
    if not os.path.isfile(carousel):
        return _fail(f"Wallpaper picker not found: {carousel}")

    try:
        if spawner is not None:
            spawner([carousel])
        else:
            subprocess.Popen(
                [carousel],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                shell=False,
            )
    except OSError as exc:
        return _fail(f"Failed to launch wallpaper picker: {exc}")
    return {"ok": True, "launched": carousel, "error": None}
