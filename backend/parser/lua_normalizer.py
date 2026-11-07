"""Normalizer for recorded Lua keybindings into the HKS Phase 1 schema."""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from backend.discovery.config_discovery import build_file_record
from backend.models.types import (
    BindRecord,
    Diagnostic,
    DispatcherInfo,
    FileRecord,
    SandboxStats,
    StatsRecord,
    TraceFrame,
    default_flags,
)
from backend.parser.lua_runner import RawRecorderOutput, run_lua_recorder
from backend.parser.modifiers import (
    classify_key_kind,
    derive_bind_type_from_flags,
    resolve_modifier_tokens,
)

DECLARED_VIA_RE = re.compile(r"\bhl\.(bind\w*)\s*\(")

KNOWN_OPT_FLAGS: dict[str, str] = {
    "locked": "locked",
    "repeating": "repeating",
    "repeat": "repeating",
    "release": "release",
    "mouse": "mouse",
    "non_consuming": "non_consuming",
    "long_press": "long_press",
    "transparent": "transparent",
    "ignore_mods": "ignore_mods",
}


def summarize_dispatcher_args(args: list[Any]) -> str:
    """Format dispatcher arguments into a concise deterministic string summary."""
    if not args:
        return ""
    if len(args) == 1:
        first = args[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return ", ".join(f"{k}={first[k]}" for k in sorted(first.keys()))
        return json.dumps(first, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    return json.dumps(args, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def compute_bind_id(
    abs_file: str,
    line: int,
    occurrence: int,
    keys: str,
    dispatcher_path: str,
) -> str:
    """Compute stable 12-hex SHA1 bind identifier."""
    payload = f"{abs_file}|{line}|{occurrence}|{keys}|{dispatcher_path}"
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"b_{digest}"


def compute_stats(
    binds: list[BindRecord],
    ignored_calls: dict[str, int] | None = None,
    ignored_keywords: dict[str, int] | None = None,
    sandbox: SandboxStats | None = None,
) -> StatsRecord:
    """Aggregate statistics across all normalized binds."""
    by_type: dict[str, int] = {}
    by_dispatcher_path: dict[str, int] = {}
    flag_counts: dict[str, int] = {k: 0 for k in default_flags()}
    by_modmask: dict[str, int] = {}
    generated_binds = 0
    partial = 0
    unsupported = 0
    unresolved = 0

    for b in binds:
        by_type[b.bind_type] = by_type.get(b.bind_type, 0) + 1
        dsp_path = b.dispatcher.path
        by_dispatcher_path[dsp_path] = by_dispatcher_path.get(dsp_path, 0) + 1
        for fk, fv in b.flags.items():
            if fv:
                flag_counts[fk] = flag_counts.get(fk, 0) + 1
        mm_key = str(b.modmask)
        by_modmask[mm_key] = by_modmask.get(mm_key, 0) + 1
        if b.generated:
            generated_binds += 1
        if b.parse_status == "partial":
            partial += 1
        elif b.parse_status == "unsupported":
            unsupported += 1
        elif b.parse_status == "unresolved":
            unresolved += 1

    return StatsRecord(
        total_binds=len(binds),
        by_type=by_type,
        by_dispatcher_path=by_dispatcher_path,
        flag_counts=flag_counts,
        by_modmask=by_modmask,
        generated_binds=generated_binds,
        partial=partial,
        unsupported=unsupported,
        unresolved=unresolved,
        ignored_calls=dict(ignored_calls or {}),
        ignored_keywords=dict(ignored_keywords or {}),
        sandbox=sandbox,
    )


def _read_lines_preserved(file_path: str, cache: dict[str, list[str]]) -> list[str]:
    if file_path in cache:
        return cache[file_path]
    lines: list[str] = []
    try:
        with open(file_path, "rb") as f:
            raw = f.read()
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        text = raw.decode("utf-8", errors="replace")
        lines = [ln.rstrip("\r\n") for ln in text.splitlines(keepends=True)]
    except OSError:
        lines = []
    cache[file_path] = lines
    return lines


def normalize_lua_output(
    raw_output: RawRecorderOutput,
    entrypoint: str,
) -> tuple[list[BindRecord], list[FileRecord], list[Diagnostic], StatsRecord, bool]:
    """Normalize RawRecorderOutput into BindRecords, FileRecords, Diagnostics, and StatsRecord."""
    abs_entry = os.path.abspath(entrypoint)
    diagnostics: list[Diagnostic] = list(raw_output.diagnostics)
    has_submap_warn = any(d.code == "lua_submap_unsupported" for d in diagnostics)

    # Check ignored_calls for submap mention
    for api_name in raw_output.ignored_calls:
        if "submap" in api_name.lower() and not has_submap_warn:
            has_submap_warn = True
            diagnostics.append(
                Diagnostic(
                    level="warning",
                    code="lua_submap_unsupported",
                    message=f"Lua API '{api_name}' mentions submap; Lua submap semantics are unverified.",
                    file=abs_entry,
                    line=None,
                )
            )

    line_cache: dict[str, list[str]] = {}
    binds: list[BindRecord] = []

    for rb in raw_output.binds:
        source_file = os.path.abspath(str(rb.get("source_file") or abs_entry))
        source_line = int(rb.get("source_line") or 0)
        occurrence = int(rb.get("occurrence") or 0)
        occurrences_at_site = int(rb.get("occurrences_at_site") or 1)
        parse_status = str(rb.get("parse_status") or "ok")

        file_lines = _read_lines_preserved(source_file, line_cache)
        original_line = (
            file_lines[source_line - 1]
            if 1 <= source_line <= len(file_lines)
            else ""
        )

        m_decl = DECLARED_VIA_RE.search(original_line)
        declared_via = m_decl.group(1) if m_decl else None

        keys_raw = str(rb.get("keys") if rb.get("keys") is not None else "")
        raw_parts = [p.strip() for p in keys_raw.split("+")]

        if not keys_raw.strip() or any(p == "" for p in raw_parts):
            if parse_status == "ok":
                parse_status = "partial"
            diagnostics.append(
                Diagnostic(
                    level="warning",
                    code="invalid_key_combo",
                    message=f"Key combination has empty token or trailing '+': '{keys_raw}'",
                    file=source_file,
                    line=source_line,
                )
            )
            non_empty = [p for p in raw_parts if p != ""]
            mod_tokens = non_empty[:-1] if len(non_empty) > 1 else []
            key = non_empty[-1] if non_empty else ""
        else:
            mod_tokens = raw_parts[:-1]
            key = raw_parts[-1]

        parsed_mods = resolve_modifier_tokens(mod_tokens)
        if parsed_mods.unknown_tokens:
            if parse_status == "ok":
                parse_status = "partial"
            for utok in parsed_mods.unknown_tokens:
                diagnostics.append(
                    Diagnostic(
                        level="warning",
                        code="unknown_modifier",
                        message=f"Unknown modifier token '{utok}' in '{keys_raw}'",
                        file=source_file,
                        line=source_line,
                    )
                )

        modifiers_raw = " + ".join(mod_tokens)
        key_kind = classify_key_kind(key)

        flags = default_flags()
        flags_extra: dict[str, Any] = {}
        description: str | None = None

        raw_opts = rb.get("opts")
        if isinstance(raw_opts, dict):
            for opt_k, opt_v in sorted(raw_opts.items()):
                if opt_k == "description":
                    description = str(opt_v)
                elif opt_k in KNOWN_OPT_FLAGS:
                    flags[KNOWN_OPT_FLAGS[opt_k]] = bool(opt_v)
                elif opt_k == "_raw_opts":
                    flags_extra[opt_k] = opt_v
                else:
                    flags_extra[opt_k] = opt_v
                    diagnostics.append(
                        Diagnostic(
                            level="info",
                            code="unknown_bind_opt",
                            message=f"Unrecognized bind option '{opt_k}' saved in flags_extra",
                            file=source_file,
                            line=source_line,
                        )
                    )

        bind_type = derive_bind_type_from_flags(
            flags, has_description=bool(description)
        )

        raw_dsp = rb.get("dispatcher")
        if isinstance(raw_dsp, dict):
            dsp_path = str(raw_dsp.get("path") or "")
            raw_args = raw_dsp.get("args")
            dsp_args = list(raw_args) if isinstance(raw_args, list) else []
            cb_line = (
                int(raw_dsp["callback_line"])
                if isinstance(raw_dsp.get("callback_line"), int)
                else None
            )
        else:
            dsp_path = "<unsupported>"
            dsp_args = []
            cb_line = None
            parse_status = "unsupported"

        if "submap" in dsp_path.lower() and not has_submap_warn:
            has_submap_warn = True
            diagnostics.append(
                Diagnostic(
                    level="warning",
                    code="lua_submap_unsupported",
                    message=f"Lua dispatcher path '{dsp_path}' mentions submap; Lua submap semantics are unverified.",
                    file=source_file,
                    line=source_line,
                )
            )

        arg_summary = summarize_dispatcher_args(dsp_args)
        dispatcher_info = DispatcherInfo(
            path=dsp_path,
            args=dsp_args,
            arg_summary=arg_summary,
            callback_line=cb_line,
        )

        raw_trace = rb.get("trace")
        trace_frames: list[TraceFrame] = []
        if isinstance(raw_trace, list):
            for tf in raw_trace:
                if isinstance(tf, dict):
                    trace_frames.append(
                        TraceFrame(
                            file=os.path.abspath(str(tf.get("file") or source_file)),
                            line=int(tf.get("line") or 0),
                            what=str(tf.get("what") or "Lua"),
                            istailcall=bool(tf.get("istailcall", False)),
                        )
                    )

        bind_id = compute_bind_id(
            abs_file=source_file,
            line=source_line,
            occurrence=occurrence,
            keys=keys_raw,
            dispatcher_path=dsp_path,
        )

        binds.append(
            BindRecord(
                id=bind_id,
                language="lua",
                bind_type=bind_type,
                declared_via=declared_via,
                modifiers=parsed_mods.modifiers,
                modifiers_raw=modifiers_raw,
                modmask=parsed_mods.modmask,
                key=key,
                key_kind=key_kind,
                keys_raw=keys_raw,
                flags=flags,
                flags_extra=flags_extra,
                description=description,
                dispatcher=dispatcher_info,
                submap="",
                source_file=source_file,
                source_line=source_line,
                original_line=original_line,
                original_line_number=source_line,
                generated=occurrences_at_site > 1,
                occurrence=occurrence,
                occurrences_at_site=occurrences_at_site,
                trace=trace_frames,
                parse_status=parse_status,
                key_raw=key,
                args_raw=arg_summary,
            )
        )

    # Build FileRecords for entrypoint and loaded files
    seen_files: set[str] = set()
    file_records: list[FileRecord] = []
    ordered_paths = [abs_entry] + [os.path.abspath(p) for p in raw_output.files_loaded]
    for fpath in ordered_paths:
        if fpath in seen_files:
            continue
        seen_files.add(fpath)
        if os.path.isfile(fpath):
            role = "entrypoint" if fpath == abs_entry else "loaded"
            file_records.append(build_file_record(fpath, role=role))

    stats = compute_stats(
        binds,
        ignored_calls=raw_output.ignored_calls,
        sandbox=raw_output.sandbox,
    )
    return binds, file_records, diagnostics, stats, raw_output.complete


def parse_lua_config(
    entrypoint: str,
    config_dir: str,
    instruction_limit: int | None = None,
    timeout: float = 15.0,
    env: dict[str, str] | None = None,
) -> tuple[list[BindRecord], list[FileRecord], list[Diagnostic], StatsRecord, bool]:
    """Run the Lua sandbox recorder and normalize its output."""
    raw = run_lua_recorder(
        entrypoint=entrypoint,
        config_dir=config_dir,
        instruction_limit=instruction_limit,
        timeout=timeout,
        env=env,
    )
    return normalize_lua_output(raw, entrypoint=entrypoint)
