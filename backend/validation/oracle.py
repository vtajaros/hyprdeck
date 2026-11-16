"""Oracle comparison between HyprDeck parsed binds and live `hyprctl binds -j` data."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from backend.models.types import BindRecord

HL_DISPATCHER_RE = re.compile(r"^HL\.Dispatcher\((.+)\)$")

OracleTuple = tuple[int, str, bool, bool, bool, bool, bool, str]


@dataclass(slots=True)
class OracleReport:
    matched: bool
    count_match: bool
    order_match: bool
    parser_count: int
    live_count: int
    missing_in_parser: list[dict[str, Any]]
    extra_in_parser: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "count_match": self.count_match,
            "extra_in_parser": self.extra_in_parser,
            "live_count": self.live_count,
            "matched": self.matched,
            "missing_in_parser": self.missing_in_parser,
            "order_match": self.order_match,
            "parser_count": self.parser_count,
        }


def extract_live_short_dispatcher(raw_dispatcher: str) -> str:
    """Extract the short dispatcher name from a `hyprctl binds -j` dispatcher string."""
    s = raw_dispatcher.strip()
    m = HL_DISPATCHER_RE.match(s)
    if m:
        s = m.group(1).strip()
    if "." in s:
        s = s.rsplit(".", 1)[-1]
    return s


def extract_parser_short_dispatcher(dispatcher_path: str) -> str:
    """Extract the last segment of a parser dispatcher path (e.g. window.move -> move)."""
    s = dispatcher_path.strip()
    if "." in s:
        return s.rsplit(".", 1)[-1]
    return s


def bind_record_to_tuple(b: BindRecord) -> OracleTuple:
    return (
        int(b.modmask),
        b.key.lower(),
        bool(b.flags.get("locked", False)),
        bool(b.flags.get("repeating", False)),
        bool(b.flags.get("mouse", False)),
        bool(b.flags.get("release", False)),
        bool(b.flags.get("non_consuming", False)),
        extract_parser_short_dispatcher(b.dispatcher.path),
    )


def live_entry_to_tuple(entry: dict[str, Any]) -> OracleTuple:
    raw_dsp = str(entry.get("dispatcher", ""))
    return (
        int(entry.get("modmask", 0)),
        str(entry.get("key", "")).lower(),
        bool(entry.get("locked", False)),
        bool(entry.get("repeat", False)),
        bool(entry.get("mouse", False)),
        bool(entry.get("release", False)),
        bool(entry.get("non_consuming", False)),
        extract_live_short_dispatcher(raw_dsp),
    )


def _tuple_to_dict(t: OracleTuple) -> dict[str, Any]:
    return {
        "dispatcher": t[7],
        "key": t[1],
        "locked": t[2],
        "modmask": t[0],
        "mouse": t[4],
        "non_consuming": t[6],
        "release": t[5],
        "repeat": t[3],
    }


def compare_with_oracle(
    parser_binds: list[BindRecord],
    live_binds: list[dict[str, Any]],
) -> OracleReport:
    """Compare parsed BindRecords against live `hyprctl binds -j` entries as multisets."""
    parser_tuples = [bind_record_to_tuple(b) for b in parser_binds]
    live_tuples = [
        live_entry_to_tuple(lb)
        for lb in live_binds
        if isinstance(lb, dict) and lb.get("submap") != "hks_record"
    ]

    parser_counter = Counter(parser_tuples)
    live_counter = Counter(live_tuples)

    missing_counter = live_counter - parser_counter
    extra_counter = parser_counter - live_counter

    missing_list = [_tuple_to_dict(t) for t in sorted(missing_counter.elements())]
    extra_list = [_tuple_to_dict(t) for t in sorted(extra_counter.elements())]

    matched = (len(missing_list) == 0) and (len(extra_list) == 0)
    count_match = len(parser_tuples) == len(live_tuples)
    order_match = parser_tuples == live_tuples

    return OracleReport(
        matched=matched,
        count_match=count_match,
        order_match=order_match,
        parser_count=len(parser_tuples),
        live_count=len(live_tuples),
        missing_in_parser=missing_list,
        extra_in_parser=extra_list,
    )


def format_oracle_stderr_summary(report: OracleReport) -> str:
    """Format a concise human-readable summary of the oracle comparison for stderr."""
    status = "MATCH" if report.matched else "MISMATCH"
    lines = [
        f"[HyprDeck Oracle] Status: {status} "
        f"(parser={report.parser_count}, live={report.live_count}, "
        f"count_match={report.count_match}, order_match={report.order_match})"
    ]
    if report.missing_in_parser:
        lines.append(f"  Missing in parser ({len(report.missing_in_parser)}):")
        for item in report.missing_in_parser[:10]:
            lines.append(
                f"    - modmask={item['modmask']} key={item['key']} dsp={item['dispatcher']}"
            )
    if report.extra_in_parser:
        lines.append(f"  Extra in parser ({len(report.extra_in_parser)}):")
        for item in report.extra_in_parser[:10]:
            lines.append(
                f"    + modmask={item['modmask']} key={item['key']} dsp={item['dispatcher']}"
            )
    return "\n".join(lines)
