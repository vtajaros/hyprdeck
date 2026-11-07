"""Deterministic JSON serializer and plain-text summary formatter for HKS."""

from __future__ import annotations

import datetime
import json
import os
from typing import Any

import backend
from backend.models.types import (
    BindRecord,
    ConflictRecord,
    Diagnostic,
    EnvironmentInfo,
    FileRecord,
    ScanDocument,
    StatsRecord,
    UnbindRecord,
)


def make_scan_document(
    environment: EnvironmentInfo,
    files: list[FileRecord],
    binds: list[BindRecord],
    unbinds: list[UnbindRecord],
    diagnostics: list[Diagnostic],
    stats: StatsRecord,
    complete: bool,
    conflicts: list[ConflictRecord] | None = None,
    oracle: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> ScanDocument:
    """Create a complete ScanDocument ready for serialization."""
    ts = (
        generated_at
        if generated_at is not None
        else datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    return ScanDocument(
        schema_version=1,
        tool={
            "name": backend.__tool_name__,
            "version": backend.__version__,
        },
        generated_at=ts,
        environment=environment,
        files=files,
        binds=binds,
        unbinds=unbinds,
        diagnostics=diagnostics,
        stats=stats,
        complete=complete,
        conflicts=conflicts if conflicts is not None else [],
        oracle=oracle,
    )


def serialize_scan_document(doc: ScanDocument, compact: bool = False) -> str:
    """Serialize a ScanDocument to deterministic JSON with sorted keys."""
    payload = doc.to_dict()
    if compact:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    return json.dumps(
        payload,
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
    )


def _truncate_cell(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    if width <= 3:
        return value[:width]
    return value[: width - 3] + "..."


def format_summary_table(doc: ScanDocument) -> str:
    """Format a plain-text summary table within 120 columns:
    SHORTCUT | DISPATCHER | ARGS | DESCRIPTION | CATEGORY | file:line
    """
    rows: list[tuple[str, str, str, str, str, str]] = []
    for b in doc.binds:
        if b.modifiers:
            shortcut = " + ".join([*b.modifiers, b.key])
        else:
            shortcut = b.key
        dsp = b.dispatcher.path
        args = b.dispatcher.arg_summary
        desc = b.description_effective.text
        cat = b.category
        loc = f"{os.path.basename(b.source_file)}:{b.source_line}"
        rows.append((shortcut, dsp, args, desc, cat, loc))

    headers = ("SHORTCUT", "DISPATCHER", "ARGS", "DESCRIPTION", "CATEGORY", "file:line")
    w0 = min(22, max([len(headers[0]), *(len(r[0]) for r in rows)], default=len(headers[0])))
    w1 = min(22, max([len(headers[1]), *(len(r[1]) for r in rows)], default=len(headers[1])))
    w3 = min(28, max([len(headers[3]), *(len(r[3]) for r in rows)], default=len(headers[3])))
    w4 = min(16, max([len(headers[4]), *(len(r[4]) for r in rows)], default=len(headers[4])))
    w5 = min(18, max([len(headers[5]), *(len(r[5]) for r in rows)], default=len(headers[5])))

    # 5 separators of " | " take 15 columns; keep total table width <= 120 columns
    max_args_width = max(len(headers[2]), 120 - (w0 + w1 + w3 + w4 + w5 + 15))
    w2 = min(max_args_width, max([len(headers[2]), *(len(r[2]) for r in rows)], default=len(headers[2])))

    lines: list[str] = []
    header_line = (
        f"{headers[0]:<{w0}} | {headers[1]:<{w1}} | {headers[2]:<{w2}} | "
        f"{headers[3]:<{w3}} | {headers[4]:<{w4}} | {headers[5]}"
    )
    sep_line = (
        f"{'-' * w0}-+-{'-' * w1}-+-{'-' * w2}-+-"
        f"{'-' * w3}-+-{'-' * w4}-+-{'-' * max(len(headers[5]), w5)}"
    )
    lines.append(header_line)
    lines.append(sep_line)
    for sc, dsp, arg_str, desc, cat, loc in rows:
        c0 = _truncate_cell(sc, w0)
        c1 = _truncate_cell(dsp, w1)
        c2 = _truncate_cell(arg_str, w2)
        c3 = _truncate_cell(desc, w3)
        c4 = _truncate_cell(cat, w4)
        c5 = _truncate_cell(loc, w5)
        lines.append(
            f"{c0:<{w0}} | {c1:<{w1}} | {c2:<{w2}} | {c3:<{w3}} | {c4:<{w4}} | {c5}"
        )

    if doc.stats.sandbox is not None:
        sb = doc.stats.sandbox
        lines.append(
            f"Sandbox: {sb.instructions_used:,}/{sb.instruction_limit:,} instructions | "
            f"{sb.elapsed_ms:.1f}ms elapsed | cpu_limit={sb.cpu_limit_s:.0f}s | wall_timeout={sb.wall_timeout_s:.0f}s"
        )
    return "\n".join(lines)


def format_conflicts_table(doc: ScanDocument) -> str:
    """Format a plain-text table of conflicting and stacked keybindings."""
    if not doc.conflicts:
        return "No conflicts found."

    stats = doc.stats.conflicts
    header_summary = (
        f"Conflicts: {stats.total} total "
        f"({stats.duplicate} duplicate, {stats.multiple_actions} multiple_actions)"
    )

    rows: list[tuple[str, str, str, str, str, str]] = []
    for c in doc.conflicts:
        cid = c.id
        sev = c.severity
        kind = c.kind
        if c.modifiers:
            shortcut = " + ".join([*c.modifiers, c.key])
        else:
            shortcut = c.key
        if c.submap:
            shortcut = f"[{c.submap}] {shortcut}"
        binds_cnt = str(len(c.bind_ids))
        sources_str = ", ".join(
            f"{os.path.basename(s['file'])}:{s['line']}" for s in c.sources
        )
        rows.append((cid, sev, kind, shortcut, binds_cnt, sources_str))

    headers = ("ID", "SEVERITY", "KIND", "SHORTCUT", "BINDS", "SOURCES")
    w0 = max([len(headers[0]), *(len(r[0]) for r in rows)], default=len(headers[0]))
    w1 = max([len(headers[1]), *(len(r[1]) for r in rows)], default=len(headers[1]))
    w2 = max([len(headers[2]), *(len(r[2]) for r in rows)], default=len(headers[2]))
    w3 = max([len(headers[3]), *(len(r[3]) for r in rows)], default=len(headers[3]))
    w4 = max([len(headers[4]), *(len(r[4]) for r in rows)], default=len(headers[4]))
    w5 = max([len(headers[5]), *(len(r[5]) for r in rows)], default=len(headers[5]))

    lines: list[str] = [header_summary, ""]
    header_line = (
        f"{headers[0]:<{w0}} | {headers[1]:<{w1}} | {headers[2]:<{w2}} | "
        f"{headers[3]:<{w3}} | {headers[4]:<{w4}} | {headers[5]}"
    )
    sep_line = (
        f"{'-' * w0}-+-{'-' * w1}-+-{'-' * w2}-+-"
        f"{'-' * w3}-+-{'-' * w4}-+-{'-' * w5}"
    )
    lines.append(header_line)
    lines.append(sep_line)
    for r in rows:
        lines.append(
            f"{r[0]:<{w0}} | {r[1]:<{w1}} | {r[2]:<{w2}} | "
            f"{r[3]:<{w3}} | {r[4]:<{w4}} | {r[5]}"
        )
    return "\n".join(lines)
