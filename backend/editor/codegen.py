"""Code generation and line rewriting engine for Hyprland Keybind Studio (Phase 3b)."""

from __future__ import annotations

import re
from typing import Any

from backend.editor.edit_plan import NotEditableError
from backend.parser.modifiers import (
    MODIFIER_ALIASES,
    MODIFIER_BITS,
    resolve_modifier_tokens,
)

CANONICAL_MOD_ORDER = ["SUPER", "CTRL", "ALT", "SHIFT", "MOD2", "MOD3", "MOD5"]


def escape_lua_string(s: str) -> str:
    """Escape backslashes and double quotes for inclusion in a Lua double-quoted string literal."""
    if "\n" in s or "\r" in s:
        raise ValueError("Newlines are not allowed in string arguments")
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


REQUIRE_ARGS_DISPATCHERS: frozenset[str] = frozenset({
    "exec_cmd",
    "hl.dsp.exec_cmd",
    "exec",
    "workspace",
    "movetoworkspace",
    "movetoworkspacesilent",
    "submap",
    "hl.dsp.submap",
})


def validate_required_args(dispatcher: str | None, args: str | None) -> None:
    """Reject empty or whitespace-only args for dispatchers that require an argument."""
    if not dispatcher:
        return
    clean_dsp = dispatcher.strip()
    if "(" in clean_dsp:
        # Inline Lua call like hl.dsp.exec_cmd("kitty") already carries its argument
        return
    if clean_dsp.lower() in REQUIRE_ARGS_DISPATCHERS:
        if args is None or not str(args).strip():
            raise ValueError(f"Dispatcher '{clean_dsp}' requires non-empty arguments")


def validate_code_tokens(dispatcher: str, args: str | None = None) -> None:
    """Validate dispatcher and args to ensure no newlines and balanced quotes/brackets."""
    if "\n" in dispatcher or "\r" in dispatcher:
        raise ValueError("Newlines are not allowed in dispatcher")
    if args and ("\n" in args or "\r" in args):
        raise ValueError("Newlines are not allowed in args")

    combined = dispatcher + (" " + args if args else "")

    # Check balanced quotes (ignoring escaped ones)
    single_quotes = 0
    double_quotes = 0
    in_escape = False
    for ch in combined:
        if in_escape:
            in_escape = False
            continue
        if ch == "\\":
            in_escape = True
            continue
        if ch == "'":
            single_quotes += 1
        elif ch == '"':
            double_quotes += 1

    if single_quotes % 2 != 0:
        raise ValueError(f"Unbalanced single quotes in code: {combined!r}")
    if double_quotes % 2 != 0:
        raise ValueError(f"Unbalanced double quotes in code: {combined!r}")

    # Check balanced brackets (), [], {}
    stack: list[str] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    in_str: str | None = None
    in_esc = False

    for ch in combined:
        if in_esc:
            in_esc = False
            continue
        if ch == "\\":
            in_esc = True
            continue
        if in_str:
            if ch == in_str:
                in_str = None
            continue
        if ch in ("'", '"'):
            in_str = ch
            continue
        if ch in ("(", "[", "{"):
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack[-1] != pairs[ch]:
                raise ValueError(f"Unbalanced bracket {ch!r} in code: {combined!r}")
            stack.pop()

    if stack:
        raise ValueError(f"Unclosed bracket(s) {stack!r} in code: {combined!r}")


def _normalize_mods(mods: list[str] | str | None) -> list[str]:
    """Normalize modifier input into an ordered list of canonical modifier names."""
    if not mods:
        return []
    if isinstance(mods, str):
        # Support comma, plus, or space separated
        raw_tokens = [tok.strip() for tok in re.split(r"[,+\s]+", mods) if tok.strip()]
    else:
        raw_tokens = []
        for m in mods:
            raw_tokens.extend([tok.strip() for tok in re.split(r"[,+\s]+", m) if tok.strip()])

    parsed = resolve_modifier_tokens(raw_tokens)
    if parsed.unknown_tokens:
        raise ValueError(f"Unknown modifier token(s): {', '.join(parsed.unknown_tokens)}")

    ordered = [m for m in CANONICAL_MOD_ORDER if m in parsed.modifiers]
    # Add any remaining modifiers not in standard order
    for m in parsed.modifiers:
        if m not in ordered:
            ordered.append(m)
    return ordered


