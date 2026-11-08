"""CLI entrypoint for Hyprland Keybind Studio (HKS) Phase 1."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from backend.conflicts import check_candidate_conflict, detect_conflicts
from backend.describe import (
    SidecarCollisionError,
    SidecarStoreError,
    backup_sidecar_file,
    build_sidecar_template,
    delete_override,
    list_orphans,
    load_and_apply_sidecar,
    migrate_override,
    resolve_sidecar_path,
    save_override,
)
from backend.describe.sidecar_store import _read_sidecar_raw, matches_equal
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
    enter_submap,
    generate_unified_diff,
    get_catalog,
    heal_submap,
    leave_submap,
    list_backups,
    render_from_catalog,
    resolve_insert_op,
    resolve_replace_op,
    resolve_uncomment_op,
    restore_backup,
    submap_status,
)
from backend.editor.apply import _run_live_reload_and_check
from backend.editor.backups import create_backup, resolve_backup_dir
from backend.models.types import (
    VALID_CATEGORIES,
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

    conf_sub = conf_p.add_subparsers(dest="conflicts_action", required=False)
    chk_p = conf_sub.add_parser(
        "check",
        help="Fast pre-flight check of candidate shortcut against active configuration.",
    )
    chk_p.add_argument(
        "--mods",
        dest="mods",
        required=True,
        help="Candidate modifiers (e.g. 'SUPER', 'SUPER+SHIFT', or bitmask number).",
    )
    chk_p.add_argument(
        "--key",
        dest="key",
        required=True,
        help="Candidate key (e.g. 'Return', 'Q', 'grave').",
    )
    chk_p.add_argument(
        "--submap",
        dest="submap",
        default="",
        help="Candidate submap name.",
    )
    chk_p.add_argument(
        "--exclude-id",
        dest="exclude_id",
        default=None,
        help="Bind ID to exclude (the bind being replaced).",
    )
    chk_p.add_argument(
        "--config-dir",
        dest="config_dir",
        default=None,
        help="Override Hyprland config dir.",
    )
    chk_p.add_argument(
        "--entrypoint",
        dest="entrypoint",
        default=None,
        help="Override entrypoint file.",
    )
    chk_p.add_argument(
        "--no-live",
        dest="no_live",
        action="store_true",
        help="Disable optional live hyprctl probing during discovery.",
    )
    chk_p.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        default=True,
        help="Emit JSON output.",
    )

    # dispatchers subcommand
    disp_p = subparsers.add_parser(
        "dispatchers",
        help="List data-driven dispatcher catalog.",
    )
    disp_p.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        default=True,
        help="Emit JSON output.",
    )

    # categories subcommand
    cat_p = subparsers.add_parser(
        "categories",
        help="List valid categories for sidecar descriptions.",
    )
    cat_p.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        default=False,
        help="Emit JSON output.",
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
        "--sidecar",
        dest="sidecar",
        default=None,
        help="Explicit path to a sidecar descriptions.json override file.",
    )
    edit_p.add_argument(
        "--id",
        dest="id",
        default=None,
        help="Bind ID for description/category modification.",
    )
    edit_p.add_argument(
        "--desc",
        "--description",
        dest="description",
        default=None,
        help="Custom description (max 200 chars).",
    )
    edit_p.add_argument(
        "--cat",
        "--category",
        dest="category",
        default=None,
        help="Category name.",
    )
    edit_p.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        default=False,
        help="Emit result as JSON to stdout.",
    )

    edit_sub = edit_p.add_subparsers(dest="edit_action", required=False)

    # edit replace subcommand
    rep_p = edit_sub.add_parser("replace", help="Replace an existing keybinding line.")
    rep_p.add_argument("--id", dest="id", required=True, help="Target bind ID to replace.")
    rep_p.add_argument("--mods", dest="mods", required=True, help="New modifiers (e.g. 'SUPER', 'SUPER+SHIFT').")
    rep_p.add_argument("--key", dest="key", required=True, help="New key (e.g. 'Return', 'Q').")
    rep_p.add_argument("--dispatcher", dest="dispatcher", default=None, help="New dispatcher (e.g. 'exec_cmd', 'window.close').")
    rep_p.add_argument("--args", dest="args", default=None, help="New dispatcher arguments.")
    rep_p.add_argument("--dispatcher-id", dest="dispatcher_id", default=None, help="Catalog dispatcher ID.")
    rep_p.add_argument("--args-json", dest="args_json", default=None, help="JSON arguments for catalog dispatcher.")
    rep_p.add_argument("--preserve-dispatcher", dest="preserve_dispatcher", action="store_true", default=False, help="Preserve original dispatcher call expression verbatim.")
    rep_p.add_argument("--sidecar", dest="sidecar", default=None, help="Explicit path to sidecar descriptions.json.")
    rep_p.add_argument("--desc", "--description", dest="description", default=None, help="Custom description.")
    rep_p.add_argument("--cat", "--category", dest="category", default=None, help="Category name.")
    rep_p.add_argument("--config-dir", dest="config_dir", default=None, help="Override Hyprland config dir.")
    rep_p.add_argument("--entrypoint", dest="entrypoint", default=None, help="Override entrypoint file.")
    rep_p.add_argument("--no-live", dest="no_live", action="store_true", help="Disable live hyprctl probing.")
    rep_p.add_argument("--dry-run", dest="dry_run", action="store_true", default=False, help="Preview only.")
    rep_p.add_argument("--apply", dest="apply", action="store_true", default=False, help="Apply edit to disk.")
    rep_p.add_argument("--reload", dest="reload", action="store_true", default=False, help="Reload Hyprland.")
    rep_p.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    # edit add subcommand
    add_p = edit_sub.add_parser("add", help="Add a new keybinding line.")
    add_p.add_argument("--mods", dest="mods", default="", help="Modifiers (e.g. 'SUPER', 'SUPER+SHIFT').")
    add_p.add_argument("--key", dest="key", required=True, help="Key (e.g. 'Return', 'Q').")
    add_p.add_argument("--dispatcher", dest="dispatcher", default=None, help="Dispatcher (e.g. 'exec_cmd', 'window.close').")
    add_p.add_argument("--args", dest="args", default=None, help="Dispatcher arguments.")
    add_p.add_argument("--flags", dest="flags", default="", help="Comma-separated flags (e.g. 'locked,repeating').")
    add_p.add_argument("--submap", dest="submap", default="", help="Candidate submap name.")
    add_p.add_argument("--dispatcher-id", dest="dispatcher_id", default=None, help="Catalog dispatcher ID.")
    add_p.add_argument("--args-json", dest="args_json", default=None, help="JSON-encoded argument object.")
    add_p.add_argument("--force", dest="force", action="store_true", default=False, help="Force addition despite conflicts/duplicates.")
    add_p.add_argument("--sidecar", dest="sidecar", default=None, help="Explicit path to sidecar descriptions.json.")
    add_p.add_argument("--desc", "--description", dest="description", default=None, help="Custom description.")
    add_p.add_argument("--cat", "--category", dest="category", default=None, help="Category name.")
    add_p.add_argument("--prefer-mainmod", dest="prefer_mainmod", action="store_true", default=False, help="Prefer mainMod .. '+' when adding bind with SUPER.")
    add_p.add_argument("--config-dir", dest="config_dir", default=None, help="Override Hyprland config dir.")
    add_p.add_argument("--entrypoint", dest="entrypoint", default=None, help="Override entrypoint file.")
    add_p.add_argument("--no-live", dest="no_live", action="store_true", help="Disable live hyprctl probing.")
    add_p.add_argument("--dry-run", dest="dry_run", action="store_true", default=False, help="Preview only.")
    add_p.add_argument("--apply", dest="apply", action="store_true", default=False, help="Apply edit to disk.")
    add_p.add_argument("--reload", dest="reload", action="store_true", default=False, help="Reload Hyprland.")
    add_p.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

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

    # recorder subcommand
    rec_p = subparsers.add_parser(
        "recorder",
        help="Manage Hyprland recorder submap for key interception.",
    )
    rec_sub = rec_p.add_subparsers(dest="recorder_action", required=True)

    rec_enter = rec_sub.add_parser("enter", help="Enter the recorder submap.")
    rec_enter.add_argument("--language", dest="language", default="lua", choices=["lua", "hyprlang"])
    rec_enter.add_argument("--submap", dest="submap", default="hks_record")
    rec_enter.add_argument("--json", dest="json_output", action="store_true", default=False)

    rec_leave = rec_sub.add_parser("leave", help="Leave the recorder submap.")
    rec_leave.add_argument("--language", dest="language", default="lua", choices=["lua", "hyprlang"])
    rec_leave.add_argument("--json", dest="json_output", action="store_true", default=False)

    rec_status = rec_sub.add_parser("status", help="Get current active submap.")
    rec_status.add_argument("--json", dest="json_output", action="store_true", default=False)

    rec_heal = rec_sub.add_parser("heal", help="Reset submap if currently stuck in recorder submap.")
    rec_heal.add_argument("--language", dest="language", default="lua", choices=["lua", "hyprlang"])
    rec_heal.add_argument("--submap", dest="submap", default="hks_record")
    rec_heal.add_argument("--json", dest="json_output", action="store_true", default=False)

    # sidecar subcommand
    sc_p = subparsers.add_parser(
        "sidecar",
        help="Manage sidecar descriptions and categories.",
    )
    sc_p.add_argument("--sidecar", dest="sidecar", default=None, help="Explicit path to sidecar descriptions.json.")
    sc_p.add_argument("--config-dir", dest="config_dir", default=None, help="Override Hyprland config dir.")
    sc_p.add_argument("--entrypoint", dest="entrypoint", default=None, help="Override entrypoint file.")
    sc_p.add_argument("--no-live", dest="no_live", action="store_true", default=False, help="Disable live hyprctl probing.")
    sc_p.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    sc_sub = sc_p.add_subparsers(dest="sidecar_action", required=False)

    def _add_common_sc_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--sidecar", dest="sidecar", default=None, help="Explicit path to sidecar descriptions.json.")
        p.add_argument("--config-dir", dest="config_dir", default=None, help="Override Hyprland config dir.")
        p.add_argument("--entrypoint", dest="entrypoint", default=None, help="Override entrypoint file.")
        p.add_argument("--no-live", dest="no_live", action="store_true", default=False, help="Disable live hyprctl probing.")
        p.add_argument("--json", dest="json_output", action="store_true", default=False)

    sc_list = sc_sub.add_parser("list", help="List sidecar overrides or orphans.")
    sc_list.add_argument("--orphans", dest="orphans", action="store_true", default=False, help="List only orphan overrides.")
    _add_common_sc_args(sc_list)

    sc_get = sc_sub.add_parser("get", help="Get sidecar override for a bind ID.")
    sc_get.add_argument("--id", dest="id", required=True, help="Target bind ID.")
    _add_common_sc_args(sc_get)

    sc_set = sc_sub.add_parser("set", help="Set sidecar override for a bind ID.")
    sc_set.add_argument("--id", dest="id", required=True, help="Target bind ID.")
    sc_set.add_argument("--desc", "--description", dest="description", default=None, help="Custom description.")
    sc_set.add_argument("--cat", "--category", dest="category", default=None, help="Category name.")
    _add_common_sc_args(sc_set)

    sc_clear = sc_sub.add_parser("clear", help="Clear sidecar override for a bind ID or match.")
    sc_clear.add_argument("--id", dest="id", default=None, help="Target bind ID.")
    sc_clear.add_argument("--mods", dest="mods", default=None, help="Modifier tokens (e.g. 'SUPER').")
    sc_clear.add_argument("--key", dest="key", default=None, help="Key string.")
    sc_clear.add_argument("--submap", dest="submap", default="", help="Submap name.")
    sc_clear.add_argument("--dispatcher", dest="dispatcher", default=None, help="Optional dispatcher filter.")
    _add_common_sc_args(sc_clear)

    sc_mig = sc_sub.add_parser("migrate", help="Migrate sidecar override from old bind ID to new bind ID.")
    sc_mig.add_argument("--old-id", dest="old_id", required=True, help="Old bind ID.")
    sc_mig.add_argument("--new-id", dest="new_id", required=True, help="New bind ID.")
    _add_common_sc_args(sc_mig)

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

    disabled_binds = detect_disabled_binds(
        entrypoint=disc.environment.entrypoint,
        config_dir=disc.environment.config_dir,
        language=disc.environment.language,
        env=env,
    )
    stats.disabled_binds = len(disabled_binds)

    sidecar_stats, sidecar_diags = load_and_apply_sidecar(
        binds=binds,
        disabled_binds=disabled_binds,
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


def format_match_combo(match: dict[str, Any] | None) -> str:
    """Format a match dictionary into human-readable shortcut string."""
    if not match:
        return "bind"
    mods = match.get("modifiers") or []
    key = match.get("key") or ""
    submap = match.get("submap") or ""
    parts = list(mods) + ([key] if key else [])
    combo = " + ".join(parts) if parts else key
    if submap:
        return f"{combo} (submap: {submap})"
    return combo


def _resolve_bind_match(doc: ScanDocument, bind_id: str) -> dict[str, Any] | None:
    for b in doc.binds:
        if b.id == bind_id:
            return {
                "modifiers": list(b.modifiers),
                "key": b.key,
                "submap": b.submap or "",
                "dispatcher": b.dispatcher.path if b.dispatcher else None,
            }
    for d in doc.disabled_binds:
        if d.id == bind_id:
            hint = getattr(d, "key_hint", "") or getattr(d, "original_text", "")
            for pfx in ("-- HKS-DISABLED:", "# HKS-DISABLED:", "--", "#"):
                if hint.startswith(pfx):
                    hint = hint[len(pfx):].strip()
            tokens = [t.strip() for t in re.split(r"[,+\s]+", hint) if t.strip()]
            if tokens:
                parsed = resolve_modifier_tokens(tokens[:-1])
                return {
                    "modifiers": list(parsed.modifiers),
                    "key": tokens[-1],
                    "submap": "",
                    "dispatcher": None,
                }
    return None


def _handle_categories(args: argparse.Namespace) -> int:
    is_json = bool(getattr(args, "json_output", False))
    cats = list(VALID_CATEGORIES)
    if is_json:
        sys.stdout.write(json.dumps(cats, indent=2) + "\n")
    else:
        for c in cats:
            sys.stdout.write(f"{c}\n")
    sys.stdout.flush()
    return 0


def _handle_sidecar(args: argparse.Namespace) -> int:
    is_json = bool(getattr(args, "json_output", False))
    action = getattr(args, "sidecar_action", "list")
    sidecar_path = resolve_sidecar_path(cli_path=getattr(args, "sidecar", None))
    if not sidecar_path:
        msg = "No sidecar path could be resolved."
        if is_json:
            sys.stdout.write(json.dumps({"error": msg}, indent=2) + "\n")
        else:
            sys.stderr.write(f"hks sidecar: error: {msg}\n")
        return 1

    try:
        if action == "list":
            if getattr(args, "orphans", False):
                doc, _ = run_scan_pipeline(
                    config_dir=getattr(args, "config_dir", None),
                    entrypoint=getattr(args, "entrypoint", None),
                    no_live=getattr(args, "no_live", False),
                    with_oracle=False,
                    no_sidecar=True,
                )
                orphans = list_orphans(sidecar_path, doc.binds, doc.disabled_binds)
                out = {"path": sidecar_path, "orphans": orphans, "count": len(orphans)}
            else:
                raw_data = _read_sidecar_raw(sidecar_path)
                overrides = raw_data.get("overrides", [])
                out = {"path": sidecar_path, "overrides": overrides, "count": len(overrides)}

            if is_json:
                sys.stdout.write(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
            else:
                sys.stdout.write(f"Sidecar: {sidecar_path}\nTotal: {out['count']}\n")
            sys.stdout.flush()
            return 0

        # Actions get, set, clear, migrate require scanning binds to resolve IDs
        doc, _ = run_scan_pipeline(
            config_dir=getattr(args, "config_dir", None),
            entrypoint=getattr(args, "entrypoint", None),
            no_live=getattr(args, "no_live", False),
            with_oracle=False,
            no_sidecar=True,
        )

        if action == "get":
            match = _resolve_bind_match(doc, args.id)
            if match is None:
                msg = f"Bind '{args.id}' not found in active or disabled configuration."
                if is_json:
                    sys.stdout.write(json.dumps({"found": False, "error": msg}, indent=2) + "\n")
                else:
                    sys.stderr.write(f"hks sidecar: {msg}\n")
                return 1

            raw_data = _read_sidecar_raw(sidecar_path)
            found_ov = None
            for ov in raw_data.get("overrides", []):
                if isinstance(ov.get("match"), dict) and matches_equal(ov["match"], match):
                    found_ov = ov
                    break

            out = {"found": bool(found_ov), "match": match, "override": found_ov, "id": args.id}
            if is_json:
                sys.stdout.write(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
            else:
                if found_ov:
                    sys.stdout.write(f"Override: {found_ov}\n")
                else:
                    sys.stdout.write("No custom override found.\n")
            sys.stdout.flush()
            return 0

        elif action == "set":
            match = _resolve_bind_match(doc, args.id)
            if match is None:
                msg = f"Bind '{args.id}' not found in active or disabled configuration."
                if is_json:
                    sys.stdout.write(json.dumps({"error": msg}, indent=2) + "\n")
                else:
                    sys.stderr.write(f"hks sidecar: {msg}\n")
                return 1

            if not os.path.isfile(sidecar_path):
                os.makedirs(os.path.dirname(os.path.abspath(sidecar_path)), exist_ok=True)
                with open(sidecar_path, "w", encoding="utf-8") as f:
                    f.write("{\n  \"version\": 1,\n  \"overrides\": []\n}\n")

            b_rec = create_backup(sidecar_path, backup_dir=resolve_backup_dir(), config_dir=getattr(args, "config_dir", None))

            res = save_override(
                sidecar_path,
                match,
                description=getattr(args, "description", None),
                category=getattr(args, "category", None),
            )
            res["backup"] = b_rec.to_dict()
            res["id"] = args.id
            if is_json:
                sys.stdout.write(json.dumps(res, indent=2, ensure_ascii=False) + "\n")
            else:
                sys.stdout.write(f"Saved override for {args.id} (backup: {b_rec.id})\n")
            sys.stdout.flush()
            return 0

        elif action == "clear":
            match = None
            if getattr(args, "id", None):
                match = _resolve_bind_match(doc, args.id)
                if match is None:
                    msg = f"Bind '{args.id}' not found in active or disabled configuration."
                    if is_json:
                        sys.stdout.write(json.dumps({"error": msg}, indent=2) + "\n")
                    else:
                        sys.stderr.write(f"hks sidecar: {msg}\n")
                    return 1
            elif getattr(args, "key", None):
                raw_mods = getattr(args, "mods", "") or ""
                toks = [t.strip() for t in re.split(r"[,+\s]+", raw_mods) if t.strip()]
                match = {
                    "modifiers": toks,
                    "key": getattr(args, "key"),
                    "submap": getattr(args, "submap", "") or "",
                }
                if getattr(args, "dispatcher", None):
                    match["dispatcher"] = getattr(args, "dispatcher")
            else:
                msg = "Either --id or --key is required to clear an override."
                if is_json:
                    sys.stdout.write(json.dumps({"error": msg}, indent=2) + "\n")
                else:
                    sys.stderr.write(f"hks sidecar: {msg}\n")
                return 1

            b_rec = None
            if os.path.isfile(sidecar_path):
                b_rec = create_backup(sidecar_path, backup_dir=resolve_backup_dir(), config_dir=getattr(args, "config_dir", None))

            res = delete_override(sidecar_path, match)
            if b_rec is not None:
                res["backup"] = b_rec.to_dict()
            if getattr(args, "id", None):
                res["id"] = args.id
            if is_json:
                sys.stdout.write(json.dumps(res, indent=2, ensure_ascii=False) + "\n")
            else:
                bak_msg = f" (backup: {b_rec.id})" if b_rec else ""
                sys.stdout.write(f"Cleared override{bak_msg}\n")
            sys.stdout.flush()
            return 0

        elif action == "migrate":
            old_match = _resolve_bind_match(doc, args.old_id)
            new_match = _resolve_bind_match(doc, args.new_id)
            if old_match is None:
                msg = f"Old bind '{args.old_id}' not found."
                if is_json:
                    sys.stdout.write(json.dumps({"error": msg}, indent=2) + "\n")
                else:
                    sys.stderr.write(f"hks sidecar: {msg}\n")
                return 1
            if new_match is None:
                msg = f"New bind '{args.new_id}' not found."
                if is_json:
                    sys.stdout.write(json.dumps({"error": msg}, indent=2) + "\n")
                else:
                    sys.stderr.write(f"hks sidecar: {msg}\n")
                return 1

            b_rec = None
            if os.path.isfile(sidecar_path):
                b_rec = create_backup(sidecar_path, backup_dir=resolve_backup_dir(), config_dir=getattr(args, "config_dir", None))

            res = migrate_override(sidecar_path, old_match, new_match)
            if b_rec is not None:
                res["backup"] = b_rec.to_dict()
            if is_json:
                sys.stdout.write(json.dumps(res, indent=2, ensure_ascii=False) + "\n")
            else:
                if res.get("migrated"):
                    sys.stdout.write(f"Migrated override from {args.old_id} to {args.new_id}\n")
                elif res.get("collision"):
                    sys.stderr.write(f"Collision migrating override: target already has override\n")
                else:
                    sys.stderr.write(f"Override for {args.old_id} not found\n")
            sys.stdout.flush()
            return 0 if (res.get("migrated") or not res.get("collision")) else 1

        else:
            sys.stderr.write(f"hks sidecar: unknown action '{action}'\n")
            return 2
    except SidecarStoreError as exc:
        if is_json:
            sys.stdout.write(json.dumps({"error": str(exc)}, indent=2) + "\n")
        else:
            sys.stderr.write(f"hks sidecar: error: {exc}\n")
        return 1
    except Exception as exc:
        if is_json:
            sys.stdout.write(json.dumps({"error": str(exc)}, indent=2) + "\n")
        else:
            sys.stderr.write(f"hks sidecar: error: {exc}\n")
        return 1


def _handle_edit(args: argparse.Namespace) -> int:
    is_json = bool(getattr(args, "json_output", False))
    edit_action = getattr(args, "edit_action", None)

    if getattr(args, "dry_run", False) and getattr(args, "apply", False):
        msg = "--dry-run and --apply are mutually exclusive"
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode="error", applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[msg]
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hks: error: {msg}\n")
        return 2

    if getattr(args, "reload", False) and not getattr(args, "apply", False):
        msg = "--reload requires --apply"
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode="error", applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[msg]
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hks: error: {msg}\n")
        return 2

    desc_only = (
        edit_action is None
        and getattr(args, "id", None) is not None
        and (getattr(args, "description", None) is not None or getattr(args, "category", None) is not None)
        and not getattr(args, "comment_out", None)
        and not getattr(args, "uncomment", None)
        and not getattr(args, "delete", None)
    )

    if not desc_only and edit_action is None and not getattr(args, "comment_out", None) and not getattr(args, "uncomment", None) and not getattr(args, "delete", None):
        msg = "edit requires at least one --comment-out, --uncomment, or --delete BIND_ID (or 'replace', 'add' subcommand, or --id with --description/--category)"
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode="error", applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[msg]
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hks: error: {msg}\n")
        return 2

    is_dry_run = not getattr(args, "apply", False)
    reload_requested = bool(getattr(args, "reload", False))

    if edit_action == "replace":
        mode_name = "replace (dry-run)" if is_dry_run else ("replace (apply+reload)" if reload_requested else "replace (apply)")
    elif edit_action == "add":
        mode_name = "add (dry-run)" if is_dry_run else ("add (apply+reload)" if reload_requested else "add (apply)")
    else:
        mode_name = "dry-run" if is_dry_run else ("apply+reload" if reload_requested else "apply")

    doc, _ = run_scan_pipeline(
        config_dir=getattr(args, "config_dir", None),
        entrypoint=getattr(args, "entrypoint", None),
        no_live=getattr(args, "no_live", False),
        with_oracle=False,
        no_sidecar=True,
    )

    if desc_only:
        sidecar_path = resolve_sidecar_path(cli_path=getattr(args, "sidecar", None))
        match = _resolve_bind_match(doc, args.id)
        if match is None:
            msg = f"bind '{args.id}' not found in active or disabled configuration."
            if is_json:
                sys.stdout.write(json.dumps(make_editor_json_output(
                    mode="describe (error)", applied=False, rolled_back=False, diff="", verify=None,
                    warnings=[], backup=None, errors=[msg], config_unchanged=True,
                ), indent=2) + "\n")
            else:
                sys.stderr.write(f"hks edit: error: {msg}\n")
            return 1

        if is_dry_run:
            preview_res = {
                "id": args.id,
                "match": match,
                "description": getattr(args, "description", None),
                "category": getattr(args, "category", None),
            }
            if is_json:
                sys.stdout.write(json.dumps(make_editor_json_output(
                    mode="describe (dry-run)", applied=False, rolled_back=False, diff="", verify=None,
                    warnings=[], backup=None, errors=[], config_unchanged=True, sidecar_preview=preview_res,
                ), indent=2) + "\n")
            else:
                sys.stdout.write(f"Dry-run sidecar update for {args.id}: {preview_res}\n")
            sys.stdout.flush()
            return 0
        else:
            if not os.path.isfile(sidecar_path):
                os.makedirs(os.path.dirname(os.path.abspath(sidecar_path)), exist_ok=True)
                with open(sidecar_path, "w", encoding="utf-8") as f:
                    f.write("{\n  \"version\": 1,\n  \"overrides\": []\n}\n")
            b_rec = create_backup(sidecar_path, backup_dir=resolve_backup_dir(), config_dir=getattr(args, "config_dir", None))
            res = save_override(
                sidecar_path,
                match,
                description=getattr(args, "description", None),
                category=getattr(args, "category", None),
            )
            if is_json:
                sys.stdout.write(json.dumps(make_editor_json_output(
                    mode="describe (apply)", applied=True, rolled_back=False, diff="", verify=None,
                    warnings=[], backup=b_rec.to_dict(), errors=[], config_unchanged=True, sidecar=res,
                ), indent=2) + "\n")
            else:
                sys.stdout.write(f"Applied sidecar update for {args.id} (backup: {b_rec.id})\n")
            sys.stdout.flush()
            return 0

    bind_by_id = {b.id: b for b in doc.binds}
    file_hashes = {f.path: f.sha256 for f in doc.files}
    candidate_files = [f.path for f in doc.files]
    ops: list[EditOp] = []
    op_kind: str | None = None
    expected_new_bind = None
    anchor_created = False
    plan = None
    conflicts: list[dict[str, Any]] = []
    has_conflicts = False
    disabled_held = False
    disabled_binds_matched: list[dict[str, Any]] = []

    sidecar_path = resolve_sidecar_path(cli_path=getattr(args, "sidecar", None))
    sidecar_migration_info: dict[str, Any] | None = None
    sidecar_override_found = False
    old_match: dict[str, Any] | None = None
    new_match: dict[str, Any] | None = None

    sidecar_warning: dict[str, Any] | None = None

    def get_extra_fields() -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if sidecar_warning is not None:
            fields["sidecar_warning"] = sidecar_warning
        if edit_action == "replace" and sidecar_migration_info is not None:
            fields["sidecar_migration"] = sidecar_migration_info
            return fields
        if edit_action == "add":
            fields.update({
                "file_to_modify": plan.file if plan else doc.environment.entrypoint,
                "anchor_created": plan.anchor_created if plan else False,
                "insert_line": plan.line_number if plan else None,
                "expected_new_bind": expected_new_bind.to_dict() if expected_new_bind else None,
                "conflicts": conflicts,
                "has_conflicts": has_conflicts,
                "disabled_held": disabled_held,
                "disabled_binds": disabled_binds_matched,
            })
            if getattr(args, "description", None) or getattr(args, "category", None):
                fields["sidecar_addition"] = {
                    "description": getattr(args, "description", None),
                    "category": getattr(args, "category", None),
                }
            return fields
        return fields

    try:
        if edit_action == "replace":
            op_kind = "replace"
            target_b = next((b for b in doc.binds if b.id == args.id), None)
            new_dsp = getattr(args, "dispatcher", None)
            new_args = getattr(args, "args", None)

            if getattr(args, "dispatcher_id", None):
                rendered_dsp, rendered_args = render_from_catalog(
                    dispatcher_id=args.dispatcher_id,
                    args=getattr(args, "args_json", None) or new_args,
                    language=doc.environment.language,
                )
                new_dsp = rendered_dsp
                new_args = rendered_args

            preserve_dsp = bool(getattr(args, "preserve_dispatcher", False))

            op, target_b, expected_new = resolve_replace_op(
                bind_id=args.id,
                new_mods=args.mods,
                new_key=args.key,
                new_dispatcher=new_dsp,
                new_args=new_args,
                binds=doc.binds,
                preserve_dispatcher=preserve_dsp,
            )
            ops.append(op)
            expected_new_bind = expected_new

            old_match = {
                "modifiers": list(target_b.modifiers),
                "key": target_b.key,
                "submap": target_b.submap or "",
                "dispatcher": target_b.dispatcher.path if target_b.dispatcher else None,
            }
            new_match = {
                "modifiers": list(expected_new.modifiers),
                "key": expected_new.key,
                "submap": expected_new.submap or "",
                "dispatcher": expected_new.dispatcher.path if expected_new and expected_new.dispatcher else None,
            }
            sidecar_collision = False
            if sidecar_path and os.path.isfile(sidecar_path):
                try:
                    sc_data = _read_sidecar_raw(sidecar_path)
                    for ov in sc_data.get("overrides", []):
                        if isinstance(ov.get("match"), dict) and matches_equal(ov["match"], old_match):
                            sidecar_override_found = True
                            break
                    if sidecar_override_found:
                        for ov in sc_data.get("overrides", []):
                            if isinstance(ov.get("match"), dict) and matches_equal(ov["match"], new_match):
                                sidecar_collision = True
                                break
                except Exception:
                    pass

            sidecar_migration_info = {
                "from": old_match,
                "to": new_match,
                "has_override": sidecar_override_found,
                "collision": sidecar_collision,
            }

        elif edit_action == "add":
            op_kind = "insert"
            new_dsp = getattr(args, "dispatcher", None)
            new_args = getattr(args, "args", None)

            if getattr(args, "dispatcher_id", None):
                rendered_dsp, rendered_args = render_from_catalog(
                    dispatcher_id=args.dispatcher_id,
                    args=getattr(args, "args_json", None) or new_args,
                    language=doc.environment.language,
                )
                new_dsp = rendered_dsp
                new_args = rendered_args
            elif not new_dsp:
                raise ValueError("edit add requires --dispatcher or --dispatcher-id")

            # Parse flags
            raw_flags = getattr(args, "flags", "") or ""
            parsed_flags: dict[str, bool] = {}
            if raw_flags:
                ALLOWED_FLAGS = {
                    "locked", "repeating", "mouse", "release",
                    "non_consuming", "transparent", "ignore_mods", "long_press"
                }
                for tok in (t.strip().lower() for t in raw_flags.split(",") if t.strip()):
                    if tok == "repeat":
                        tok = "repeating"
                    if tok not in ALLOWED_FLAGS:
                        raise ValueError(f"Unknown flag '{tok}'. Allowed flags: {', '.join(sorted(ALLOWED_FLAGS))}")
                    parsed_flags[tok] = True

            target_submap = getattr(args, "submap", "") or ""

            # Conflict pre-check on ADD
            conflict_result = check_candidate_conflict(
                binds=doc.binds,
                mods=args.mods,
                key=args.key,
                submap=target_submap,
                disabled_binds=doc.disabled_binds,
            )
            conflicts = conflict_result.get("conflicts", [])
            disabled_held = conflict_result.get("disabled_held", False)
            disabled_binds_matched = conflict_result.get("disabled_binds", [])
            has_conflicts = bool(conflicts or disabled_held)

            if not getattr(args, "force", False) and not is_dry_run:
                if conflicts:
                    raise EditConflict(
                        f"Candidate keybind matches active bind(s): {', '.join(c['id'] for c in conflicts)}. Use --force to proceed anyway."
                    )
                if disabled_held:
                    raise EditConflict(
                        f"Candidate keybind matches disabled bind(s): {', '.join(d['id'] for d in disabled_binds_matched)}. Re-enable or use --force to proceed."
                    )

            op, plan, expected_new = resolve_insert_op(
                file_path=doc.environment.entrypoint,
                language=doc.environment.language,
                mods=args.mods,
                key=args.key,
                dispatcher=new_dsp,
                args=new_args,
                flags=parsed_flags,
                submap=target_submap,
                all_files=[f.path for f in doc.files],
                prefer_mainmod=bool(getattr(args, "prefer_mainmod", False)),
            )
            ops.append(op)
            expected_new_bind = expected_new
            anchor_created = plan.anchor_created

        else:
            for bid in getattr(args, "comment_out", []):
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

            for bid in getattr(args, "uncomment", []):
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

            for bid in getattr(args, "delete", []):
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
            reload=reload_requested,
            scan_sha256=file_hashes,
            before_binds=doc.binds,
            op_kind=op_kind,
            expected_new_bind=expected_new_bind,
            anchor_created=anchor_created,
            sidecar_path=sidecar_path,
        )

        if is_dry_run and edit_action == "replace" and sidecar_override_found and sidecar_collision:
            sidecar_warning = {
                "code": "collision",
                "message": f"Custom description cannot be migrated: destination shortcut ({format_match_combo(new_match)}) already has a custom override. The previous description will be preserved on the old shortcut.",
                "old_match": old_match,
                "new_match": new_match,
                "orphaned_old": True,
            }

        if edit_action == "replace" and result.applied and not result.rolled_back:
            if sidecar_override_found and sidecar_path and old_match and new_match:
                try:
                    mig_res = migrate_override(sidecar_path, old_match, new_match)
                    if mig_res.get("collision"):
                        sidecar_warning = {
                            "code": "collision",
                            "message": f"Custom description could not be migrated: destination shortcut ({format_match_combo(new_match)}) already has a custom override. The previous description was preserved on the old shortcut.",
                            "old_match": old_match,
                            "new_match": new_match,
                            "orphaned_old": True,
                        }
                    elif not mig_res.get("migrated"):
                        sidecar_warning = {
                            "code": "write_failed",
                            "message": "Sidecar migration failed: could not update sidecar file.",
                            "old_match": old_match,
                            "new_match": new_match,
                            "orphaned_old": False,
                        }
                except Exception as exc:
                    sidecar_warning = {
                        "code": "write_failed",
                        "message": f"Sidecar migration error: {exc}",
                        "old_match": old_match,
                        "new_match": new_match,
                        "orphaned_old": False,
                    }

            if (getattr(args, "description", None) or getattr(args, "category", None)) and sidecar_path and new_match:
                try:
                    save_override(
                        sidecar_path,
                        new_match,
                        description=getattr(args, "description", None),
                        category=getattr(args, "category", None),
                    )
                except Exception as exc:
                    if sidecar_warning is None:
                        sidecar_warning = {
                            "code": "write_failed",
                            "message": f"Sidecar update error: {exc}",
                            "old_match": old_match,
                            "new_match": new_match,
                            "orphaned_old": False,
                        }

        if edit_action == "add" and result.applied and not result.rolled_back:
            if (getattr(args, "description", None) or getattr(args, "category", None)) and sidecar_path and expected_new_bind:
                add_match = {
                    "modifiers": list(expected_new_bind.modifiers),
                    "key": expected_new_bind.key,
                    "submap": expected_new_bind.submap or "",
                    "dispatcher": expected_new_bind.dispatcher.path if expected_new_bind.dispatcher else None,
                }
                try:
                    save_override(
                        sidecar_path,
                        add_match,
                        description=getattr(args, "description", None),
                        category=getattr(args, "category", None),
                    )
                except Exception as exc:
                    sidecar_warning = {
                        "code": "write_failed",
                        "message": f"Sidecar addition error: {exc}",
                        "old_match": None,
                        "new_match": add_match,
                        "orphaned_old": False,
                    }
    except NotEditableError as exc:
        msg = f"not editable: {exc}"
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode=mode_name, applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[msg], **get_extra_fields()
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hks edit: {msg}\n")
        return 1
    except EditConflict as exc:
        msg = f"conflict: {exc}"
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode=mode_name, applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[msg], **get_extra_fields()
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hks edit: {msg}\n")
        return 1
    except ValueError as exc:
        msg = str(exc)
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode=mode_name, applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[msg], **get_extra_fields()
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hks edit: error: {msg}\n")
        return 1
    except KeyError as exc:
        raw_msg = exc.args[0] if exc.args else str(exc)
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode=mode_name, applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[raw_msg], **get_extra_fields()
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hks edit: error: {raw_msg}\n")
        return 1
    except BackupError as exc:
        msg = f"backup error: {exc}"
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode=mode_name, applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[msg], **get_extra_fields()
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hks edit: {msg}\n")
        return 1

    if is_json:
        warnings = []
        if result.companion_warning:
            warnings.append(result.companion_warning)
        if sidecar_warning:
            warnings.append(sidecar_warning["message"])
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
            dispatcher_unchanged=result.dispatcher_unchanged,
            **get_extra_fields(),
        )
        sys.stdout.write(json.dumps(out_data, indent=2, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    else:
        output = format_apply_result(result, dry_run=is_dry_run, reload=args.reload)
        if sidecar_warning:
            output += f"\n[Sidecar Warning] {sidecar_warning['message']}"
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


def _handle_recorder(args: argparse.Namespace) -> int:
    is_json = bool(getattr(args, "json_output", False))
    action = getattr(args, "recorder_action", None)
    language = getattr(args, "language", "lua")
    submap = getattr(args, "submap", "hks_record")

    if action == "enter":
        res = enter_submap(language=language, submap_name=submap)
        res["action"] = "enter"
    elif action == "leave":
        res = leave_submap(language=language)
    elif action == "status":
        res = submap_status()
    elif action == "heal":
        res = heal_submap(language=language, submap_name=submap)
    else:
        sys.stderr.write(f"hks recorder: unknown action {action}\n")
        return 2

    if is_json:
        sys.stdout.write(json.dumps(res, indent=2) + "\n")
    else:
        if res.get("ok"):
            msg = res.get("message") or res.get("reason") or res.get("strategy") or "ok"
            sys.stdout.write(f"recorder {action}: {msg}\n")
        else:
            msg = res.get("message") or res.get("reason") or "error"
            sys.stderr.write(f"recorder {action} failed: {msg}\n")

    return 0 if res.get("ok", True) else 1


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

        if args.subcommand == "dispatchers":
            sys.stdout.write(json.dumps({"ok": True, "dispatchers": get_catalog()}, indent=2) + "\n")
            sys.stdout.flush()
            return 0

        if args.subcommand == "conflicts":
            if getattr(args, "conflicts_action", None) == "check" or (
                getattr(args, "mods", None) is not None and getattr(args, "key", None) is not None
            ):
                doc, _ = run_scan_pipeline(
                    config_dir=getattr(args, "config_dir", None),
                    entrypoint=getattr(args, "entrypoint", None),
                    no_live=bool(getattr(args, "no_live", False)),
                    with_oracle=False,
                )
                res = check_candidate_conflict(
                    binds=doc.binds,
                    mods=args.mods,
                    key=args.key,
                    submap=getattr(args, "submap", "") or "",
                    exclude_id=getattr(args, "exclude_id", None),
                    disabled_binds=doc.disabled_binds,
                )
                sys.stdout.write(json.dumps(res, indent=2) + "\n")
                sys.stdout.flush()
                return 0

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

        if args.subcommand == "categories":
            return _handle_categories(args)

        if args.subcommand == "sidecar":
            return _handle_sidecar(args)

        if args.subcommand == "recorder":
            return _handle_recorder(args)
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
