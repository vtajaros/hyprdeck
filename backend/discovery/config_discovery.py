"""Configuration directory and entrypoint discovery for Hyprland Keybind Studio."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
from dataclasses import dataclass, field
from typing import Any

from backend.models.types import Diagnostic, EnvironmentInfo, FileRecord, ShadowedFile


class DiscoveryError(Exception):
    """Raised when configuration directory or entrypoint cannot be found."""


@dataclass(slots=True)
class DiscoveryResult:
    environment: EnvironmentInfo
    entrypoint_record: FileRecord
    diagnostics: list[Diagnostic] = field(default_factory=list)
    live_binds: list[dict[str, Any]] | None = None


def resolve_default_config_dir(env: dict[str, str] | None = None) -> str:
    """Resolve $XDG_CONFIG_HOME/hypr else ~/.config/hypr."""
    environ = env if env is not None else os.environ
    xdg = environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg:
        return os.path.abspath(os.path.join(os.path.expanduser(xdg), "hypr"))
    home = environ.get("HOME", "").strip() or os.path.expanduser("~")
    return os.path.abspath(os.path.join(home, ".config", "hypr"))


def build_file_record(path: str, role: str = "loaded") -> FileRecord:
    """Read a single file and compute its FileRecord metadata."""
    abs_path = os.path.abspath(path)
    real_path = os.path.realpath(abs_path)
    with open(abs_path, "rb") as f:
        raw = f.read()
    sha256 = hashlib.sha256(raw).hexdigest()
    line_count = len(raw.splitlines())
    return FileRecord(
        path=abs_path,
        real_path=real_path,
        role=role,
        sha256=sha256,
        line_count=line_count,
    )


def probe_hyprctl_version(timeout: float = 3.0) -> str | None:
    """Optionally query `hyprctl version -j`. Degrades gracefully to None."""
    try:
        proc = subprocess.run(
            ["hyprctl", "version", "-j"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        data = json.loads(proc.stdout)
        if isinstance(data, dict):
            tag = data.get("tag") or data.get("version")
            commit = data.get("commit")
            if tag and commit and isinstance(commit, str):
                return f"{tag} ({commit[:8]})"
            if tag:
                return str(tag)
            branch = data.get("branch")
            if branch:
                return str(branch)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return None


def probe_hyprctl_binds(timeout: float = 3.0) -> list[dict[str, Any]] | None:
    """Optionally query `hyprctl binds -j`. Degrades gracefully to None."""
    try:
        proc = subprocess.run(
            ["hyprctl", "binds", "-j"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        data = json.loads(proc.stdout)
        if isinstance(data, list):
            return [b for b in data if isinstance(b, dict) and b.get("submap") != "hks_record"]
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return None


def detect_live_language(live_binds: list[dict[str, Any]]) -> str:
    """Inspect `hyprctl binds -j` entries to detect whether Lua or Hyprlang is active."""
    for entry in live_binds:
        if isinstance(entry, dict):
            dsp = entry.get("dispatcher")
            if isinstance(dsp, str) and dsp.startswith("HL.Dispatcher("):
                return "lua"
    return "hyprlang"


def discover_config(
    config_dir: str | None = None,
    entrypoint: str | None = None,
    no_live: bool = False,
    live_binds_override: list[dict[str, Any]] | None = None,
    hyprland_version_override: str | None = None,
    env: dict[str, str] | None = None,
) -> DiscoveryResult:
    """Discover entrypoint and environment without ever globbing the config directory."""
    diagnostics: list[Diagnostic] = []
    shadowed: list[ShadowedFile] = []

    entrypoint_source = "auto"
    if entrypoint is not None:
        entrypoint_source = "explicit"
        exp_entry = os.path.expanduser(entrypoint)
        if config_dir is not None:
            resolved_dir = os.path.abspath(os.path.expanduser(config_dir))
            if not os.path.isabs(exp_entry) and not os.path.exists(exp_entry):
                candidate = os.path.join(resolved_dir, exp_entry)
                resolved_entry = os.path.abspath(candidate)
            else:
                resolved_entry = os.path.abspath(exp_entry)
        else:
            resolved_entry = os.path.abspath(exp_entry)
            resolved_dir = os.path.dirname(resolved_entry)

        if not os.path.isdir(resolved_dir):
            raise DiscoveryError(f"Configuration directory does not exist: {resolved_dir}")
        if not os.path.isfile(resolved_entry):
            raise DiscoveryError(f"Entrypoint file does not exist: {resolved_entry}")

        language = "lua" if resolved_entry.endswith(".lua") else "hyprlang"
        lua_default = os.path.join(resolved_dir, "hyprland.lua")
        conf_default = os.path.join(resolved_dir, "hyprland.conf")
        if resolved_entry == lua_default and os.path.isfile(conf_default):
            shadowed.append(
                ShadowedFile(
                    path=conf_default,
                    reason="hyprland.lua takes precedence over hyprland.conf",
                )
            )
        elif resolved_entry == conf_default and os.path.isfile(lua_default):
            shadowed.append(
                ShadowedFile(
                    path=lua_default,
                    reason="explicit --entrypoint selected hyprland.conf over hyprland.lua",
                )
            )
    elif config_dir is not None and os.path.isfile(os.path.expanduser(config_dir)):
        entrypoint_source = "explicit"
        resolved_entry = os.path.abspath(os.path.expanduser(config_dir))
        resolved_dir = os.path.dirname(resolved_entry)
        language = "lua" if resolved_entry.endswith(".lua") else "hyprlang"
        lua_default = os.path.join(resolved_dir, "hyprland.lua")
        conf_default = os.path.join(resolved_dir, "hyprland.conf")
        if resolved_entry == lua_default and os.path.isfile(conf_default):
            shadowed.append(
                ShadowedFile(
                    path=conf_default,
                    reason="hyprland.lua takes precedence over hyprland.conf",
                )
            )
        elif resolved_entry == conf_default and os.path.isfile(lua_default):
            shadowed.append(
                ShadowedFile(
                    path=lua_default,
                    reason="explicit entrypoint selected hyprland.conf over hyprland.lua",
                )
            )
    else:
        resolved_dir = (
            os.path.abspath(os.path.expanduser(config_dir))
            if config_dir is not None
            else resolve_default_config_dir(env=env)
        )
        if not os.path.isdir(resolved_dir):
            raise DiscoveryError(f"Configuration directory does not exist: {resolved_dir}")

        # NEVER glob the directory; probe only the two canonical filenames.
        lua_candidate = os.path.join(resolved_dir, "hyprland.lua")
        conf_candidate = os.path.join(resolved_dir, "hyprland.conf")
        has_lua = os.path.isfile(lua_candidate)
        has_conf = os.path.isfile(conf_candidate)

        if has_lua:
            resolved_entry = lua_candidate
            language = "lua"
            if has_conf:
                shadowed.append(
                    ShadowedFile(
                        path=conf_candidate,
                        reason="hyprland.lua takes precedence over hyprland.conf",
                    )
                )
        elif has_conf:
            resolved_entry = conf_candidate
            language = "hyprlang"
        else:
            raise DiscoveryError(
                f"Neither hyprland.lua nor hyprland.conf found in {resolved_dir}"
            )

    detected_by = "file-precedence"
    hypr_version: str | None = hyprland_version_override
    live_binds: list[dict[str, Any]] | None = live_binds_override

    if not no_live:
        if hypr_version is None:
            hypr_version = probe_hyprctl_version()
        if live_binds is None:
            live_binds = probe_hyprctl_binds()

    if live_binds is not None:
        live_lang = detect_live_language(live_binds)
        if live_lang == language:
            detected_by = "live-hyprctl"
        else:
            detected_by = "file-precedence"
            if entrypoint_source == "auto":
                diagnostics.append(
                    Diagnostic(
                        level="warning",
                        code="entrypoint_live_mismatch",
                        message=(
                            f"File precedence selected {language} ({os.path.basename(resolved_entry)}), "
                            f"but live hyprctl binds indicate {live_lang} is currently active."
                        ),
                        file=resolved_entry,
                        line=1,
                    )
                )

    entry_record = build_file_record(resolved_entry, role="entrypoint")
    env_info = EnvironmentInfo(
        config_dir=resolved_dir,
        entrypoint=resolved_entry,
        language=language,
        detected_by=detected_by,
        entrypoint_source=entrypoint_source,
        shadowed=shadowed,
        hyprland_version=hypr_version,
        python=platform.python_version(),
    )
    return DiscoveryResult(
        environment=env_info,
        entrypoint_record=entry_record,
        diagnostics=diagnostics,
        live_binds=live_binds,
    )