def _extract_trailing_comment(line: str, lang: str) -> tuple[str, str]:
    """Extract trailing comment from a line, respecting string literals."""
    comment_marker = "--" if lang == "lua" else "#"
    in_str: str | None = None
    in_esc = False

    for idx, ch in enumerate(line):
        if in_esc:
            in_esc = False
            continue
        if ch == "\\":
            in_esc = True
            continue
        if in_str:
            if ch == in_str:
                in_str = None
            continue
        if ch in ("'", '"'):
            in_str = ch
            continue
        if line[idx:].startswith(comment_marker):
            code_part = line[:idx].rstrip()
            comment_part = line[idx:]
            return code_part, (" " if not comment_part.startswith(" ") else "") + comment_part

    return line, ""


def _rewrite_lua_shortcut(original_line: str, new_combo_expr: str) -> str | None:
    """Rewrite only the shortcut combo in an hl.bind(...) call, preserving everything else."""
    m = re.match(r"^(\s*)(hl\.bind\w*\s*\()", original_line)
    if not m:
        return None
    prefix_text = m.group(0)
    start_pos = len(prefix_text)
    m_lead = re.match(r"^(\s*)", original_line[start_pos:])
    lead_ws = m_lead.group(1) if m_lead else ""
    scan_start = start_pos + len(lead_ws)
    in_str: str | None = None
    in_esc = False
    depth = 0
    for i in range(scan_start, len(original_line)):
        ch = original_line[i]
        if in_esc:
            in_esc = False
            continue
        if ch == "\\":
            in_esc = True
            continue
        if in_str:
            if ch == in_str:
                in_str = None
            continue
        if ch in ('"', "'"):
            in_str = ch
            continue
        if ch in ("(", "[", "{"):
            depth += 1
            continue
        if ch in (")", "]", "}"):
            if depth == 0:
                break
            depth -= 1
            continue
        if ch == "," and depth == 0:
            combo = original_line[scan_start:i]
            rest = original_line[i:]  # starts with ','
            # Check spacing after comma for column alignment preservation
            m_sep = re.match(r"^,([ \t]+)", rest)
            if m_sep and "\n" not in original_line:
                orig_col = scan_start + len(combo) + len(m_sep.group(0))
                new_prefix = f"{prefix_text}{lead_ws}{new_combo_expr},"
                if len(new_prefix) < orig_col and len(m_sep.group(1)) >= 2:
                    padding = " " * (orig_col - len(new_prefix))
                    return new_prefix + padding + rest[len(m_sep.group(0)):]
                elif len(m_sep.group(1)) >= 2:
                    return new_prefix + " " + rest[len(m_sep.group(0)):]
            return f"{prefix_text}{lead_ws}{new_combo_expr}{rest}"
    return None


