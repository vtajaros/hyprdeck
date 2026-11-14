"""Live Hyprland option reader and overrides-file state merger."""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any, Callable

from backend.core.constants import OVERRIDES_FILENAME, SHA256_ABSENT
from backend.core.include_block import IncludeBlockError, has_include
from backend.core.overrides import OverridesError, parse_sections
from backend.discovery.config_discovery import discover_config
from backend.editor.backups import compute_file_sha256
from backend.settings.catalog import CATALOG, CATALOG_BY_ID


def parse_getoption_output(raw: str, expected_type: str) -> tuple[bool, Any]:
    """Parse `hyprctl getoption <name> -j` output into (capable, typed_value)."""
    text = (raw or "").strip()
    if not text or text == "no such option":
        return False, None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return False, None
    if not isinstance(data, dict):
        return False, None

    if "bool" in data:
        return True, bool(data["bool"])
    if "int" in data:
        val = data["int"]
        if expected_type == "bool":
            return True, bool(val)
        return True, int(val)
    if "float" in data:
        return True, round(float(data["float"]), 4)
    if "str" in data:
        s = str(data["str"])
        if s == "[[EMPTY]]":
            s = ""
        return True, s
    if "css" in data:
        # e.g. "8 8 8 8" for gaps_in / gaps_out
        first = str(data["css"]).strip().split()[0]
        try:
            return True, int(first)
        except ValueError:
            return True, str(data["css"])
    if "gradient" in data:
        # e.g. "ee0b0e10 0deg" -> "0xee0b0e10"
        first = str(data["gradient"]).strip().split()[0]
        if re.fullmatch(r"[0-9a-fA-F]{6,8}", first):
            return True, "0x" + first.lower()
        return True, first
    return False, None


_CONFIG_CALL_RE = re.compile(r"hl\.config\s*\(\s*(\{.*\})\s*\)\s*$", re.DOTALL)


def _parse_lua_literal(tokens: list[str], pos: int) -> tuple[Any, int]:
    tok = tokens[pos]
    if tok == "{":
        pos += 1
        out: dict[str, Any] = {}
        while pos < len(tokens) and tokens[pos] != "}":
            key = tokens[pos]
            pos += 1
            if pos >= len(tokens) or tokens[pos] != "=":
                raise ValueError(f"Expected '=' after key {key!r}")
            pos += 1
            val, pos = _parse_lua_literal(tokens, pos)
            out[key] = val
            if pos < len(tokens) and tokens[pos] == ",":
                pos += 1
        if pos >= len(tokens) or tokens[pos] != "}":
            raise ValueError("Unclosed Lua table")
        return out, pos + 1
    if tok == "true":
        return True, pos + 1
    if tok == "false":
        return False, pos + 1
    if tok.startswith('"') and tok.endswith('"'):
        return json.loads(tok), pos + 1
    if "." in tok:
        return float(tok), pos + 1
    return int(tok), pos + 1


def _tokenize_lua_table(src: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    n = len(src)
    while i < n:
        ch = src[i]
        if ch.isspace():
            i += 1
        elif ch in "{}=,":
            tokens.append(ch)
            i += 1
        elif ch == '"':
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                elif src[j] == '"':
                    j += 1
                    break
                else:
                    j += 1
            tokens.append(src[i:j])
            i = j
        else:
            j = i
            while j < n and not src[j].isspace() and src[j] not in "{}=,":
                j += 1
            tokens.append(src[i:j])
            i = j
    return tokens


def extract_overrides_map(overrides_text: str) -> dict[str, Any]:
    """Extract {option_id: value} from managed sections of hks-overrides.lua."""
    result: dict[str, Any] = {}
    if not overrides_text.strip():
        return result
    sections = parse_sections(overrides_text)
    for body in sections.values():
        m = _CONFIG_CALL_RE.search(body.strip())
        if not m:
            continue
        try:
            tokens = _tokenize_lua_table(m.group(1))
            parsed, _ = _parse_lua_literal(tokens, 0)
        except Exception:
            continue
        if isinstance(parsed, dict):
            _flatten_to_options(parsed, "", result)
    return result


def _flatten_to_options(node: dict[str, Any], prefix: str, out: dict[str, Any]) -> None:
    for k, v in node.items():
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            _flatten_to_options(v, path, out)
        elif path in CATALOG_BY_ID:
            out[path] = v


def current_state(
    *,
    config_dir: str | None = None,
    entrypoint: str | None = None,
    no_live: bool = False,
    hyprctl_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    """Return merged live + overrides + capability state for all catalog options."""
    disc = discover_config(config_dir=config_dir, entrypoint=entrypoint, no_live=no_live)
    env_info = disc.environment

    include_installed = False
    if env_info.language == "lua" and os.path.isfile(env_info.entrypoint):
        try:
            with open(env_info.entrypoint, "r", encoding="utf-8") as f:
                include_installed = has_include(f.read())
        except IncludeBlockError:
            include_installed = False

    ov_path = os.path.join(env_info.config_dir, OVERRIDES_FILENAME)
    ov_present = os.path.isfile(ov_path)
    ov_sha = compute_file_sha256(ov_path) if ov_present else SHA256_ABSENT
    ov_values: dict[str, Any] = {}
    if ov_present:
        with open(ov_path, "r", encoding="utf-8") as f:
            try:
                ov_values = extract_overrides_map(f.read())
            except OverridesError:
                ov_values = {}

    run_fn = hyprctl_runner if hyprctl_runner is not None else subprocess.run
    options_out: list[dict[str, Any]] = []
    for opt in CATALOG:
        capable = False
        live_val: Any = None
        if not no_live or hyprctl_runner is not None:
            try:
                proc = run_fn(
                    ["hyprctl", "getoption", opt.getoption_name, "-j"],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=3.0,
                    check=False,
                )
                if proc.returncode == 0:
                    capable, live_val = parse_getoption_output(proc.stdout, opt.type)
            except (OSError, subprocess.SubprocessError):
                capable = False
                live_val = None

        ov_val = ov_values.get(opt.id)
        entry = opt.to_dict()
        entry["capable"] = capable
        entry["live_value"] = live_val
        entry["override_value"] = ov_val
        entry["effective_value"] = ov_val if ov_val is not None else live_val
        options_out.append(entry)

    return {
        "config_dir": env_info.config_dir,
        "entrypoint": env_info.entrypoint,
        "language": env_info.language,
        "include_installed": include_installed,
        "overrides_path": ov_path,
        "overrides_present": ov_present,
        "overrides_sha256": ov_sha,
        "options": options_out,
    }
