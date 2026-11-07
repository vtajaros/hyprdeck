"""Deterministic JSON serializer and plain-text summary formatter for HKS."""

from __future__ import annotations

import datetime
import json
from typing import Any

import backend
from backend.models.types import (
    BindRecord,
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


def format_summary_table(doc: ScanDocument) -> str:
    """Format a plain-text summary table: SHORTCUT | DISPATCHER | ARGS | file:line."""
    rows: list[tuple[str, str, str, str]] = []
    for b in doc.binds:
        if b.modifiers:
            shortcut = " + ".join([*b.modifiers, b.key])
        else:
            shortcut = b.key
        dsp = b.dispatcher.path
        args = b.dispatcher.arg_summary
        loc = f"{b.source_file}:{b.source_line}"
        rows.append((shortcut, dsp, args, loc))

    headers = ("SHORTCUT", "DISPATCHER", "ARGS", "file:line")
    w0 = max([len(headers[0]), *(len(r[0]) for r in rows)], default=len(headers[0]))
    w1 = max([len(headers[1]), *(len(r[1]) for r in rows)], default=len(headers[1]))
    w2 = min(48, max([len(headers[2]), *(len(r[2]) for r in rows)], default=len(headers[2])))

    lines: list[str] = []
    header_line = f"{headers[0]:<{w0}} | {headers[1]:<{w1}} | {headers[2]:<{w2}} | {headers[3]}"
    sep_line = f"{'-' * w0}-+-{'-' * w1}-+-{'-' * w2}-+-{'-' * len(headers[3])}"
    lines.append(header_line)
    lines.append(sep_line)
    for sc, dsp, arg_str, loc in rows:
        trunc_arg = arg_str if len(arg_str) <= w2 else (arg_str[: w2 - 3] + "...")
        lines.append(f"{sc:<{w0}} | {dsp:<{w1}} | {trunc_arg:<{w2}} | {loc}")
    return "\n".join(lines)