def generate_lua_bind(
    mods: list[str] | str | None,
    key: str,
    dispatcher: str | None = None,
    args: str | None = None,
    *,
    original_line: str | None = None,
    flags: dict[str, Any] | None = None,
    indent: str | None = None,
    preserve_dispatcher: bool = False,
    prefer_mainmod: bool = False,
) -> str:
    """Generate a clean Lua `hl.bind(...)` statement, preserving layout and mainMod if used."""
    if not key or not key.strip():
        raise ValueError("Key cannot be empty")
    clean_key = key.strip()

    canonical_mods = _normalize_mods(mods)

    if indent is not None:
        final_indent = indent
    elif original_line is not None:
        final_indent = re.match(r"^\s*", original_line).group(0)
    else:
        final_indent = ""

    # Determine combo expression (preserving mainMod if original used it or prefer_mainmod, and SUPER is present)
    uses_main_mod = (original_line is not None and bool(re.search(r"\bmainMod\b", original_line))) or prefer_mainmod
    has_super = "SUPER" in canonical_mods

    if uses_main_mod and has_super:
        extras = [m for m in canonical_mods if m != "SUPER"]
        if extras:
            combo_expr = f'mainMod .. " + {" + ".join(extras)} + {clean_key}"'
        else:
            combo_expr = f'mainMod .. " + {clean_key}"'
    else:
        if canonical_mods:
            combo_str = " + ".join(canonical_mods) + " + " + clean_key
        else:
            combo_str = clean_key
        combo_expr = f'"{combo_str}"'

    if preserve_dispatcher and original_line is not None:
        rewritten = _rewrite_lua_shortcut(original_line, combo_expr)
        if rewritten is not None:
            return rewritten

    if dispatcher is None:
        raise ValueError("dispatcher cannot be None when not preserving original dispatcher")

    validate_required_args(dispatcher, args)

    d_lower = dispatcher.strip().lower()
    is_exec = d_lower in ("exec_cmd", "hl.dsp.exec_cmd", "exec")
    if is_exec:
        if "\n" in dispatcher or "\r" in dispatcher:
            raise ValueError("Newlines are not allowed in dispatcher")
        if args and ("\n" in args or "\r" in args):
            raise ValueError("Newlines are not allowed in args")
    else:
        validate_code_tokens(dispatcher, args)

    trailing_comment = ""
    opts_str = ""

    if original_line is not None:
        raw_code = original_line.strip()
        if not re.search(r"\bhl\.bind\w*\s*\(", raw_code):
            raise NotEditableError(
                f"Cannot rewrite statement: line does not contain a standard hl.bind call: {original_line!r}"
            )

        code_no_comment, trailing_comment = _extract_trailing_comment(original_line, "lua")

        # Extract options table if present, e.g. `, { locked = true }`
        opts_match = re.search(r",\s*(\{[^}]+\})\s*\)\s*$", code_no_comment)
        if opts_match:
            opts_str = f", {opts_match.group(1).strip()}"

    if flags and not opts_str:
        true_flags = [f"{k} = true" for k, v in sorted(flags.items()) if v]
        if true_flags:
            opts_str = f", {{ {', '.join(true_flags)} }}"

    # Determine dispatcher expression
    clean_dsp = dispatcher.strip()
    clean_args = args.strip() if args else ""

    if clean_args:
        dsp_base = clean_dsp.split("(")[0].strip()
        if not dsp_base.startswith("hl."):
            dsp_base = f"hl.dsp.{dsp_base}"

        if clean_dsp == "custom" or dsp_base == "hl.dsp.custom":
            dsp_call = clean_args
        elif "exec_cmd" in dsp_base or dsp_base.endswith("exec_cmd"):
            arg_formatted = escape_lua_string(clean_args)
            dsp_call = f"{dsp_base}({arg_formatted})"
        elif clean_args.startswith("{") and clean_args.endswith("}"):
            dsp_call = f"{dsp_base}({clean_args})"
        elif clean_args.isdigit():
            dsp_call = f"{dsp_base}({clean_args})"
        elif re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", clean_args) and original_line and clean_args in original_line:
            dsp_call = f"{dsp_base}({clean_args})"
        else:
            arg_formatted = escape_lua_string(clean_args)
            dsp_call = f"{dsp_base}({arg_formatted})"
    else:
        if "(" in clean_dsp and clean_dsp.endswith(")"):
            dsp_call = clean_dsp if clean_dsp.startswith("hl.") else f"hl.dsp.{clean_dsp}"
        else:
            dsp_base = clean_dsp if clean_dsp.startswith("hl.") else f"hl.dsp.{clean_dsp}"
            dsp_call = f"{dsp_base}()"

    if original_line is not None and "\n" in original_line:
        lines = original_line.splitlines()
        line2_indent = "    " if len(lines) < 2 else re.match(r"^\s*", lines[1]).group(0)
        return f"{final_indent}hl.bind({combo_expr},\n{line2_indent}{dsp_call}{opts_str}){trailing_comment}"

    # Preserve column padding between key and dispatcher if original padded with 2+ spaces
    sep = " "
    if original_line is not None and "\n" not in original_line:
        m_pad = re.search(r",(\s{2,})(hl\.dsp|\w+)", original_line)
        if m_pad:
            target_col = m_pad.start(2)
            prefix = f"{final_indent}hl.bind({combo_expr},"
            if len(prefix) < target_col:
                sep = " " * (target_col - len(prefix))

    return f"{final_indent}hl.bind({combo_expr},{sep}{dsp_call}{opts_str}){trailing_comment}"


