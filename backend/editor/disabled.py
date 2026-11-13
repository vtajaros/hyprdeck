"""Detection and parsing of HKS-disabled keybinding lines."""

from __future__ import annotations

import os
import re
from typing import Any

from backend.editor.edit_plan import (
    HYPRLANG_DISABLED_PREFIX,
    LUA_DISABLED_PREFIX,
    EditOp,
    apply_ops_to_text,
)
from backend.editor.validator import stage_candidate_config
from backend.models.types import DisabledBindRecord
from backend.parser import compute_bind_id, parse_hyprlang_config, parse_lua_config

LUA_BIND_HINT_RE = re.compile(
    r"""hl\.(?:bind\w*)\s*\(\s*(?:([a-zA-Z0-9_.]+(?:\s*\.\.\s*["'][^"']+["'])*|["'][^"']+["'])\s*,)?\s*([a-zA-Z0-9_.]+(?:\s*\.\.\s*["'][^"']+["'])*|["'][^"']+["'])"""
)
HYPR_BIND_HINT_RE = re.compile(
    r"""bind\w*\s*=\s*([^,]+),\s*([^,]+)"""
)


def collect_disabled_uncomment_ops(
    lines: list[str],
    file_path: str,
    language: str,
) -> list[EditOp]:
    """Group HKS-disabled lines (including multi-line Lua statements) into uncomment EditOps."""
    is_lua = language == "lua"
    prefix = LUA_DISABLED_PREFIX if is_lua else HYPRLANG_DISABLED_PREFIX
    ops: list[EditOp] = []
    i = 0
    while i < len(lines):
        line_str = lines[i]
        if not line_str.lstrip(" \t").startswith(prefix):
            i += 1
            continue
        start_line_no = i + 1
        block_lines = [line_str]
        if is_lua:
            from backend.parser.lua_normalizer import extract_lua_statement_span
            unprefixed: list[str] = []
            j = i
            while j < len(lines) and lines[j].lstrip(" \t").startswith(prefix):
                raw_j = lines[j]
                lead_len = len(raw_j) - len(raw_j.lstrip(" \t"))
                unprefixed.append(raw_j[:lead_len] + raw_j[lead_len + len(prefix):])
                j += 1
            span_text = extract_lua_statement_span(unprefixed, 1)
            span_count = max(1, len(span_text.splitlines()))
            block_lines = lines[i:i + span_count]
            i += span_count
        else:
            i += 1

        ops.append(
            EditOp(
                kind="uncomment",
                file=file_path,
                line_number=start_line_no,
                expected_text="\n".join(block_lines),
                language=language,
            )
        )
    return ops


def detect_disabled_binds(
    entrypoint: str,
    config_dir: str,
    language: str,
    env: dict[str, str] | None = None,
) -> list[DisabledBindRecord]:
    """Scan entrypoint for HKS-disabled binds, parsing them via sandbox recorder or regex."""
    abs_entry = os.path.abspath(os.path.expanduser(entrypoint))
    abs_config_dir = os.path.abspath(os.path.expanduser(config_dir))

    if not os.path.isfile(abs_entry):
        return []

    with open(abs_entry, "r", encoding="utf-8") as f:
        text = f.read()

    lines = text.splitlines()
    is_lua = language == "lua"

    disabled_ops = collect_disabled_uncomment_ops(lines, abs_entry, language)
    disabled_lines = [(op.line_number, op.expected_text) for op in disabled_ops]

    if not disabled_lines:
        return []

    # Best-effort staged parsing
    parsed_by_line: dict[int, Any] = {}
    try:
        trial_text = apply_ops_to_text(text, disabled_ops)
        trial_bytes = trial_text.encode("utf-8")
        with stage_candidate_config(
            config_dir=abs_config_dir,
            entrypoint=abs_entry,
            target_file=abs_entry,
            new_bytes=trial_bytes,
        ) as (staged_dir, staged_entry, _):
            if is_lua:
                staged_binds, _, _, _, _ = parse_lua_config(
                    entrypoint=staged_entry,
                    config_dir=staged_dir,
                    env=env,
                )
            else:
                staged_binds, _, _, _, _, _ = parse_hyprlang_config(
                    entrypoint=staged_entry,
                )
            for b in staged_binds:
                if b.source_line not in parsed_by_line:
                    parsed_by_line[b.source_line] = b
    except Exception:
        # Sandbox or parsing failed; proceed with regex fallback
        pass

    results: list[DisabledBindRecord] = []
    for line_no, raw_line in disabled_lines:
        b = parsed_by_line.get(line_no)
        if b is not None:
            # Recompute bind ID using real entrypoint path so it matches the pre-disabled ID
            real_id = compute_bind_id(
                abs_file=abs_entry,
                line=line_no,
                occurrence=b.occurrence,
                keys=b.keys_raw,
                dispatcher_path=b.dispatcher.path,
            )
            key_hint = b.keys_raw or b.key
            desc_hint = b.description_effective.text if b.description_effective else None
            results.append(
                DisabledBindRecord(
                    id=real_id,
                    file=abs_entry,
                    line=line_no,
                    original_text=raw_line,
                    key_hint=key_hint,
                    description_hint=desc_hint,
                )
            )
        else:
            # Fallback regex extraction
            uncommented = raw_line.lstrip(" \t")
            if uncommented.startswith(prefix):
                uncommented = uncommented[len(prefix):]

            key_hint: str | None = None
            if is_lua:
                m = LUA_BIND_HINT_RE.search(uncommented)
                if m:
                    key_part = m.group(2) or m.group(1)
                    key_hint = key_part.replace('"', "").replace("'", "").strip()
            else:
                m = HYPR_BIND_HINT_RE.search(uncommented)
                if m:
                    m1 = m.group(1).strip()
                    m2 = m.group(2).strip()
                    key_hint = f"{m1} + {m2}" if m1 else m2

            fallback_id = compute_bind_id(
                abs_file=abs_entry,
                line=line_no,
                occurrence=0,
                keys=key_hint or "",
                dispatcher_path="",
            )
            results.append(
                DisabledBindRecord(
                    id=fallback_id,
                    file=abs_entry,
                    line=line_no,
                    original_text=raw_line,
                    key_hint=key_hint,
                    description_hint=None,
                )
            )

    return results
