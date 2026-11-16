"""Hyprlang (.conf) line state machine parser for HyprDeck."""

from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass, field
from typing import Any

from backend.describe.derive import populate_bind_descriptions
from backend.discovery.config_discovery import build_file_record
from backend.models.types import (
    BindRecord,
    Diagnostic,
    DispatcherInfo,
    FileRecord,
    StatsRecord,
    TraceFrame,
    UnbindRecord,
    default_flags,
)
from backend.parser.lua_normalizer import compute_bind_id, compute_stats
from backend.parser.modifiers import (
    LETTER_TO_FLAG,
    classify_key_kind,
    resolve_modifier_tokens,
)

MAX_SOURCE_DEPTH = 16

VAR_DEF_RE = re.compile(r"^\$([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
BIND_KW_RE = re.compile(r"^(bind[a-zA-Z]*|unbind)\s*=\s*(.*)$")
SUBMAP_KW_RE = re.compile(r"^submap\s*=\s*(.*)$")
SOURCE_KW_RE = re.compile(r"^source\s*=\s*(.*)$")
GENERIC_KW_RE = re.compile(r"^([A-Za-z0-9_.-]+)\s*=\s*(.*)$")
SECTION_OPEN_RE = re.compile(r"^([A-Za-z0-9_.:-]+)\s*\{\s*$")
SUSPICIOUS_PREFIX_RE = re.compile(r"^(bind\w*|unbind|submap|source)\b", re.IGNORECASE)

VALID_BIND_LETTERS = frozenset({"l", "r", "e", "n", "m", "t", "i", "o", "s", "d"})


def strip_hyprlang_comment(line: str) -> str:
    """Strip '#' comments while converting '##' into a literal '#'."""
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == "#":
            if i + 1 < n and line[i + 1] == "#":
                out.append("#")
                i += 2
                continue
            break
        out.append(ch)
        i += 1
    return "".join(out)


def expand_variables(
    text: str,
    variables: dict[str, str],
) -> tuple[str, list[str]]:
    """Expand $var references longest-name-first, preserving '$(' untouched.

    Returns (expanded_text, unresolved_var_names).
    """
    if "$" not in text:
        return text, []

    sorted_vars = sorted(variables.keys(), key=len, reverse=True)
    unresolved: list[str] = []
    out: list[str] = []
    i = 0
    n = len(text)

    while i < n:
        if text[i] != "$":
            out.append(text[i])
            i += 1
            continue

        # Must leave "$(" untouched
        if i + 1 < n and text[i + 1] == "(":
            out.append("$(")
            i += 2
            continue

        matched_name: str | None = None
        for vname in sorted_vars:
            if text.startswith(vname, i + 1):
                matched_name = vname
                break

        if matched_name is not None:
            out.append(variables[matched_name])
            i += 1 + len(matched_name)
            continue

        # Check if it looks like an identifier $unknown
        m_ident = re.match(r"^[A-Za-z_][A-Za-z0-9_]*", text[i + 1 :])
        if m_ident:
            uname = m_ident.group(0)
            unresolved.append(uname)
            out.append("$" + uname)
            i += 1 + len(uname)
        else:
            out.append("$")
            i += 1

    return "".join(out), unresolved


def _expand_path_home(path_str: str, home_dir: str) -> str:
    p = path_str.strip()
    if p == "~":
        return home_dir
    if p.startswith("~/"):
        return os.path.join(home_dir, p[2:])
    p = p.replace("${HOME}", home_dir).replace("$HOME", home_dir)
    return os.path.expanduser(p)


@dataclass(slots=True)
class _ParserState:
    home_dir: str
    variables: dict[str, str] = field(default_factory=dict)
    current_submap: str = ""
    binds: list[BindRecord] = field(default_factory=list)
    unbinds: list[UnbindRecord] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    ignored_keywords: dict[str, int] = field(default_factory=dict)
    files_ordered: list[tuple[str, str]] = field(default_factory=list)  # (abs_path, role)
    files_seen: set[str] = field(default_factory=set)
    active_real_stack: list[str] = field(default_factory=list)
    site_occurrences: dict[tuple[str, int], int] = field(default_factory=dict)


def _split_n_commas(text: str, max_splits: int) -> list[str]:
    parts = text.split(",", max_splits)
    return [p.strip() for p in parts]


def _parse_mod_string(mod_str: str) -> list[str]:
    stripped = mod_str.strip()
    if not stripped:
        return []
    return [t for t in re.split(r"[\s+]+", stripped) if t]


def _parse_file_recursive(
    file_path: str,
    role: str,
    depth: int,
    state: _ParserState,
) -> None:
    abs_path = os.path.abspath(file_path)
    real_path = os.path.realpath(abs_path)

    if depth > MAX_SOURCE_DEPTH:
        state.diagnostics.append(
            Diagnostic(
                level="error",
                code="source_depth_exceeded",
                message=f"Maximum source inclusion depth ({MAX_SOURCE_DEPTH}) exceeded at {abs_path}",
                file=abs_path,
                line=None,
            )
        )
        return

    if real_path in state.active_real_stack:
        state.diagnostics.append(
            Diagnostic(
                level="error",
                code="source_cycle",
                message=f"Circular source inclusion detected for {abs_path}",
                file=abs_path,
                line=None,
            )
        )
        return

    try:
        with open(abs_path, "rb") as f:
            raw_bytes = f.read()
    except OSError as exc:
        state.diagnostics.append(
            Diagnostic(
                level="error",
                code="source_missing",
                message=f"Cannot read configuration file {abs_path}: {exc}",
                file=abs_path,
                line=None,
            )
        )
        return

    if abs_path not in state.files_seen:
        state.files_seen.add(abs_path)
        state.files_ordered.append((abs_path, role))

    state.active_real_stack.append(real_path)

    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        raw_bytes = raw_bytes[3:]
    text = raw_bytes.decode("utf-8", errors="replace")
    physical_lines = [ln.rstrip("\r\n") for ln in text.splitlines(keepends=True)]

    section_stack: list[str] = []
    base_dir = os.path.dirname(abs_path)

    for idx, orig_line in enumerate(physical_lines):
        line_no = idx + 1
        uncommented = strip_hyprlang_comment(orig_line).strip()
        if not uncommented:
            continue

        # Section braces tracking
        if uncommented == "}":
            if section_stack:
                section_stack.pop()
            continue
        m_sec = SECTION_OPEN_RE.match(uncommented)
        if m_sec:
            section_stack.append(m_sec.group(1))
            continue

        # Variable definition ($name = value)
        m_var = VAR_DEF_RE.match(uncommented)
        if m_var:
            var_name = m_var.group(1)
            var_raw_val = m_var.group(2).strip()
            expanded_val, _ = expand_variables(var_raw_val, state.variables)
            if var_name == "HOME" and state.home_dir:
                state.variables[var_name] = expanded_val
            else:
                state.variables[var_name] = expanded_val
            continue

        # Inside a block section (e.g. general { ... })
        if section_stack:
            m_gen = GENERIC_KW_RE.match(uncommented)
            if m_gen:
                kw = f"{'.'.join(section_stack)}.{m_gen.group(1)}"
                state.ignored_keywords[kw] = state.ignored_keywords.get(kw, 0) + 1
            continue

        # source = path
        m_src = SOURCE_KW_RE.match(uncommented)
        if m_src:
            raw_src_path = m_src.group(1).strip()
            # Expand $HOME first if referenced, then user variables
            vars_with_home = {"HOME": state.home_dir, **state.variables}
            expanded_src, unresolved_vars = expand_variables(raw_src_path, vars_with_home)
            if unresolved_vars:
                for uv in unresolved_vars:
                    state.diagnostics.append(
                        Diagnostic(
                            level="error",
                            code="unresolved_variable",
                            message=f"Unresolved variable '${uv}' in source path '{raw_src_path}'",
                            file=abs_path,
                            line=line_no,
                        )
                    )
                continue

            home_expanded = _expand_path_home(expanded_src, state.home_dir)
            if not os.path.isabs(home_expanded):
                resolved_target = os.path.abspath(os.path.join(base_dir, home_expanded))
            else:
                resolved_target = os.path.abspath(home_expanded)

            if glob.has_magic(resolved_target):
                matches = sorted(glob.glob(resolved_target))
                if not matches:
                    state.diagnostics.append(
                        Diagnostic(
                            level="warning",
                            code="source_missing",
                            message=f"Glob source pattern matched no files: {resolved_target}",
                            file=abs_path,
                            line=line_no,
                        )
                    )
                for m_path in matches:
                    if os.path.isfile(m_path):
                        _parse_file_recursive(m_path, "loaded", depth + 1, state)
            else:
                if not os.path.isfile(resolved_target):
                    state.diagnostics.append(
                        Diagnostic(
                            level="error",
                            code="source_missing",
                            message=f"Sourced file does not exist: {resolved_target}",
                            file=abs_path,
                            line=line_no,
                        )
                    )
                else:
                    _parse_file_recursive(resolved_target, "loaded", depth + 1, state)
            continue

        # submap = name | reset
        m_sub = SUBMAP_KW_RE.match(uncommented)
        if m_sub:
            sub_val, unresolved_sub = expand_variables(m_sub.group(1).strip(), state.variables)
            for uv in unresolved_sub:
                state.diagnostics.append(
                    Diagnostic(
                        level="warning",
                        code="unresolved_variable",
                        message=f"Unresolved variable '${uv}' in submap directive",
                        file=abs_path,
                        line=line_no,
                    )
                )
            if sub_val in ("reset", ""):
                state.current_submap = ""
            else:
                state.current_submap = sub_val
            continue

        # bind[flags] = ... or unbind = ...
        m_bind = BIND_KW_RE.match(uncommented)
        if m_bind:
            kw = m_bind.group(1)
            rhs = m_bind.group(2)
            if kw == "unbind":
                _handle_unbind_line(kw, rhs, abs_path, line_no, orig_line, state)
            else:
                _handle_bind_line(kw, rhs, abs_path, line_no, orig_line, state)
            continue

        # Other keyword = value at top level
        m_gen = GENERIC_KW_RE.match(uncommented)
        if m_gen:
            kw_name = m_gen.group(1)
            if SUSPICIOUS_PREFIX_RE.match(kw_name):
                state.diagnostics.append(
                    Diagnostic(
                        level="warning",
                        code="unrecognized_line",
                        message=f"Malformed directive '{uncommented}'",
                        file=abs_path,
                        line=line_no,
                    )
                )
            else:
                state.ignored_keywords[kw_name] = (
                    state.ignored_keywords.get(kw_name, 0) + 1
                )
            continue

        # Line without '=' that starts with bind/unbind/submap/source or is otherwise unrecognized
        state.diagnostics.append(
            Diagnostic(
                level="warning",
                code="unrecognized_line",
                message=f"Unrecognized configuration line: '{uncommented}'",
                file=abs_path,
                line=line_no,
            )
        )

    state.active_real_stack.pop()


def _handle_unbind_line(
    _kw: str,
    rhs: str,
    abs_path: str,
    line_no: int,
    orig_line: str,
    state: _ParserState,
) -> None:
    if "," not in rhs:
        state.diagnostics.append(
            Diagnostic(
                level="warning",
                code="unrecognized_line",
                message=f"Malformed unbind directive (expected 'MODS, KEY'): '{orig_line.strip()}'",
                file=abs_path,
                line=line_no,
            )
        )
        return

    raw_parts = _split_n_commas(rhs, 1)
    mods_raw = raw_parts[0]
    key_raw = raw_parts[1]

    mods_exp, unres_m = expand_variables(mods_raw, state.variables)
    key_exp, unres_k = expand_variables(key_raw, state.variables)
    parse_status = "ok"

    for uv in [*unres_m, *unres_k]:
        parse_status = "unresolved"
        state.diagnostics.append(
            Diagnostic(
                level="warning",
                code="unresolved_variable",
                message=f"Unresolved variable '${uv}' in unbind directive",
                file=abs_path,
                line=line_no,
            )
        )

    parsed_mods = resolve_modifier_tokens(_parse_mod_string(mods_exp))
    if parsed_mods.unknown_tokens:
        if parse_status == "ok":
            parse_status = "partial"
        for utok in parsed_mods.unknown_tokens:
            state.diagnostics.append(
                Diagnostic(
                    level="warning",
                    code="unknown_modifier",
                    message=f"Unknown modifier token '{utok}' in unbind directive",
                    file=abs_path,
                    line=line_no,
                )
            )

    state.unbinds.append(
        UnbindRecord(
            modifiers=parsed_mods.modifiers,
            modifiers_raw=mods_raw,
            modmask=parsed_mods.modmask,
            key=key_exp.strip(),
            key_raw=key_raw,
            submap=state.current_submap,
            source_file=abs_path,
            source_line=line_no,
            original_line=orig_line,
            parse_status=parse_status,
        )
    )


def _handle_bind_line(
    kw: str,
    rhs: str,
    abs_path: str,
    line_no: int,
    orig_line: str,
    state: _ParserState,
) -> None:
    flag_letters = kw[4:]  # characters after "bind"
    flags = default_flags()
    flags_extra: dict[str, Any] = {}
    parse_status = "ok"

    for ch in flag_letters:
        if ch not in VALID_BIND_LETTERS:
            parse_status = "unsupported"
            state.diagnostics.append(
                Diagnostic(
                    level="warning",
                    code="unknown_bind_flag",
                    message=f"Unsupported bind flag letter '{ch}' in keyword '{kw}'",
                    file=abs_path,
                    line=line_no,
                )
            )
            flags_extra[f"unknown_flag_{ch}"] = True
        else:
            mapped = LETTER_TO_FLAG[ch]
            if mapped in flags:
                flags[mapped] = True
            else:
                flags_extra[mapped] = True

    has_desc_flag = "d" in flag_letters

    # Split fields according to whether 'd' (description) flag is present
    if has_desc_flag:
        # MODS, KEY, DESCRIPTION, DISPATCHER[, ARGS]
        comma_count = rhs.count(",")
        if comma_count < 3:
            state.diagnostics.append(
                Diagnostic(
                    level="warning",
                    code="unrecognized_line",
                    message=f"Malformed {kw} directive (expected at least 4 comma-separated fields): '{orig_line.strip()}'",
                    file=abs_path,
                    line=line_no,
                )
            )
            return
        raw_fields = _split_n_commas(rhs, 4)
        mods_raw = raw_fields[0]
        key_raw = raw_fields[1]
        desc_raw = raw_fields[2]
        dsp_raw = raw_fields[3]
        args_raw = raw_fields[4] if len(raw_fields) > 4 else ""
    else:
        # MODS, KEY, DISPATCHER[, ARGS]
        comma_count = rhs.count(",")
        if comma_count < 2:
            state.diagnostics.append(
                Diagnostic(
                    level="warning",
                    code="unrecognized_line",
                    message=f"Malformed {kw} directive (expected at least 3 comma-separated fields): '{orig_line.strip()}'",
                    file=abs_path,
                    line=line_no,
                )
            )
            return
        raw_fields = _split_n_commas(rhs, 3)
        mods_raw = raw_fields[0]
        key_raw = raw_fields[1]
        desc_raw = None
        dsp_raw = raw_fields[2]
        args_raw = raw_fields[3] if len(raw_fields) > 3 else ""

    mods_exp, unres_m = expand_variables(mods_raw, state.variables)
    key_exp, unres_k = expand_variables(key_raw, state.variables)
    dsp_exp, unres_d = expand_variables(dsp_raw, state.variables)
    args_exp, unres_a = expand_variables(args_raw, state.variables)
    if desc_raw is not None:
        desc_exp, unres_desc = expand_variables(desc_raw, state.variables)
    else:
        desc_exp, unres_desc = None, []

    all_unresolved = [*unres_m, *unres_k, *unres_desc, *unres_d, *unres_a]
    if all_unresolved:
        if parse_status == "ok":
            parse_status = "unresolved"
        for uv in all_unresolved:
            state.diagnostics.append(
                Diagnostic(
                    level="warning",
                    code="unresolved_variable",
                    message=f"Unresolved variable '${uv}' in {kw} directive",
                    file=abs_path,
                    line=line_no,
                )
            )

    parsed_mods = resolve_modifier_tokens(_parse_mod_string(mods_exp))
    if parsed_mods.unknown_tokens:
        if parse_status == "ok":
            parse_status = "partial"
        for utok in parsed_mods.unknown_tokens:
            state.diagnostics.append(
                Diagnostic(
                    level="warning",
                    code="unknown_modifier",
                    message=f"Unknown modifier token '{utok}' in '{mods_raw}'",
                    file=abs_path,
                    line=line_no,
                )
            )

    key_clean = key_exp.strip()
    if not key_clean:
        if parse_status == "ok":
            parse_status = "partial"
        state.diagnostics.append(
            Diagnostic(
                level="warning",
                code="invalid_key_combo",
                message=f"Empty key in {kw} directive",
                file=abs_path,
                line=line_no,
            )
        )

    key_kind = classify_key_kind(key_clean)
    dsp_clean = dsp_exp.strip()
    args_clean = args_exp.strip()
    dsp_args: list[Any] = [args_clean] if args_clean != "" else []

    site_key = (abs_path, line_no)
    occ = state.site_occurrences.get(site_key, 0)
    state.site_occurrences[site_key] = occ + 1

    keys_raw_combined = f"{mods_raw}, {key_raw}" if mods_raw else f", {key_raw}"
    bind_id = compute_bind_id(
        abs_file=abs_path,
        line=line_no,
        occurrence=occ,
        keys=keys_raw_combined,
        dispatcher_path=dsp_clean,
    )

    trace = [
        TraceFrame(
            file=abs_path,
            line=line_no,
            what="hyprlang",
            istailcall=False,
        )
    ]

    state.binds.append(
        BindRecord(
            id=bind_id,
            language="hyprlang",
            bind_type=kw,
            declared_via=kw,
            modifiers=parsed_mods.modifiers,
            modifiers_raw=mods_raw,
            modmask=parsed_mods.modmask,
            key=key_clean,
            key_kind=key_kind,
            keys_raw=keys_raw_combined,
            flags=flags,
            flags_extra=flags_extra,
            description=desc_exp,
            dispatcher=DispatcherInfo(
                path=dsp_clean,
                args=dsp_args,
                arg_summary=args_clean,
            ),
            submap=state.current_submap,
            source_file=abs_path,
            source_line=line_no,
            original_line=orig_line,
            original_line_number=line_no,
            generated=False,
            occurrence=occ,
            occurrences_at_site=1,
            trace=trace,
            parse_status=parse_status,
            key_raw=key_raw,
            args_raw=args_raw,
        )
    )


def parse_hyprlang_config(
    entrypoint: str,
    home_dir: str | None = None,
) -> tuple[
    list[BindRecord],
    list[UnbindRecord],
    list[FileRecord],
    list[Diagnostic],
    StatsRecord,
    bool,
]:
    """Parse a Hyprlang entrypoint and all sourced files into normalized records."""
    abs_entry = os.path.abspath(entrypoint)
    resolved_home = (
        os.path.abspath(os.path.expanduser(home_dir))
        if home_dir is not None
        else (os.environ.get("HOME") or os.path.expanduser("~"))
    )

    state = _ParserState(home_dir=resolved_home)
    _parse_file_recursive(abs_entry, role="entrypoint", depth=0, state=state)

    if state.current_submap != "":
        state.diagnostics.append(
            Diagnostic(
                level="warning",
                code="unclosed_submap",
                message=f"Submap '{state.current_submap}' was not reset with 'submap = reset' before EOF",
                file=abs_entry,
                line=None,
            )
        )

    # Update occurrences_at_site and generated flag (e.g. if a file was sourced multiple times)
    for b in state.binds:
        total_occ = state.site_occurrences.get((b.source_file, b.source_line), 1)
        b.occurrences_at_site = total_occ
        b.generated = total_occ > 1

    populate_bind_descriptions(state.binds)

    file_records: list[FileRecord] = []
    for fpath, role in state.files_ordered:
        if os.path.isfile(fpath):
            file_records.append(build_file_record(fpath, role=role))

    stats = compute_stats(
        state.binds,
        ignored_calls={},
        ignored_keywords=state.ignored_keywords,
    )
    return (
        state.binds,
        state.unbinds,
        file_records,
        state.diagnostics,
        stats,
        True,
    )
