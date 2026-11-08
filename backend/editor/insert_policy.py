"""Insertion policy and anchor management for Hyprland Keybind Studio (Phase 3b)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from backend.editor.codegen import generate_hyprlang_bind, generate_lua_bind
from backend.editor.edit_plan import EditOp, NotEditableError

LUA_ANCHOR = "-- HKS: custom binds"
HYPRLANG_ANCHOR = "# HKS: custom binds"


@dataclass(slots=True)
class InsertPlan:
    file: str
    line_number: int  # 1-based line after which new text is inserted
    expected_text: str  # Content of line_number before edit
    new_text: str  # Content to insert
    anchor_created: bool
    generated_line: str


def compute_lua_line_depths(lines: list[str]) -> list[int]:
    """Compute the block nesting depth at the start of each line in a Lua file."""
    depths: list[int] = []
    current_depth = 0

    OPEN_KW = re.compile(r"\b(function|for|while|if|repeat)\b")
    CLOSE_KW = re.compile(r"\b(end|until)\b")

    for raw_line in lines:
        line = raw_line.split("--")[0].strip()  # Strip comments
        depths.append(current_depth)

        if not line:
            continue

        # Count opening keywords
        opens = len(OPEN_KW.findall(line))
        # Account for standalone 'do'
        if re.search(r"\bdo\b", line) and not re.search(r"\b(for|while)\b", line):
            opens += 1

        # Count closing keywords
        closes = len(CLOSE_KW.findall(line))

        # Adjust depth
        current_depth = max(0, current_depth + opens - closes)

    return depths


def plan_insert_bind(
    file_path: str,
    language: str,
    mods: list[str] | str | None,
    key: str,
    dispatcher: str,
    args: str | None = None,
    *,
    flags: dict[str, bool] | None = None,
    submap: str | None = None,
    prefer_mainmod: bool = False,
) -> tuple[EditOp, InsertPlan]:
    """Plan insertion of a new keybinding into `file_path` according to HKS anchor policy."""
    abs_path = os.path.abspath(os.path.expanduser(file_path))
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"Configuration file not found: {abs_path}")

    with open(abs_path, "r", encoding="utf-8", newline="") as f:
        content = f.read()

    eol = "\r\n" if "\r\n" in content else "\n"
    lines = content.splitlines()
    is_lua = language == "lua"
    anchor = LUA_ANCHOR if is_lua else HYPRLANG_ANCHOR

    clean_submap = (submap or "").strip()

    # 1. Submap insertion handling
    if clean_submap:
        if is_lua:
            submap_idx = -1
            submap_pattern = re.compile(
                rf"""\bdefine_submap\s*\(\s*["']{re.escape(clean_submap)}["']|submap\s*=\s*["']{re.escape(clean_submap)}["']"""
            )
            for idx, line in enumerate(lines):
                if submap_pattern.search(line):
                    submap_idx = idx
                    break

            if submap_idx == -1:
                raise NotEditableError(
                    f"Cannot insert into submap '{clean_submap}': submap '{clean_submap}' does not exist in {abs_path}"
                )

            # Find insertion position inside submap block before its closing end or table }
            depths = compute_lua_line_depths(lines)
            submap_depth = depths[submap_idx]
            target_idx = -1
            for idx in range(submap_idx + 1, len(lines)):
                if depths[idx] <= submap_depth and re.search(r"\b(end|\})\b", lines[idx]):
                    target_idx = max(submap_idx, idx - 1)
                    break
            if target_idx == -1:
                target_idx = len(lines) - 1

            target_line_number = target_idx + 1
            expected_text = lines[target_idx] if lines else ""
            neighbour_indent = re.match(r"^\s*", expected_text).group(0) if expected_text else "    "
            new_bind_line = generate_lua_bind(mods, key, dispatcher, args, flags=flags, indent=neighbour_indent, prefer_mainmod=prefer_mainmod)
            new_text = new_bind_line
            anchor_created = False

        else:
            # Hyprlang submap: look for `submap = NAME`
            submap_start_idx = -1
            for idx, line in enumerate(lines):
                m = re.match(r"^submap\s*=\s*(.*)$", line.strip())
                if m and m.group(1).strip() == clean_submap:
                    submap_start_idx = idx
                    break

            if submap_start_idx == -1:
                raise NotEditableError(
                    f"Cannot insert into submap '{clean_submap}': submap '{clean_submap}' does not exist in {abs_path}"
                )

            # Find matching reset or next submap or EOF
            submap_end_idx = len(lines) - 1
            for idx in range(submap_start_idx + 1, len(lines)):
                m = re.match(r"^submap\s*=\s*(.*)$", lines[idx].strip())
                if m:
                    submap_end_idx = max(submap_start_idx, idx - 1)
                    break

            # Find last bind in this submap section
            last_bind_idx = -1
            for idx in range(submap_start_idx + 1, submap_end_idx + 1):
                if re.match(r"^bind\w*\s*=", lines[idx].strip()):
                    last_bind_idx = idx

            target_idx = last_bind_idx if last_bind_idx != -1 else submap_start_idx
            target_line_number = target_idx + 1
            expected_text = lines[target_idx] if lines else ""
            neighbour_indent = re.match(r"^\s*", expected_text).group(0) if expected_text else ""
            new_bind_line = generate_hyprlang_bind(mods, key, dispatcher, args, flags=flags, indent=neighbour_indent)
            new_text = new_bind_line
            anchor_created = False

    else:
        # 2. Check if anchor already exists
        anchor_idx = -1
        for idx, line in enumerate(lines):
            if line.strip() == anchor:
                anchor_idx = idx
                break

        if anchor_idx != -1:
            # Anchor exists: find the last HKS-managed line in this block.
            # Continue downwards while lines are HKS-managed binds or comments.
            last_block_idx = anchor_idx
            for scan_idx in range(anchor_idx + 1, len(lines)):
                l_strip = lines[scan_idx].strip()
                if not l_strip:
                    break
                if is_lua:
                    is_hks_line = l_strip.startswith("hl.bind") or l_strip.startswith("-- HKS")
                else:
                    is_hks_line = bool(re.match(r"^bind\w*\s*=", l_strip)) or l_strip.startswith("# HKS")
                if not is_hks_line:
                    break
                last_block_idx = scan_idx

            target_line_number = last_block_idx + 1  # 1-based
            expected_text = lines[last_block_idx] if lines else ""
            neighbour_indent = re.match(r"^\s*", expected_text).group(0) if expected_text else ""
            if is_lua:
                new_bind_line = generate_lua_bind(mods, key, dispatcher, args, flags=flags, indent=neighbour_indent, prefer_mainmod=prefer_mainmod)
            else:
                new_bind_line = generate_hyprlang_bind(mods, key, dispatcher, args, flags=flags, indent=neighbour_indent)
            new_text = new_bind_line
            anchor_created = False

        else:
            # Anchor is absent: locate the last top-level bind statement at depth 0.
            if is_lua:
                depths = compute_lua_line_depths(lines)
                last_top_level_idx = -1
                BIND_RE = re.compile(r"^\s*hl\.bind\w*\s*\(")

                for idx, line in enumerate(lines):
                    if depths[idx] == 0 and BIND_RE.search(line):
                        last_top_level_idx = idx

                if last_top_level_idx == -1:
                    # Fallback: check if EOF is at depth 0
                    if depths and depths[-1] == 0:
                        last_top_level_idx = len(lines) - 1
                    else:
                        raise NotEditableError(
                            f"Cannot safely insert bind: no top-level bind statement found at block depth 0 in {abs_path}"
                        )
            else:
                # Hyprlang: look for last top-level bind directive
                last_top_level_idx = -1
                in_submap = False
                for idx, line in enumerate(lines):
                    l_strip = line.strip()
                    if l_strip.startswith("submap"):
                        in_submap = not l_strip.endswith("reset")
                    if not in_submap and re.match(r"^bind\w*\s*=", l_strip):
                        last_top_level_idx = idx

                if last_top_level_idx == -1:
                    last_top_level_idx = max(0, len(lines) - 1)

            target_line_number = last_top_level_idx + 1 if lines else 1
            expected_text = lines[last_top_level_idx] if lines else ""
            neighbour_indent = re.match(r"^\s*", expected_text).group(0) if expected_text else ""
            if is_lua:
                new_bind_line = generate_lua_bind(mods, key, dispatcher, args, flags=flags, indent=neighbour_indent, prefer_mainmod=prefer_mainmod)
            else:
                new_bind_line = generate_hyprlang_bind(mods, key, dispatcher, args, flags=flags, indent=neighbour_indent)
            # Insert blank line, anchor header, and the new bind line using neighbour_indent
            if lines:
                new_text = f"{eol}{neighbour_indent}{anchor}{eol}{new_bind_line}"
            else:
                new_text = f"{anchor}{eol}{new_bind_line}"
            anchor_created = True

    plan = InsertPlan(
        file=abs_path,
        line_number=target_line_number,
        expected_text=expected_text,
        new_text=new_text,
        anchor_created=anchor_created,
        generated_line=new_bind_line,
    )

    op = EditOp(
        kind="insert_after",
        file=abs_path,
        line_number=target_line_number,
        expected_text=expected_text,
        new_text=new_text,
        language=language,
    )

    return op, plan
