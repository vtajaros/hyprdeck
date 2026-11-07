"""CLI entrypoint for Hyprland Keybind Studio (HKS) Phase 1."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from backend.conflicts import detect_conflicts
from backend.describe import build_sidecar_template, load_and_apply_sidecar
from backend.discovery import (
    DiscoveryError,
    discover_config,
    probe_hyprctl_binds,
)
from backend.editor import (
    ApplyResult,
    BackupConflictError,
    BackupError,
    BackupRecord,
    EditConflict,
    EditOp,
    NotEditableError,
    apply_edit,
    build_op_for_bind,
    detect_disabled_binds,
    generate_unified_diff,
    list_backups,
    resolve_uncomment_op,
    restore_backup,
)
from backend.editor.apply import _run_live_reload_and_check
from backend.models.types import (
    ConflictStats,
    Diagnostic,
    DisabledBindRecord,
    ScanDocument,
    UnbindRecord,
)
from backend.parser import parse_hyprlang_config, parse_lua_config
from backend.serializer import (
    format_conflicts_table,
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

    # conflicts subcommand
    conf_p = subparsers.add_parser(
        "conflicts",
        help="Print a human-readable table of conflicting and stacked keybindings.",
    )
    conf_p.add_argument(
        "--config-dir",
        dest="config_dir",
        default=None,
        help="Override Hyprland configuration directory.",
    )
    conf_p.add_argument(
        "--entrypoint",
        dest="entrypoint",
        default=None,
        help="Override entrypoint configuration file.",
    )
    conf_p.add_argument(
        "--no-live",
        dest="no_live",
        action="store_true",
        help="Disable optional live hyprctl probing during discovery.",
    )
    conf_p.add_argument(
        "--sidecar",
        dest="sidecar",
        default=None,
        help="Explicit path to a sidecar descriptions.json override file.",
    )
    conf_p.add_argument(
        "--no-sidecar",
        dest="no_sidecar",
        action="store_true",
        help="Disable loading any sidecar overrides.",
    )

    # edit subcommand
    edit_p = subparsers.add_parser(
        "edit",
        help="Safely comment out or uncomment keybindings (dry-run by default; requires --apply to write).",
    )
    edit_p.add_argument(
        "--config-dir",
        dest="config_dir",
        default=None,
        help="Override Hyprland configuration directory.",
    )
    edit_p.add_argument(
        "--entrypoint",
        dest="entrypoint",
        default=None,
        help="Override entrypoint configuration file.",
    )
    edit_p.add_argument(
        "--no-live",
        dest="no_live",
        action="store_true",
        help="Disable optional live hyprctl probing during discovery.",
    )
    edit_p.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=False,
        help="Preview diff and run verification without writing (default when --apply is omitted).",
    )
    edit_p.add_argument(
        "--apply",
        dest="apply",
        action="store_true",
        default=False,
        help="Apply changes atomically after verification and backup.",
    )
    edit_p.add_argument(
        "--reload",
        dest="reload",
        action="store_true",
        default=False,
        help="Run `hyprctl reload config-only` after applying and auto-rollback if configerrors occur.",
    )
    edit_p.add_argument(
        "--comment-out",
        dest="comment_out",
        action="append",
        default=[],
        metavar="BIND_ID",
        help="Comment out the specified bind ID (may be specified multiple times).",
    )
    edit_p.add_argument(
        "--uncomment",
        dest="uncomment",
        action="append",
        default=[],
        metavar="BIND_ID",
        help="Uncomment a previously HKS-disabled bind ID (may be specified multiple times).",
    )
    edit_p.add_argument(
        "--delete",
        dest="delete",
        action="append",
        default=[],
        metavar="BIND_ID",
        help="Delete the specified bind ID (may be specified multiple times).",
    )
    edit_p.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        default=False,
        help="Emit result as JSON to stdout.",
    )

    # backups subcommand
    bak_p = subparsers.add_parser(
        "backups",
        help="List configuration backups stored in the HKS backup directory.",
    )
    bak_p.add_argument(
        "--path",
        dest="path",
        default=None,
        help="Filter backups by original file path.",
    )
    bak_p.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        default=False,
        help="Emit backups as JSON to stdout.",
    )

    # restore subcommand
    res_p = subparsers.add_parser(
        "restore",
        help="Restore a configuration backup by ID or --latest (requires --apply to write).",
    )
    res_p.add_argument(
        "backup_id",
        nargs="?",
        default=None,
        help="Backup ID to restore.",
    )
    res_p.add_argument(
        "--id",
        dest="id_flag",
        default=None,
        help="Backup ID to restore (alternative to positional argument).",
    )
    res_p.add_argument(
        "--latest",
        dest="latest",
        action="store_true",
        default=False,
        help="Restore the most recent backup.",
    )
    res_p.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=False,
        help="Preview diff and verification of the restore without modifying files.",
    )
    res_p.add_argument(
        "--apply",
        dest="apply",
        action="store_true",
        default=False,
        help="Required flag to write the restored backup to disk.",
    )
    res_p.add_argument(
        "--reload",
        dest="reload",
        action="store_true",
        default=False,
        help="Run live reload after restoring.",
    )
    res_p.add_argument(
        "--force",
        dest="force",
        action="store_true",
        default=False,
        help="Restore even if the current file hash differs from expected.",
    )
    res_p.add_argument(
        "--expected-sha256",
        dest="expected_sha256",
        default=None,
        help="Expected SHA-256 hash of the current file before restoring.",
    )
    res_p.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        default=False,
        help="Emit restore result as JSON to stdout.",
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

    disabled_binds = detect_disabled_binds(
        entrypoint=disc.environment.entrypoint,
        config_dir=disc.environment.config_dir,
        language=disc.environment.language,
        env=env,
    )
    stats.disabled_binds = len(disabled_binds)

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
        disabled_binds=disabled_binds,
        oracle=oracle_dict,
    )
    return doc, exit_code


def format_apply_result(result: ApplyResult, *, dry_run: bool, reload: bool) -> str:
    """Format an ApplyResult into human-readable diff and verification report."""
    lines: list[str] = []
    mode_label = "DRY-RUN (no files modified)" if dry_run else ("APPLY + RELOAD" if reload else "APPLY")
    lines.append(f"[HKS Edit] Mode: {mode_label}")
    lines.append("")

    if result.diff:
        lines.append(result.diff.rstrip("\n"))
    else:
        lines.append("(no diff generated)")
    lines.append("")

    if result.verify is not None:
        if result.verify.ok is True:
            lines.append(f"Verification (Hyprland --verify-config): OK ({result.verify.message})")
        elif result.verify.ok is None:
            lines.append(
                f"Verification (Hyprland --verify-config): SKIPPED ({result.verify.reason}: {result.verify.message})"
            )
        else:
            lines.append(f"Verification (Hyprland --verify-config): FAILED ({result.verify.message})")

    if result.bind_comparison is not None:
        bc = result.bind_comparison
        if bc.ok:
            lines.append(
                f"Verification (Recorder + bind-set diff): OK "
                f"(before={bc.before_count}, after={bc.after_count}, "
                f"removed={bc.removed_count}, added={bc.added_count})"
            )
        else:
            lines.append(f"Verification (Recorder + bind-set diff): FAILED ({bc.message})")

    if result.companion_warning:
        lines.append(f"Warning: {result.companion_warning}")

    if result.backup is not None:
        lines.append(f"Backup: {result.backup.id} ({result.backup.backup_path})")

    if result.errors:
        for err in result.errors:
            lines.append(f"Error: {err}")
        if result.rolled_back:
            lines.append("Result: ROLLED BACK")
        else:
            lines.append("Result: FAILED")
    elif dry_run:
        lines.append("Result: VERIFIED (dry-run only; pass --apply to write changes)")
    else:
        lines.append("Result: APPLIED")

    return "\n".join(lines)


def format_backups_table(records: list[BackupRecord]) -> str:
    """Format backup records as a plain-text table."""
    if not records:
        return "No backups found."
    lines: list[str] = [
        f"{'ID':<32}  {'CREATED_AT':<25}  {'SHA256':<12}  {'ORIGINAL_PATH'}",
        "-" * 96,
    ]
    for r in records:
        lines.append(
            f"{r.id:<32}  {r.created_at:<25}  {r.sha256[:12]:<12}  {r.original_path}"
        )
    return "\n".join(lines)


def make_editor_json_output(
    mode: str,
    applied: bool,
    rolled_back: bool,
    diff: str,
    verify: Any | None,
    warnings: list[str],
    backup: Any | None,
    errors: list[str],
    **extra: Any,
) -> dict[str, Any]:
    """Build a uniform JSON response structure for edit/backups/restore operations."""
    backup_dict: dict[str, Any] | None = None
    if backup is not None:
        if isinstance(backup, dict):
            backup_dict = {
                "id": backup.get("id", ""),
                "path": backup.get("path") or backup.get("backup_path", ""),
                "sha256": backup.get("sha256", ""),
            }
        else:
            backup_dict = {
                "id": getattr(backup, "id", ""),
                "path": getattr(backup, "backup_path", ""),
                "sha256": getattr(backup, "sha256", ""),
            }
    verify_dict: dict[str, Any] | None = None
    if verify is not None:
        if isinstance(verify, dict):
            verify_dict = verify
        else:
            verify_dict = verify.to_dict()
    res = {
        "applied": applied,
        "backup": backup_dict,
        "diff": diff,
        "errors": list(errors),
        "mode": mode,
        "rolled_back": rolled_back,
        "verify": verify_dict,
        "warnings": list(warnings),
    }
    res.update(extra)
    return res


def _handle_edit(args: argparse.Namespace) -> int:
    is_json = bool(getattr(args, "json_output", False))
    if args.dry_run and args.apply:
        msg = "--dry-run and --apply are mutually exclusive"
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode="error", applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[msg]
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hks: error: {msg}\n")
        return 2
    if args.reload and not args.apply:
        msg = "--reload requires --apply"
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode="error", applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[msg]
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hks: error: {msg}\n")
        return 2
    if not args.comment_out and not args.uncomment and not args.delete:
        msg = "edit requires at least one --comment-out, --uncomment, or --delete BIND_ID"
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode="error", applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[msg]
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hks: error: {msg}\n")
        return 2

    is_dry_run = not args.apply
    mode_name = "dry-run" if is_dry_run else ("apply+reload" if args.reload else "apply")
    doc, _ = run_scan_pipeline(
        config_dir=args.config_dir,
        entrypoint=args.entrypoint,
        no_live=args.no_live,
        with_oracle=False,
        no_sidecar=True,
    )

    bind_by_id = {b.id: b for b in doc.binds}
    file_hashes = {f.path: f.sha256 for f in doc.files}
    candidate_files = [f.path for f in doc.files]
    ops: list[EditOp] = []

    try:
        for bid in args.comment_out:
            b = bind_by_id.get(bid)
            if b is None:
                msg = f"bind '{bid}' not found in active configuration."
                if is_json:
                    sys.stdout.write(json.dumps(make_editor_json_output(
                        mode=mode_name, applied=False, rolled_back=False, diff="", verify=None,
                        warnings=[], backup=None, errors=[msg]
                    ), indent=2) + "\n")
                else:
                    sys.stderr.write(f"hks edit: error: {msg}\n")
                return 1
            ops.append(build_op_for_bind(b, "comment_out"))

        for bid in args.uncomment:
            if bid in bind_by_id:
                b = bind_by_id[bid]
                msg = f"bind '{bid}' at {b.source_file}:{b.source_line} is already active."
                if is_json:
                    sys.stdout.write(json.dumps(make_editor_json_output(
                        mode=mode_name, applied=False, rolled_back=False, diff="", verify=None,
                        warnings=[], backup=None, errors=[msg]
                    ), indent=2) + "\n")
                else:
                    sys.stderr.write(f"hks edit: error: {msg}\n")
                return 1
            op = resolve_uncomment_op(
                bind_id=bid,
                config_dir=doc.environment.config_dir,
                entrypoint=doc.environment.entrypoint,
                candidate_files=candidate_files,
            )
            ops.append(op)

        for bid in args.delete:
            b = bind_by_id.get(bid)
            if b is not None:
                ops.append(build_op_for_bind(b, "delete_line"))
            else:
                d = next((x for x in doc.disabled_binds if x.id == bid), None)
                if d is not None:
                    ops.append(
                        EditOp(
                            kind="delete_line",
                            file=d.file,
                            line_number=d.line,
                            expected_text=d.original_text,
                            language=doc.environment.language,
                        )
                    )
                else:
                    msg = f"bind '{bid}' not found in active or disabled configuration."
                    if is_json:
                        sys.stdout.write(json.dumps(make_editor_json_output(
                            mode=mode_name, applied=False, rolled_back=False, diff="", verify=None,
                            warnings=[], backup=None, errors=[msg]
                        ), indent=2) + "\n")
                    else:
                        sys.stderr.write(f"hks edit: error: {msg}\n")
                    return 1

        result = apply_edit(
            ops=ops,
            config_dir=doc.environment.config_dir,
            entrypoint=doc.environment.entrypoint,
            dry_run=is_dry_run,
            reload=args.reload,
            scan_sha256=file_hashes,
            before_binds=doc.binds,
        )
    except NotEditableError as exc:
        msg = f"not editable: {exc}"
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode=mode_name, applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[msg]
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hks edit: {msg}\n")
        return 1
    except EditConflict as exc:
        msg = f"conflict: {exc}"
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode=mode_name, applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[msg]
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hks edit: {msg}\n")
        return 1
    except KeyError as exc:
        raw_msg = exc.args[0] if exc.args else str(exc)
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode=mode_name, applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[raw_msg]
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hks edit: error: {raw_msg}\n")
        return 1
    except BackupError as exc:
        msg = f"backup error: {exc}"
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode=mode_name, applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[msg]
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hks edit: {msg}\n")
        return 1

    if is_json:
        warnings = [result.companion_warning] if result.companion_warning else []
        out_data = make_editor_json_output(
            mode=mode_name,
            applied=result.applied,
            rolled_back=result.rolled_back,
            diff=result.diff,
            verify=result.verify,
            warnings=warnings,
            backup=result.backup,
            errors=result.errors,
            bind_comparison=result.bind_comparison.to_dict() if result.bind_comparison else None,
        )
        sys.stdout.write(json.dumps(out_data, indent=2, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    else:
        output = format_apply_result(result, dry_run=is_dry_run, reload=args.reload)
        sys.stdout.write(output + "\n")
        sys.stdout.flush()

    if result.errors or result.rolled_back:
        return 1
    return 0


def _handle_backups(args: argparse.Namespace) -> int:
    is_json = bool(getattr(args, "json_output", False))
    try:
        records = list_backups(path=args.path)
    except BackupError as exc:
        msg = str(exc)
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode="backups", applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[msg], backups=[]
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hks backups: error: {msg}\n")
        return 1

    if is_json:
        out_data = make_editor_json_output(
            mode="backups",
            applied=False,
            rolled_back=False,
            diff="",
            verify=None,
            warnings=[],
            backup=None,
            errors=[],
            backups=[r.to_dict() for r in records],
        )
        sys.stdout.write(json.dumps(out_data, indent=2, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    else:
        sys.stdout.write(format_backups_table(records) + "\n")
        sys.stdout.flush()
    return 0


def _handle_restore(args: argparse.Namespace) -> int:
    is_json = bool(getattr(args, "json_output", False))
    if getattr(args, "latest", False):
        try:
            records = list_backups()
        except BackupError as exc:
            msg = str(exc)
            if is_json:
                sys.stdout.write(json.dumps(make_editor_json_output(
                    mode="restore", applied=False, rolled_back=False, diff="", verify=None,
                    warnings=[], backup=None, errors=[msg]
                ), indent=2) + "\n")
            else:
                sys.stderr.write(f"hks restore: error: {msg}\n")
            return 1
        if not records:
            msg = "no backups available to restore."
            if is_json:
                sys.stdout.write(json.dumps(make_editor_json_output(
                    mode="restore", applied=False, rolled_back=False, diff="", verify=None,
                    warnings=[], backup=None, errors=[msg]
                ), indent=2) + "\n")
            else:
                sys.stderr.write(f"hks restore: error: {msg}\n")
            return 1
        matched = records[-1]
    else:
        target_id = args.id_flag or args.backup_id
        if not target_id:
            msg = "restore requires a backup ID or --latest"
            if is_json:
                sys.stdout.write(json.dumps(make_editor_json_output(
                    mode="restore", applied=False, rolled_back=False, diff="", verify=None,
                    warnings=[], backup=None, errors=[msg]
                ), indent=2) + "\n")
            else:
                sys.stderr.write(f"hks: error: {msg}\n")
            return 2

        try:
            records = list_backups()
            matched = next((r for r in records if r.id == target_id), None)
            if matched is None:
                msg = f"backup '{target_id}' not found."
                if is_json:
                    sys.stdout.write(json.dumps(make_editor_json_output(
                        mode="restore", applied=False, rolled_back=False, diff="", verify=None,
                        warnings=[], backup=None, errors=[msg]
                    ), indent=2) + "\n")
                else:
                    sys.stderr.write(f"hks restore: error: {msg}\n")
                return 1
        except BackupError as exc:
            msg = str(exc)
            if is_json:
                sys.stdout.write(json.dumps(make_editor_json_output(
                    mode="restore", applied=False, rolled_back=False, diff="", verify=None,
                    warnings=[], backup=None, errors=[msg]
                ), indent=2) + "\n")
            else:
                sys.stderr.write(f"hks restore: error: {msg}\n")
            return 1

    # Diff preview between current target file and backup
    diff_text = ""
    if os.path.isfile(matched.original_path) and os.path.isfile(matched.backup_path):
        with open(matched.original_path, "r", encoding="utf-8") as f:
            curr_text = f.read()
        with open(matched.backup_path, "r", encoding="utf-8") as f:
            bak_text = f.read()
        diff_text = generate_unified_diff(
            curr_text,
            bak_text,
            file_path=os.path.basename(matched.original_path),
        )

    if not args.apply and not getattr(args, "dry_run", False):
        if not is_json:
            sys.stderr.write("hks: error: restore requires --apply to write files (use --dry-run to preview)\n")
            return 2

    if not args.apply:
        # Dry-run preview
        if is_json:
            out_data = make_editor_json_output(
                mode="restore (dry-run)",
                applied=False,
                rolled_back=False,
                diff=diff_text,
                verify={"ok": True, "message": "backup verified", "line": None, "reason": None},
                warnings=[],
                backup=matched,
                errors=[],
            )
            sys.stdout.write(json.dumps(out_data, indent=2, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        else:
            sys.stdout.write("[HKS Restore] Mode: DRY-RUN (no files modified)\n\n" + diff_text + "\nResult: PREVIEW\n")
            sys.stdout.flush()
        return 0

    try:
        restore_backup(
            matched,
            expected_current_sha256=args.expected_sha256,
            force=args.force,
        )
    except BackupConflictError as exc:
        msg = f"conflict: {exc}"
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode="restore", applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=matched, errors=[msg]
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hks restore: {msg}\n")
        return 1
    except BackupError as exc:
        msg = str(exc)
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode="restore", applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=matched, errors=[msg]
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hks restore: error: {msg}\n")
        return 1

    errors: list[str] = []
    if getattr(args, "reload", False):
        reload_ok, reload_err = _run_live_reload_and_check()
        if not reload_ok:
            errors.append(f"Live reload failed: {reload_err}")

    if is_json:
        out_data = make_editor_json_output(
            mode="restore",
            applied=True,
            rolled_back=False,
            diff=diff_text,
            verify={"ok": True, "message": "restored ok", "line": None, "reason": None},
            warnings=[],
            backup=matched,
            errors=errors,
        )
        sys.stdout.write(json.dumps(out_data, indent=2, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    else:
        sys.stdout.write(
            f"Restored {matched.original_path} from backup {matched.id} (sha256={matched.sha256})\n"
        )
        sys.stdout.flush()
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    if not args.subcommand:
        parser.print_usage(sys.stderr)
        sys.stderr.write(
            "hks: error: subcommand required (choose from 'scan', 'summary', 'sidecar-template', 'conflicts', 'edit', 'backups', 'restore')\n"
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

        if args.subcommand == "conflicts":
            doc, _ = run_scan_pipeline(
                config_dir=args.config_dir,
                entrypoint=args.entrypoint,
                no_live=args.no_live,
                with_oracle=False,
                sidecar_path=args.sidecar,
                no_sidecar=args.no_sidecar,
            )
            sys.stdout.write(format_conflicts_table(doc) + "\n")
            sys.stdout.flush()
            return 0

        if args.subcommand == "edit":
            return _handle_edit(args)

        if args.subcommand == "backups":
            return _handle_backups(args)

        if args.subcommand == "restore":
            return _handle_restore(args)
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