def generate_hyprlang_bind(
    mods: list[str] | str | None,
    key: str,
    dispatcher: str | None = None,
    args: str | None = None,
    *,
    original_line: str | None = None,
    flags: dict[str, Any] | None = None,
    indent: str | None = None,
    preserve_dispatcher: bool = False,
) -> str:
    """Generate a clean Hyprlang `bind = ...` statement, preserving $mainMod and flags if used."""
    if not key or not key.strip():
        raise ValueError("Key cannot be empty")
    clean_key = key.strip()

    canonical_mods = _normalize_mods(mods)

    if indent is not None:
        final_indent = indent
    elif original_line is not None:
        final_indent = re.match(r"^\s*", original_line).group(0)
    else:
        final_indent = ""
    trailing_comment = ""
    bind_kw = "bind"

    if original_line is not None:
        raw_code = original_line.strip()
        m_kw = re.match(r"^(bind\w*)\s*=", raw_code)
        if m_kw:
            bind_kw = m_kw.group(1)
        else:
            raise NotEditableError(
                f"Cannot rewrite statement: line does not contain a standard Hyprlang bind directive: {original_line!r}"
            )
        code_no_comment, trailing_comment = _extract_trailing_comment(original_line, "hyprlang")

        if preserve_dispatcher:
            # Extract kw and rest
            m_stmt = re.match(r"^(bind\w*)\s*=\s*(.*)$", code_no_comment)
            if m_stmt:
                parts = [p.strip() for p in m_stmt.group(2).split(",")]
                if len(parts) >= 3:
                    rest_dsp_args = ", ".join(parts[2:])
                    uses_main_mod = "$mainMod" in original_line
                    has_super = "SUPER" in canonical_mods
                    mod_tokens = list(canonical_mods)
                    if uses_main_mod and has_super:
                        mod_tokens = ["$mainMod" if m == "SUPER" else m for m in mod_tokens]
                    mods_str = " ".join(mod_tokens)
                    return f"{final_indent}{bind_kw} = {mods_str}, {clean_key}, {rest_dsp_args}{trailing_comment}"
    elif flags:
        from backend.parser.modifiers import derive_bind_type_from_flags
        bind_kw = derive_bind_type_from_flags(flags)
    else:
        bind_kw = "bind"

    if dispatcher is None:
        raise ValueError("dispatcher cannot be None when not preserving original dispatcher")

    validate_required_args(dispatcher, args)

    d_lower = dispatcher.strip().lower()
    is_exec = d_lower in ("exec_cmd", "hl.dsp.exec_cmd", "exec")
    if is_exec:
        if "\n" in dispatcher or "\r" in dispatcher:
            raise ValueError("Newlines are not allowed in dispatcher")
        if args and ("\n" in args or "\r" in args):
            raise ValueError("Newlines are not allowed in args")
    else:
        validate_code_tokens(dispatcher, args)

    uses_main_mod = original_line is not None and "$mainMod" in original_line
    has_super = "SUPER" in canonical_mods

    mod_tokens = list(canonical_mods)
    if uses_main_mod and has_super:
        mod_tokens = ["$mainMod" if m == "SUPER" else m for m in mod_tokens]

    mods_str = " ".join(mod_tokens)
    from backend.editor.dispatchers import map_lua_dispatcher_to_hyprlang
    clean_dsp, mapped_args = map_lua_dispatcher_to_hyprlang(dispatcher, args)
    clean_args = mapped_args.strip() if mapped_args else ""
    if clean_args and ("\n" in clean_args or "\r" in clean_args):
        raise ValueError("Newlines are not allowed in args")

    if clean_args:
        stmt = f"{bind_kw} = {mods_str}, {clean_key}, {clean_dsp}, {clean_args}"
    else:
        stmt = f"{bind_kw} = {mods_str}, {clean_key}, {clean_dsp}"

    return f"{final_indent}{stmt}{trailing_comment}"
