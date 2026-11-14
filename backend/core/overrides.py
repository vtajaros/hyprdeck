"""Pure managed-document model and Lua value serializer for hks-overrides.lua."""

from __future__ import annotations

import math
import re
from typing import Any

from backend.core.constants import (
    OVERRIDES_HEADER,
    SECTION_BEGIN_PREFIX,
    SECTION_END_PREFIX,
    section_begin_marker,
    section_end_marker,
)
from backend.editor.codegen import encode_lua_string

_LUA_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SECTION_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

_LUA_KEYWORDS: frozenset[str] = frozenset(
    {
        "and",
        "break",
        "do",
        "else",
        "elseif",
        "end",
        "false",
        "for",
        "function",
        "goto",
        "if",
        "in",
        "local",
        "nil",
        "not",
        "or",
        "repeat",
        "return",
        "then",
        "true",
        "until",
        "while",
    }
)


class OverridesError(ValueError):
    """Raised on invalid overrides sections, keys, or Lua values."""


def create_overrides_text() -> str:
    """Return initial content (with generated-file header) for a newly created overrides file."""
    return OVERRIDES_HEADER


def _validate_section_name(name: str) -> str:
    if not isinstance(name, str) or not _SECTION_NAME_RE.match(name):
        raise OverridesError(f"Invalid overrides section name: {name!r}")
    return name


def _validate_lua_key(key: Any) -> str:
    if not isinstance(key, str):
        raise OverridesError(f"Lua table key must be a string, got {type(key).__name__}")
    if not _LUA_IDENTIFIER_RE.match(key) or key in _LUA_KEYWORDS:
        raise OverridesError(f"Lua table key must be a valid non-keyword identifier: {key!r}")
    return key


def serialize_lua_value(value: Any) -> str:
    """Serialize Python dict/list/str/int/float/bool into a deterministic Lua literal.

    Rejects None, NaN/inf, non-identifier dict keys, and unsupported types.
    """
    if value is None:
        raise OverridesError("None is not a valid Lua value; omit the key instead")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise OverridesError(f"Non-finite float is not valid in Lua: {value!r}")
        return repr(value)
    if isinstance(value, str):
        return encode_lua_string(value, allow_multiline=True)
    if isinstance(value, (list, tuple)):
        if not value:
            return "{}"
        items = ", ".join(serialize_lua_value(item) for item in value)
        return f"{{ {items} }}"
    if isinstance(value, dict):
        if not value:
            return "{}"
        parts: list[str] = []
        for k in sorted(value.keys()):
            valid_k = _validate_lua_key(k)
            parts.append(f"{valid_k} = {serialize_lua_value(value[k])}")
        return "{ " + ", ".join(parts) + " }"
    raise OverridesError(f"Unsupported value type for Lua serialization: {type(value).__name__}")


def render_config_call(nested_dict: dict[str, Any]) -> str:
    """Render a nested configuration dict as `hl.config({ ... })`."""
    if not isinstance(nested_dict, dict):
        raise OverridesError("render_config_call requires a dict")
    return f"hl.config({serialize_lua_value(nested_dict)})"


def _scan_sections(text: str) -> dict[str, tuple[int, int, int, int]]:
    """Return mapping of section_name -> (block_start, body_start, body_end, block_end)."""
    sections: dict[str, tuple[int, int, int, int]] = {}
    open_name: str | None = None
    open_block_start = 0
    open_body_start = 0

    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        line_end = offset + len(line)
        if stripped.startswith(SECTION_BEGIN_PREFIX):
            name = stripped[len(SECTION_BEGIN_PREFIX) :]
            _validate_section_name(name)
            if open_name is not None:
                raise OverridesError(
                    f"Nested section {name!r} inside unclosed section {open_name!r}"
                )
            if name in sections:
                raise OverridesError(f"Duplicate overrides section: {name!r}")
            open_name = name
            open_block_start = offset
            open_body_start = line_end
        elif stripped.startswith(SECTION_END_PREFIX):
            name = stripped[len(SECTION_END_PREFIX) :]
            _validate_section_name(name)
            if open_name is None:
                raise OverridesError(f"Orphan section END marker for {name!r}")
            if name != open_name:
                raise OverridesError(
                    f"Mismatched section END marker {name!r} (expected {open_name!r})"
                )
            sections[name] = (open_block_start, open_body_start, offset, line_end)
            open_name = None
        offset = line_end

    if open_name is not None:
        raise OverridesError(f"Unclosed section BEGIN marker for {open_name!r}")
    return sections


def parse_sections(text: str) -> dict[str, str]:
    """Parse named managed sections from overrides file text."""
    spans = _scan_sections(text)
    result: dict[str, str] = {}
    for name, (_, body_start, body_end, _) in spans.items():
        result[name] = text[body_start:body_end].rstrip("\r\n")
    return result


def replace_section(text: str | None, name: str, body: str) -> str:
    """Create or replace a named managed section, preserving outside content verbatim."""
    _validate_section_name(name)
    base = create_overrides_text() if (text is None or text == "") else text
    spans = _scan_sections(base)
    body_norm = body.rstrip("\r\n")
    inner = (body_norm + "\n") if body_norm else ""
    block = f"{section_begin_marker(name)}\n{inner}{section_end_marker(name)}\n"

    if name in spans:
        block_start, _, _, block_end = spans[name]
        return base[:block_start] + block + base[block_end:]

    if base.endswith("\n"):
        return base + ("\n" if not base.endswith("\n\n") else "") + block
    return base + "\n\n" + block


def remove_section(text: str, name: str) -> str:
    """Remove a named managed section if present, preserving outside content verbatim."""
    _validate_section_name(name)
    spans = _scan_sections(text)
    if name not in spans:
        return text
    block_start, _, _, block_end = spans[name]
    before = text[:block_start]
    after = text[block_end:]
    if before.endswith("\n\n") and (after == "" or after.startswith("\n")):
        before = before[:-1]
    return before + after
