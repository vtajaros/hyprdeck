"""CLI entrypoint for Hyprland Keybind Studio (HKS) Phase 1."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from backend.conflicts import detect_conflicts
from backend.describe import build_sidecar_template, load_and_apply_sidecar
from backend.discovery import (
    DiscoveryError,
    discover_config,
    probe_hyprctl_binds,
)
from backend.models.types import (
    ConflictStats,
    Diagnostic,
    ScanDocument,
    UnbindRecord,
)
from backend.parser import parse_hyprlang_config, parse_lua_config
from backend.serializer import (
    format_summary_table,
    make_scan_document,
    serialize_scan_document,
)
from backend.validation import (
    compare_with_oracle,
    format_oracle_stderr_summary,
)


class _CleanArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that exits with status 2 without printing a Python traceback."""

    def error(self, message: str) -> None:
        sys.stderr.write(f"hks: error: {message}\n")
        raise SystemExit(2)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = _CleanArgumentParser(
        prog="python -m backend.cli",
        description="Hyprland Keybind Studio (HKS) Phase 1 read-only config scanner.",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    # scan subcommand
    scan_p = subparsers.add_parser(
        "scan",
        help="Scan Hyprland configuration and output normalized JSON to stdout.",
    )
    scan_p.add_argument(
        "--config-dir",
        dest="config_dir",
        default=None,
        help="Override Hyprland configuration directory.",
    )
    scan_p.add_argument(
        "--entrypoint",
        dest="entrypoint",
        default=None,
        help="Override entrypoint configuration file.",
    )
    scan_p.add_argument(
        "--compact",
        action="store_true",
        help="Emit compact single-line JSON instead of pretty-printed JSON.",
    )
    scan_p.add_argument(
        "--oracle",
        action="store_true",
        help="Compare parsed binds against live `hyprctl binds -j` output.",
    )
    scan_p.add_argument(
        "--no-live",
        dest="no_live",
        action="store_true",
        help="Disable optional live hyprctl probing during discovery.",
    )
    scan_p.add_argument(
        "--sidecar",
        dest="sidecar",
        default=None,
        help="Explicit path to a sidecar descriptions.json override file.",
    )
    scan_p.add_argument(
        "--no-sidecar",
        dest="no_sidecar",
        action="store_true",
        help="Disable loading any sidecar overrides.",
    )

    # summary subcommand
    sum_p = subparsers.add_parser(
        "summary",
        help="Print a human-readable plain-text table of parsed keybindings.",
    )
    sum_p.add_argument(
        "--config-dir",
        dest="config_dir",
        default=None,
        help="Override Hyprland configuration directory.",
    )
    sum_p.add_argument(
        "--entrypoint",
        dest="entrypoint",
        default=None,
        help="Override entrypoint configuration file.",
    )
    sum_p.add_argument(
        "--no-live",
        dest="no_live",
        action="store_true",
        help="Disable optional live hyprctl probing during discovery.",
    )
    sum_p.add_argument(
        "--sidecar",
        dest="sidecar",
        default=None,
        help="Explicit path to a sidecar descriptions.json override file.",
    )
    sum_p.add_argument(
        "--no-sidecar",
        dest="no_sidecar",
        action="store_true",
        help="Disable loading any sidecar overrides.",
    )

    # sidecar-template subcommand
    tpl_p = subparsers.add_parser(
        "sidecar-template",
        help="Print a valid sidecar descriptions.json template to stdout.",
    )
    tpl_p.add_argument(
        "--all",
        dest="include_all",
        action="store_true",
        help="Scan current config and emit an override entry per unique keybind.",
    )
    tpl_p.add_argument(
        "--config-dir",
        dest="config_dir",
        default=None,
        help="Override Hyprland configuration directory (used with --all).",
    )
    tpl_p.add_argument(
        "--entrypoint",
        dest="entrypoint",
        default=None,
        help="Override entrypoint configuration file (used with --all).",
    )
    tpl_p.add_argument(
        "--no-live",
        dest="no_live",
        action="store_true",
        help="Disable optional live hyprctl probing during discovery (used with --all).",
    )

    return parser


def run_scan_pipeline(
    config_dir: str | None = None,
    entrypoint: str | None = None,
    no_live: bool = False,
    with_oracle: bool = False,
    live_binds_override: list[dict[str, Any]] | None = None,
    sidecar_path: str | None = None,
    no_sidecar: bool = False,
    env: dict[str, str] | None = None,
) -> tuple[ScanDocument, int]:
    """Execute discovery, parsing, sidecar overrides, and optional oracle verification.

    Returns (ScanDocument, exit_code).
    """
    disc = discover_config(
        config_dir=config_dir,
        entrypoint=entrypoint,
        no_live=no_live,
        live_binds_override=live_binds_override,
        env=env,
    )

    all_diagnostics: list[Diagnostic] = list(disc.diagnostics)
    unbinds: list[UnbindRecord] = []

    if disc.environment.language == "lua":
        binds, files, parse_diags, stats, complete = parse_lua_config(
            entrypoint=disc.environment.entrypoint,
            config_dir=disc.environment.config_dir,
            env=env,
        )
    else:
        binds, unbinds, files, parse_diags, stats, complete = parse_hyprlang_config(
            entrypoint=disc.environment.entrypoint,
        )

    all_diagnostics.extend(parse_diags)

    sidecar_stats, sidecar_diags = load_and_apply_sidecar(
        binds=binds,
        cli_path=sidecar_path,
        no_sidecar=no_sidecar,
        env=env,
    )
    stats.sidecar = sidecar_stats
    all_diagnostics.extend(sidecar_diags)

    conflicts = detect_conflicts(binds)
    stats.conflicts = ConflictStats(
        total=len(conflicts),
        duplicate=sum(1 for c in conflicts if c.kind == "duplicate"),
        multiple_actions=sum(1 for c in conflicts if c.kind == "multiple_actions"),
    )

    oracle_dict: dict[str, Any] | None = None
    exit_code = 0

    if with_oracle:
        live_binds = (
            live_binds_override
            if live_binds_override is not None
            else (disc.live_binds if disc.live_binds is not None else probe_hyprctl_binds())
        )
        if live_binds is None:
            all_diagnostics.append(
                Diagnostic(
                    level="error",
                    code="oracle_unavailable",
                    message="Cannot run oracle comparison: `hyprctl binds -j` data is unavailable.",
                    file=disc.environment.entrypoint,
                    line=None,
                )
            )
            oracle_dict = {
                "count_match": False,
                "extra_in_parser": [],
                "live_count": 0,
                "matched": False,
                "missing_in_parser": [],
                "order_match": False,
                "parser_count": len(binds),
            }
            sys.stderr.write(
                "[HKS Oracle] ERROR: `hyprctl binds -j` is unavailable.\n"
            )
            exit_code = 1
        else:
            report = compare_with_oracle(binds, live_binds)
            oracle_dict = report.to_dict()
            sys.stderr.write(format_oracle_stderr_summary(report) + "\n")
            if not report.matched:
                exit_code = 1

    doc = make_scan_document(
        environment=disc.environment,
        files=files,
        binds=binds,
        unbinds=unbinds,
        diagnostics=all_diagnostics,
        stats=stats,
        complete=complete,
        conflicts=conflicts,
        oracle=oracle_dict,
    )
    return doc, exit_code


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    if not args.subcommand:
        parser.print_usage(sys.stderr)
        sys.stderr.write(
            "hks: error: subcommand required (choose from 'scan', 'summary', 'sidecar-template')\n"
        )
        return 2

    try:
        if args.subcommand == "scan":
            doc, exit_code = run_scan_pipeline(
                config_dir=args.config_dir,
                entrypoint=args.entrypoint,
                no_live=args.no_live,
                with_oracle=args.oracle,
                sidecar_path=args.sidecar,
                no_sidecar=args.no_sidecar,
            )
            sys.stdout.write(serialize_scan_document(doc, compact=args.compact) + "\n")
            sys.stdout.flush()
            return exit_code

        if args.subcommand == "summary":
            doc, _ = run_scan_pipeline(
                config_dir=args.config_dir,
                entrypoint=args.entrypoint,
                no_live=args.no_live,
                with_oracle=False,
                sidecar_path=args.sidecar,
                no_sidecar=args.no_sidecar,
            )
            sys.stdout.write(format_summary_table(doc) + "\n")
            sys.stdout.flush()
            return 0

        if args.subcommand == "sidecar-template":
            if args.include_all:
                doc, _ = run_scan_pipeline(
                    config_dir=args.config_dir,
                    entrypoint=args.entrypoint,
                    no_live=args.no_live,
                    with_oracle=False,
                    no_sidecar=True,
                )
                tpl = build_sidecar_template(binds=doc.binds, include_all=True)
            else:
                tpl = build_sidecar_template(include_all=False)
            sys.stdout.write(json.dumps(tpl, indent=2, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            return 0
    except DiscoveryError as exc:
        sys.stderr.write(f"hks: error: {exc}\n")
        return 2
    except OSError as exc:
        sys.stderr.write(f"hks: error: {exc}\n")
        return 2
    except Exception as exc:  # pragma: no cover - defensive guard against raw tracebacks
        sys.stderr.write(f"hks: internal error: {exc}\n")
        return 2

    return 2


if __name__ == "__main__":
    sys.exit(main())
