"""Default applications mutation operations (setting XDG MIME defaults)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from backend.settings.default_apps.state import _scan_desktop_apps

_MIME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.+_-]*/[a-zA-Z0-9][a-zA-Z0-9.+_-]*$")
_DESKTOP_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*\.desktop$")


def set_default_app(
    mime_type: str,
    desktop_id: str,
    *,
    dry_run: bool = False,
    env: dict[str, str] | None = None,
    runner: Callable[[list[str]], tuple[int, str, str]] | None = None,
) -> dict[str, Any]:
    """Set the default `.desktop` application for `mime_type`."""
    mt = (mime_type or "").strip()
    did = (desktop_id or "").strip()

    if not _MIME_RE.match(mt):
        return {"ok": False, "error": f"Invalid MIME type: {mime_type!r}"}
    if not _DESKTOP_RE.match(did):
        return {"ok": False, "error": f"Invalid desktop ID: {desktop_id!r}"}

    effective_env = env if env is not None else dict(os.environ)
    apps, _ = _scan_desktop_apps(effective_env)
    if did not in apps:
        return {"ok": False, "error": f"Application not found: {did}"}

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "mime_type": mt,
            "desktop_id": did,
            "app_name": apps[did]["name"],
        }

    if runner is not None:
        rc, out, err = runner(["xdg-mime", "default", did, mt])
        if rc != 0:
            return {"ok": False, "error": (err or out or f"xdg-mime exited with {rc}").strip()}
        return {
            "ok": True,
            "dry_run": False,
            "mime_type": mt,
            "desktop_id": did,
            "app_name": apps[did]["name"],
        }

    xdg_mime_bin = shutil.which("xdg-mime")
    if xdg_mime_bin:
        try:
            proc = subprocess.run(
                [xdg_mime_bin, "default", did, mt],
                capture_output=True,
                text=True,
                timeout=5.0,
                env=effective_env,
                check=False,
            )
            if proc.returncode != 0:
                return {
                    "ok": False,
                    "error": (proc.stderr or proc.stdout or f"xdg-mime exited with {proc.returncode}").strip(),
                }
            return {
                "ok": True,
                "dry_run": False,
                "mime_type": mt,
                "desktop_id": did,
                "app_name": apps[did]["name"],
            }
        except (OSError, subprocess.SubprocessError) as exc:
            return {"ok": False, "error": f"xdg-mime failed: {exc}"}

    # Fallback: write directly to ~/.config/mimeapps.list [Default Applications]
    home = Path(effective_env.get("HOME") or Path.home())
    config_home = Path(effective_env.get("XDG_CONFIG_HOME") or (home / ".config"))
    mimeapps_path = config_home / "mimeapps.list"
    _update_mimeapps_default(mimeapps_path, mt, did)
    return {
        "ok": True,
        "dry_run": False,
        "mime_type": mt,
        "desktop_id": did,
        "app_name": apps[did]["name"],
    }


def _update_mimeapps_default(path: Path, mime_type: str, desktop_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.is_file() else []
    out: list[str] = []
    in_defaults = False
    found_defaults = False
    replaced = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_defaults and not replaced:
                out.append(f"{mime_type}={desktop_id}")
                replaced = True
            in_defaults = stripped == "[Default Applications]"
            if in_defaults:
                found_defaults = True
            out.append(line)
            continue
        if in_defaults and "=" in line and not stripped.startswith("#"):
            k, _ = line.split("=", 1)
            if k.strip() == mime_type:
                out.append(f"{mime_type}={desktop_id}")
                replaced = True
                continue
        out.append(line)

    if not found_defaults:
        if out and out[-1].strip():
            out.append("")
        out.append("[Default Applications]")
    if not replaced:
        out.append(f"{mime_type}={desktop_id}")

    path.write_text("\n".join(out) + "\n", encoding="utf-8")
