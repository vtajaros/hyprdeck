"""Read-only XDG MIME default applications and file-type associations probe."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

DEFAULT_APPS_CATEGORIES = [
    "All",
    "Web",
    "Files",
    "Documents",
    "Images",
    "Video",
    "Audio",
    "Text",
    "Archives",
    "Other",
]

# Curated common MIME types so users always see key file types & handlers even if
# mimeapps.list is minimal. Tuple: (mime_type, label, category, extensions)
_CURATED_MIMES: list[tuple[str, str, str, list[str]]] = [
    ("x-scheme-handler/http", "Web Browser (HTTP)", "Web", ["http://"]),
    ("x-scheme-handler/https", "Web Browser (HTTPS)", "Web", ["https://"]),
    ("text/html", "HTML Document", "Web", [".html", ".htm"]),
    ("x-scheme-handler/mailto", "Email Client (mailto)", "Web", ["mailto:"]),
    ("inode/directory", "File Manager (Folders)", "Files", ["folder"]),
    ("application/pdf", "PDF Document", "Documents", [".pdf"]),
    ("text/plain", "Plain Text", "Text", [".txt", ".log", ".md"]),
    ("application/json", "JSON File", "Text", [".json"]),
    ("image/png", "PNG Image", "Images", [".png"]),
    ("image/jpeg", "JPEG Image", "Images", [".jpg", ".jpeg"]),
    ("image/webp", "WebP Image", "Images", [".webp"]),
    ("image/svg+xml", "SVG Vector Image", "Images", [".svg"]),
    ("image/gif", "GIF Image", "Images", [".gif"]),
    ("video/mp4", "MP4 Video", "Video", [".mp4", ".m4v"]),
    ("video/x-matroska", "Matroska Video", "Video", [".mkv"]),
    ("video/webm", "WebM Video", "Video", [".webm"]),
    ("audio/mpeg", "MP3 Audio", "Audio", [".mp3"]),
    ("audio/flac", "FLAC Audio", "Audio", [".flac"]),
    ("audio/ogg", "Ogg Audio", "Audio", [".ogg"]),
    ("audio/x-wav", "WAV Audio", "Audio", [".wav"]),
    ("application/zip", "ZIP Archive", "Archives", [".zip"]),
    ("application/x-tar", "TAR Archive", "Archives", [".tar"]),
    ("application/gzip", "Gzip Archive", "Archives", [".gz"]),
]

_CURATED_MAP: dict[str, tuple[str, str, list[str]]] = {
    mime: (label, cat, exts) for mime, label, cat, exts in _CURATED_MIMES
}

_ESSENTIAL_MIMES: set[str] = {
    "x-scheme-handler/http",
    "x-scheme-handler/https",
    "x-scheme-handler/mailto",
    "inode/directory",
    "application/pdf",
    "text/plain",
    "image/png",
    "image/jpeg",
    "video/mp4",
    "video/x-matroska",
    "audio/mpeg",
    "audio/flac",
}


def _default_env() -> dict[str, str]:
    return dict(os.environ)


def _application_dirs(env: dict[str, str]) -> list[Path]:
    home = Path(env.get("HOME") or Path.home())
    data_home = Path(env.get("XDG_DATA_HOME") or (home / ".local/share"))
    raw_dirs = env.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    dirs = [data_home / "applications"]
    for d in raw_dirs.split(":"):
        d = d.strip()
        if d:
            dirs.append(Path(d) / "applications")
    return dirs


def _mimeapps_paths(env: dict[str, str]) -> list[Path]:
    home = Path(env.get("HOME") or Path.home())
    config_home = Path(env.get("XDG_CONFIG_HOME") or (home / ".config"))
    data_home = Path(env.get("XDG_DATA_HOME") or (home / ".local/share"))
    paths = [
        config_home / "mimeapps.list",
        data_home / "applications" / "mimeapps.list",
        Path("/etc/xdg/mimeapps.list"),
        Path("/usr/local/share/applications/mimeapps.list"),
        Path("/usr/share/applications/mimeapps.list"),
    ]
    return paths


def _parse_desktop_file(path: Path, desktop_id: str) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    in_entry = False
    name = ""
    icon = ""
    exec_cmd = ""
    mime_raw = ""
    no_display = False
    hidden = False
    terminal = False
    entry_type = ""

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_entry = line == "[Desktop Entry]"
            continue
        if not in_entry or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if key == "Type":
            entry_type = val
        elif key == "Name" and not name:
            name = val
        elif key == "Icon" and not icon:
            icon = val
        elif key == "Exec" and not exec_cmd:
            exec_cmd = val
        elif key == "MimeType":
            mime_raw = val
        elif key == "NoDisplay":
            no_display = val.lower() == "true"
        elif key == "Hidden":
            hidden = val.lower() == "true"
        elif key == "Terminal":
            terminal = val.lower() == "true"

    if entry_type and entry_type != "Application":
        return None
    if hidden:
        return None

    mimes = [m.strip() for m in mime_raw.split(";") if m.strip()]
    return {
        "desktop_id": desktop_id,
        "name": name or desktop_id.removesuffix(".desktop"),
        "icon": icon,
        "exec": exec_cmd,
        "mime_types": mimes,
        "no_display": no_display,
        "terminal": terminal,
    }


def _scan_desktop_apps(env: dict[str, str]) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    apps: dict[str, dict[str, Any]] = {}
    mime_to_apps: dict[str, list[str]] = {}

    for app_dir in _application_dirs(env):
        if not app_dir.is_dir():
            continue
        try:
            entries = sorted(app_dir.rglob("*.desktop"))
        except OSError:
            continue
        for p in entries:
            try:
                rel = p.relative_to(app_dir)
            except ValueError:
                continue
            desktop_id = "-".join(rel.parts)
            if desktop_id in apps:
                continue
            parsed = _parse_desktop_file(p, desktop_id)
            if parsed is None:
                continue
            apps[desktop_id] = parsed
            for mt in parsed["mime_types"]:
                mime_to_apps.setdefault(mt, [])
                if desktop_id not in mime_to_apps[mt]:
                    mime_to_apps[mt].append(desktop_id)

        # Also read mimeinfo.cache if present
        cache_path = app_dir / "mimeinfo.cache"
        if cache_path.is_file():
            try:
                for raw_line in cache_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith("[") or line.startswith("#") or "=" not in line:
                        continue
                    mt, vals = line.split("=", 1)
                    mt = mt.strip()
                    for did in vals.split(";"):
                        did = did.strip()
                        if did:
                            mime_to_apps.setdefault(mt, [])
                            if did not in mime_to_apps[mt]:
                                mime_to_apps[mt].append(did)
            except OSError:
                pass

    return apps, mime_to_apps


def _parse_mimeapps_files(
    paths: list[Path],
) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, set[str]]]:
    defaults: dict[str, list[str]] = {}
    added: dict[str, list[str]] = {}
    removed: dict[str, set[str]] = {}

    for p in paths:
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        section = ""
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line
                continue
            if "=" not in line:
                continue
            mt, vals = line.split("=", 1)
            mt = mt.strip()
            ids = [v.strip() for v in vals.split(";") if v.strip()]
            if not mt or not ids:
                continue

            if section == "[Default Applications]":
                defaults.setdefault(mt, [])
                for did in ids:
                    if did not in defaults[mt]:
                        defaults[mt].append(did)
            elif section == "[Added Associations]":
                added.setdefault(mt, [])
                for did in ids:
                    if did not in added[mt]:
                        added[mt].append(did)
            elif section == "[Removed Associations]":
                removed.setdefault(mt, set()).update(ids)

    return defaults, added, removed


def _load_etc_mime_extensions() -> dict[str, list[str]]:
    ext_map: dict[str, list[str]] = {}
    mime_types_file = Path("/etc/mime.types")
    if not mime_types_file.is_file():
        return ext_map
    try:
        for raw_line in mime_types_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            mt = parts[0]
            exts = [f".{e.lstrip('.')}" for e in parts[1:]]
            ext_map[mt] = exts[:4]
    except OSError:
        pass
    return ext_map


def _infer_category(mime_type: str) -> str:
    if mime_type in _CURATED_MAP:
        return _CURATED_MAP[mime_type][1]
    if mime_type.startswith("x-scheme-handler/http") or mime_type in {"text/html", "application/xhtml+xml"}:
        return "Web"
    if mime_type == "inode/directory":
        return "Files"
    if mime_type == "application/pdf" or "document" in mime_type or "opendocument" in mime_type or "word" in mime_type:
        return "Documents"
    if mime_type.startswith("image/"):
        return "Images"
    if mime_type.startswith("video/"):
        return "Video"
    if mime_type.startswith("audio/"):
        return "Audio"
    if mime_type.startswith("text/") or mime_type in {"application/json", "application/xml", "application/javascript"}:
        return "Text"
    if any(k in mime_type for k in ("zip", "tar", "gzip", "bzip", "xz", "7z", "rar", "archive", "compressed")):
        return "Archives"
    return "Other"


def _infer_label(mime_type: str) -> str:
    if mime_type in _CURATED_MAP:
        return _CURATED_MAP[mime_type][0]
    if mime_type.startswith("x-scheme-handler/"):
        scheme = mime_type.split("/", 1)[1].upper()
        return f"{scheme} Link Handler"
    sub = mime_type.split("/", 1)[1] if "/" in mime_type else mime_type
    sub = sub.removeprefix("x-").replace("-", " ").replace(".", " ")
    return sub.title()


def get_default_apps_state(
    env: dict[str, str] | None = None,
    query_runner: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Return XDG MIME default applications and compatible app candidates."""
    effective_env = env if env is not None else _default_env()
    apps, mime_to_apps = _scan_desktop_apps(effective_env)
    defaults, added, removed = _parse_mimeapps_files(_mimeapps_paths(effective_env))
    etc_exts = _load_etc_mime_extensions()
    xdg_mime_bin = shutil.which("xdg-mime")

    def _query_xdg_mime(mt: str) -> str:
        if query_runner is not None:
            return query_runner(mt).strip()
        if not xdg_mime_bin:
            return ""
        try:
            proc = subprocess.run(
                [xdg_mime_bin, "query", "default", mt],
                capture_output=True,
                text=True,
                timeout=2.0,
                env=effective_env,
                check=False,
            )
            if proc.returncode == 0:
                return proc.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
        return ""

    # Ordered list of MIME types: curated first, then any configured in mimeapps.list
    seen_mimes: set[str] = set()
    ordered_mimes: list[str] = []
    for mt, _, _, _ in _CURATED_MIMES:
        if mt not in seen_mimes:
            seen_mimes.add(mt)
            ordered_mimes.append(mt)
    for mt in sorted(set(defaults.keys()) | set(added.keys())):
        if mt not in seen_mimes:
            seen_mimes.add(mt)
            ordered_mimes.append(mt)

    associations: list[dict[str, Any]] = []
    configured_count = 0

    for mt in ordered_mimes:
        rem = removed.get(mt, set())

        # Determine default desktop ID
        default_id = ""
        for did in defaults.get(mt, []):
            if did not in rem and (did in apps or did.endswith(".desktop")):
                default_id = did
                break
        if not default_id and mt in _CURATED_MAP and query_runner is not None:
            # Optional injected xdg-mime query hook (avoid spawning 20+ subprocesses on live load)
            queried = _query_xdg_mime(mt)
            if queried and queried not in rem:
                default_id = queried
        if not default_id:
            # Fallback to first added association or mimeinfo candidate if any
            for did in added.get(mt, []) + mime_to_apps.get(mt, []):
                if did not in rem and did in apps:
                    default_id = did
                    break

        if default_id:
            configured_count += 1

        default_app = apps.get(default_id)
        default_name = default_app["name"] if default_app else (default_id.removesuffix(".desktop") if default_id else "")

        # Gather candidates
        cand_ids: list[str] = []
        for did in ([default_id] if default_id else []) + added.get(mt, []) + mime_to_apps.get(mt, []):
            if not did or did in rem or did in cand_ids:
                continue
            cand_ids.append(did)

        candidates: list[dict[str, Any]] = []
        for did in cand_ids:
            info = apps.get(did)
            if info is None:
                continue
            candidates.append(
                {
                    "desktop_id": did,
                    "name": info["name"],
                    "exec": info["exec"],
                    "terminal": bool(info["terminal"]),
                }
            )

        curated = _CURATED_MAP.get(mt)
        extensions = curated[2] if curated else etc_exts.get(mt, [])
        associations.append(
            {
                "mime_type": mt,
                "label": _infer_label(mt),
                "category": _infer_category(mt),
                "extensions": extensions,
                "curated": mt in _CURATED_MAP,
                "essential": mt in _ESSENTIAL_MIMES,
                "default_desktop_id": default_id,
                "default_app_name": default_name,
                "candidates": candidates,
            }
        )

    installed_apps = sorted(
        (
            {
                "desktop_id": did,
                "name": info["name"],
                "exec": info["exec"],
                "terminal": bool(info["terminal"]),
            }
            for did, info in apps.items()
            if not info.get("no_display")
        ),
        key=lambda item: (item["name"].lower(), item["desktop_id"].lower()),
    )

    return {
        "available": True,
        "xdg_mime_available": bool(xdg_mime_bin),
        "categories": DEFAULT_APPS_CATEGORIES,
        "associations": associations,
        "installed_apps": installed_apps,
        "summary": {
            "total_associations": len(associations),
            "configured_defaults": configured_count,
            "installed_apps": len(installed_apps),
        },
    }
