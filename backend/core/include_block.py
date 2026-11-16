"""Pure functions for managing the HyprDeck overrides include block in hyprland.lua."""

from __future__ import annotations

from backend.core.constants import (
    INCLUDE_BEGIN_MARKER,
    INCLUDE_END_MARKER,
    OVERRIDES_FILENAME,
)


class IncludeBlockError(ValueError):
    """Raised when include block markers are malformed."""


def render_include_block() -> str:
    """Render the marker-delimited Lua snippet that safely loads hks-overrides.lua."""
    return "\n".join(
        [
            INCLUDE_BEGIN_MARKER,
            "do",
            '    local _hks_home = os.getenv("HOME") or ""',
            '    if _hks_home ~= "" then',
            f'        local _hks_overrides = _hks_home .. "/.config/hypr/{OVERRIDES_FILENAME}"',
            '        local _hks_f = io.open(_hks_overrides, "r")',
            "        if _hks_f then",
            "            _hks_f:close()",
            "            pcall(dofile, _hks_overrides)",
            "        end",
            "    end",
            "end",
            INCLUDE_END_MARKER,
        ]
    )


def _locate_markers(text: str) -> tuple[int, int] | None:
    """Locate (begin_offset, end_line_end_offset) of the include block, or None if absent.

    Raises IncludeBlockError on missing pair, duplicates, or reversed order.
    """
    begin_matches: list[tuple[int, int]] = []
    end_matches: list[tuple[int, int]] = []

    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        line_end = offset + len(line)
        if stripped == INCLUDE_BEGIN_MARKER:
            begin_matches.append((offset, line_end))
        elif stripped == INCLUDE_END_MARKER:
            end_matches.append((offset, line_end))
        offset = line_end

    if not begin_matches and not end_matches:
        return None
    if len(begin_matches) > 1:
        raise IncludeBlockError("Duplicate HyprDeck include BEGIN marker found")
    if len(end_matches) > 1:
        raise IncludeBlockError("Duplicate HyprDeck include END marker found")
    if len(begin_matches) != len(end_matches):
        raise IncludeBlockError("Unpaired HyprDeck include marker (missing BEGIN or END)")

    begin_start, _ = begin_matches[0]
    end_start, end_finish = end_matches[0]
    if end_start < begin_start:
        raise IncludeBlockError("Malformed HyprDeck include markers (END appears before BEGIN)")

    return begin_start, end_finish


def has_include(text: str) -> bool:
    """Return True if a valid include block is present; raise on malformed markers."""
    return _locate_markers(text) is not None


def insert_include(text: str) -> str:
    """Idempotently append the include block at EOF, preserving all existing bytes."""
    if has_include(text):
        return text
    block = render_include_block()
    if text == "":
        return block + "\n"
    if text.endswith("\n"):
        return text + "\n" + block + "\n"
    return text + "\n" + block


def remove_include(text: str) -> str:
    """Remove the include block if present, restoring exact prior bytes for insert_include(x)."""
    span = _locate_markers(text)
    if span is None:
        return text
    begin_start, end_finish = span
    before = text[:begin_start]
    after = text[end_finish:]

    if after == "":
        # Block was at EOF (standard insert_include placement)
        if before == "":
            return ""
        # Case: original ended with '\n' -> insert added '\n' + block + '\n' (so before ends with '\n\n' or '\n' if original was '\n')
        block_had_trailing_nl = text[end_finish - 1 : end_finish] == "\n"
        if block_had_trailing_nl and before.endswith("\n\n"):
            return before[:-1]
        if block_had_trailing_nl and before == "\n":
            return "\n"
        if not block_had_trailing_nl and before.endswith("\n"):
            return before[:-1]
        return before

    # Content exists after the block: preserve both sides cleanly
    if before.endswith("\n\n") and after.startswith("\n"):
        return before[:-1] + after[1:]
    if before.endswith("\n") and after.startswith("\n"):
        return before + after[1:]
    return before + after
