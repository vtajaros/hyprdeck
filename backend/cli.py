"""CLI entrypoint for HyprDeck Phase 1."""

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
        sys.stderr.write(f"hyprdeck: error: {message}\n")
        raise SystemExit(2)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = _CleanArgumentParser(
        prog="python -m backend.cli",
        description="HyprDeck Phase 1 read-only config scanner.",
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
        help="Uncomment a previously disabled bind ID (may be specified multiple times).",
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
        help="List or diff configuration backups stored in the HyprDeck backup directory.",
    )
    bak_p.add_argument(
        "action",
        nargs="?",
        choices=["list", "diff"],
        default="list",
        help="Optional backup action ('list' or 'diff').",
    )
    bak_p.add_argument(
        "--id",
        dest="backup_id",
        default=None,
        help="Backup ID (for 'backups diff --id X').",
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
    rec_enter.add_argument("--watch-pid", dest="watch_pid", type=int, default=None)
    rec_enter.add_argument("--watchdog-timeout", dest="watchdog_timeout", type=float, default=20.0)
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

    # overrides subcommand
    ov_p = subparsers.add_parser(
        "overrides",
        help="Inspect or manage the HyprDeck overrides include block.",
    )
    ov_sub = ov_p.add_subparsers(dest="overrides_action", required=True)

    ov_status = ov_sub.add_parser("status", help="Show overrides include and file status.")
    ov_status.add_argument("--config-dir", dest="config_dir", default=None, help="Override Hyprland config dir.")
    ov_status.add_argument("--entrypoint", dest="entrypoint", default=None, help="Override entrypoint file.")
    ov_status.add_argument("--no-live", dest="no_live", action="store_true", default=False, help="Disable live hyprctl probing.")
    ov_status.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    for ov_act, ov_help in [
        ("install-include", "Install the HyprDeck overrides include block into hyprland.lua (dry-run by default)."),
        ("uninstall-include", "Remove the HyprDeck overrides include block from hyprland.lua (dry-run by default)."),
    ]:
        ov_act_p = ov_sub.add_parser(ov_act, help=ov_help)
        ov_act_p.add_argument("--config-dir", dest="config_dir", default=None, help="Override Hyprland config dir.")
        ov_act_p.add_argument("--entrypoint", dest="entrypoint", default=None, help="Override entrypoint file.")
        ov_act_p.add_argument("--no-live", dest="no_live", action="store_true", default=False, help="Disable live hyprctl probing and reload.")
        ov_act_p.add_argument("--apply", dest="apply", action="store_true", default=False, help="Write changes to disk (requires --scan-sha256).")
        ov_act_p.add_argument("--scan-sha256", dest="scan_sha256", default=None, help="Expected SHA-256 of the entrypoint before editing.")
        ov_act_p.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    # migrate-data subcommand
    md_p = subparsers.add_parser(
        "migrate-data",
        help="Migrate legacy ~/.config/hks and ~/.local/share/hks directories to hyprdeck (dry-run by default).",
    )
    md_mode = md_p.add_mutually_exclusive_group()
    md_mode.add_argument("--dry-run", dest="apply", action="store_false", default=False, help="Preview moves without modifying disk (default).")
    md_mode.add_argument("--apply", dest="apply", action="store_true", help="Atomically rename legacy directories and leave symlinks.")
    md_p.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    # settings subcommand
    st_p = subparsers.add_parser(
        "settings",
        help="Read, preview, commit, or reset Hyprland settings.",
    )
    st_sub = st_p.add_subparsers(dest="settings_action", required=True)

    def _add_common_st_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--config-dir", dest="config_dir", default=None, help="Override Hyprland config dir.")
        p.add_argument("--entrypoint", dest="entrypoint", default=None, help="Override entrypoint file.")
        p.add_argument("--no-live", dest="no_live", action="store_true", default=False, help="Disable live hyprctl probing/reload.")
        p.add_argument(
            "--reload-mode",
            dest="reload_mode",
            choices=["none", "config-only", "full"],
            default=None,
            help="Override reload mode (none | config-only | full).",
        )
        p.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    st_state = st_sub.add_parser("state", help="Read merged live + overrides settings state.")
    _add_common_st_args(st_state)

    st_prev = st_sub.add_parser("preview", help="Ephemerally preview settings changes via hyprctl eval.")
    st_prev.add_argument("source", nargs="?", default=None, help="Path to JSON changes file, or '-' for stdin.")
    st_prev.add_argument("--inline", dest="inline_json", default=None, help="Inline JSON string.")
    st_prev.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    st_rev = st_sub.add_parser("revert-preview", help="Revert ephemeral preview via hyprctl reload config-only.")
    st_rev.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    st_com = st_sub.add_parser("commit", help="Validate and commit settings changes to hks-overrides.lua (dry-run by default).")
    st_com.add_argument("source", nargs="?", default=None, help="Path to JSON changes file (or {changes, resets}), or '-' for stdin.")
    st_com.add_argument("--inline", dest="inline_json", default=None, help="Inline JSON string.")
    st_com.add_argument("--apply", dest="apply", action="store_true", default=False, help="Write changes to disk (requires --scan-sha256).")
    st_com.add_argument("--scan-sha256", dest="scan_sha256", default=None, help="Expected SHA-256 of hks-overrides.lua (or 'absent').")
    _add_common_st_args(st_com)

    st_rst = st_sub.add_parser("reset", help="Reset a section or option in hks-overrides.lua (dry-run by default).")
    st_rst.add_argument("--section", dest="section", default=None, help="Section to reset (appearance | desktop).")
    st_rst.add_argument("--option", dest="option_id", default=None, help="Single option ID to reset.")
    st_rst.add_argument("--apply", dest="apply", action="store_true", default=False, help="Write changes to disk (requires --scan-sha256).")
    st_rst.add_argument("--scan-sha256", dest="scan_sha256", default=None, help="Expected SHA-256 of hks-overrides.lua.")
    _add_common_st_args(st_rst)

    # settings display subcommand
    st_disp = st_sub.add_parser("display", help="Display monitors and brightness operations.")
    disp_sub = st_disp.add_subparsers(dest="display_action", required=True)

    disp_state = disp_sub.add_parser("state", help="Read monitors, overrides, and brightness state.")
    disp_state.add_argument("--enable-ddc", dest="enable_ddc", action="store_true", default=False, help="Probe ddcutil brightness.")
    disp_state.add_argument("--state-dir", dest="state_dir", default=None, help="Override revert-guard state dir.")
    _add_common_st_args(disp_state)

    disp_apply = disp_sub.add_parser("apply", help="Validate and apply monitor configuration with revert watchdog.")
    disp_apply.add_argument("source", nargs="?", default=None, help="Path to JSON monitor changes file, or '-' for stdin.")
    disp_apply.add_argument("--inline", dest="inline_json", default=None, help="Inline JSON string.")
    disp_apply.add_argument("--apply", dest="apply", action="store_true", default=False, help="Write changes and arm revert guard (requires --scan-sha256).")
    disp_apply.add_argument("--scan-sha256", dest="scan_sha256", default=None, help="Expected SHA-256 of hks-overrides.lua (or 'absent').")
    disp_apply.add_argument("--timeout", dest="timeout", type=float, default=15.0, help="Revert-guard confirmation timeout seconds.")
    disp_apply.add_argument("--watch-pid", dest="watch_pid", default=None, help="PID to watch (or 'ppid' for parent process).")
    disp_apply.add_argument("--state-dir", dest="state_dir", default=None, help="Override revert-guard state dir.")
    _add_common_st_args(disp_apply)

    disp_conf = disp_sub.add_parser("confirm", help="Confirm active display changes and disarm revert watchdog.")
    disp_conf.add_argument("--state-dir", dest="state_dir", default=None, help="Override revert-guard state dir.")
    disp_conf.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    disp_rev = disp_sub.add_parser("revert", help="Immediately revert active display changes and disarm watchdog.")
    disp_rev.add_argument("--state-dir", dest="state_dir", default=None, help="Override revert-guard state dir.")
    disp_rev.add_argument("--no-live", dest="no_live", action="store_true", default=False, help="Disable live hyprctl reload during revert.")
    disp_rev.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    disp_bri = disp_sub.add_parser("brightness", help="Read or set panel/DDC brightness (5%% minimum floor).")
    disp_bri.add_argument("--set", dest="set_percent", type=float, default=None, help="Target brightness percentage (5..100).")
    disp_bri.add_argument("--device", dest="device", default=None, help="Backlight device name for brightnessctl.")
    disp_bri.add_argument("--ddc", dest="use_ddc", action="store_true", default=False, help="Read/set via ddcutil.")
    disp_bri.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    # settings input subcommand
    st_inp = st_sub.add_parser("input", help="Input keyboard/mouse/touchpad/per-device operations.")
    inp_sub = st_inp.add_subparsers(dest="input_action", required=True)

    inp_state = inp_sub.add_parser("state", help="Read input options, XKB layouts, and devices state.")
    inp_state.add_argument("--state-dir", dest="state_dir", default=None, help="Override revert-guard state dir.")
    _add_common_st_args(inp_state)

    inp_apply = inp_sub.add_parser("apply", help="Validate and apply input/device configuration.")
    inp_apply.add_argument("source", nargs="?", default=None, help="Path to JSON input changes file, or '-' for stdin.")
    inp_apply.add_argument("--inline", dest="inline_json", default=None, help="Inline JSON string.")
    inp_apply.add_argument("--apply", dest="apply", action="store_true", default=False, help="Write changes (requires --scan-sha256).")
    inp_apply.add_argument("--scan-sha256", dest="scan_sha256", default=None, help="Expected SHA-256 of hks-overrides.lua (or 'absent').")
    inp_apply.add_argument("--timeout", dest="timeout", type=float, default=15.0, help="Revert-guard confirmation timeout seconds.")
    inp_apply.add_argument("--watch-pid", dest="watch_pid", default=None, help="PID to watch (or 'ppid' for parent process).")
    inp_apply.add_argument("--state-dir", dest="state_dir", default=None, help="Override revert-guard state dir.")
    _add_common_st_args(inp_apply)

    inp_conf = inp_sub.add_parser("confirm", help="Confirm active input changes and disarm revert watchdog.")
    inp_conf.add_argument("--state-dir", dest="state_dir", default=None, help="Override revert-guard state dir.")
    inp_conf.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    inp_rev = inp_sub.add_parser("revert", help="Immediately revert active input changes and disarm watchdog.")
    inp_rev.add_argument("--state-dir", dest="state_dir", default=None, help="Override revert-guard state dir.")
    inp_rev.add_argument("--no-live", dest="no_live", action="store_true", default=False, help="Disable live hyprctl reload during revert.")
    inp_rev.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    # settings audio subcommand
    st_aud = st_sub.add_parser("audio", help="Live PipeWire/PulseAudio device and volume operations.")
    aud_sub = st_aud.add_subparsers(dest="audio_action", required=True)

    aud_state = aud_sub.add_parser("state", help="Read audio outputs, inputs, and playback streams.")
    aud_state.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")
    aud_state.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")

    for sub_name, default_kind, help_txt in (
        ("set-volume", "sink", "Set device volume percentage (clamped 0..100 by default, hard cap 150)."),
        ("set-sink-volume", "sink", "Set output sink volume percentage."),
        ("set-source-volume", "source", "Set input source volume percentage."),
    ):
        p = aud_sub.add_parser(sub_name, help=help_txt)
        p.add_argument("name", help="Target node name (never numeric index).")
        p.add_argument("percent", help="Target volume percentage.")
        if sub_name == "set-volume":
            p.add_argument("--kind", choices=("sink", "source"), default=default_kind, help="Device kind (sink or source).")
        p.add_argument("--max-percent", dest="max_percent", type=int, default=100, help="Upper clamp limit (hard cap 150).")
        p.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
        p.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    for sub_name, default_kind, help_txt in (
        ("set-mute", "sink", "Set device mute state (1, 0, or toggle)."),
        ("set-sink-mute", "sink", "Set output sink mute state (1, 0, or toggle)."),
        ("set-source-mute", "source", "Set input source mute state (1, 0, or toggle)."),
    ):
        p = aud_sub.add_parser(sub_name, help=help_txt)
        p.add_argument("name", help="Target node name (never numeric index).")
        p.add_argument("mode", help="Mute mode: 1, 0, or toggle.")
        if sub_name == "set-mute":
            p.add_argument("--kind", choices=("sink", "source"), default=default_kind, help="Device kind (sink or source).")
        p.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
        p.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    for sub_name, default_kind, help_txt in (
        ("set-default", "sink", "Set default audio device."),
        ("set-default-sink", "sink", "Set default output sink."),
        ("set-default-source", "source", "Set default input source."),
    ):
        p = aud_sub.add_parser(sub_name, help=help_txt)
        p.add_argument("name", help="Target node name (never numeric index).")
        if sub_name == "set-default":
            p.add_argument("--kind", choices=("sink", "source"), default=default_kind, help="Device kind (sink or source).")
        p.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
        p.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    # settings bluetooth subcommand
    st_bt = st_sub.add_parser("bluetooth", help="Live BlueZ Bluetooth controller and device operations.")
    bt_sub = st_bt.add_subparsers(dest="bluetooth_action", required=True)

    bt_state = bt_sub.add_parser("state", help="Read Bluetooth controller, rfkill, and device state.")
    bt_state.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
    bt_state.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    for sub_name, help_txt in (
        ("power", "Turn Bluetooth controller on or off."),
        ("pairable", "Set controller pairable mode on or off."),
    ):
        p = bt_sub.add_parser(sub_name, help=help_txt)
        p.add_argument("state", choices=("on", "off"), help="Target state: on or off.")
        p.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
        p.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    bt_disc = bt_sub.add_parser("discoverable", help="Set controller discoverable mode on or off.")
    bt_disc.add_argument("state", choices=("on", "off"), help="Target state: on or off.")
    bt_disc.add_argument("discoverable_timeout", nargs="?", type=int, default=180, help="Discoverable timeout seconds (capped at 300).")
    bt_disc.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
    bt_disc.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    for sub_name, help_txt in (
        ("connect", "Connect to a Bluetooth device by MAC."),
        ("disconnect", "Disconnect a Bluetooth device by MAC."),
        ("trust", "Mark a Bluetooth device as trusted."),
        ("untrust", "Mark a Bluetooth device as untrusted."),
        ("block", "Block a Bluetooth device."),
        ("unblock", "Unblock a Bluetooth device."),
        ("remove", "Remove/unpair a Bluetooth device."),
        ("pair", "Pair with a Bluetooth device (one-shot NoInputNoOutput agent)."),
    ):
        p = bt_sub.add_parser(sub_name, help=help_txt)
        p.add_argument("mac", help="Device MAC address (AA:BB:CC:DD:EE:FF).")
        p.add_argument("--timeout", dest="timeout", type=float, default=15.0 if sub_name in ("connect", "pair") else 5.0, help="Per-command timeout seconds.")
        p.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    bt_alias = bt_sub.add_parser("alias", help="Set a Bluetooth device alias.")
    bt_alias.add_argument("mac", help="Device MAC address.")
    bt_alias.add_argument("name", help="New device alias.")
    bt_alias.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
    bt_alias.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    bt_scan = bt_sub.add_parser("scan", help="Start, stop, or read Bluetooth discovery scan.")
    bt_scan.add_argument("mode", choices=("start", "stop", "results"), help="Scan action: start, stop, or results.")
    bt_scan.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
    bt_scan.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    # settings network subcommand
    st_net = st_sub.add_parser("network", help="Live NetworkManager status, Wi-Fi, and connection operations.")
    net_sub = st_net.add_subparsers(dest="network_action", required=True)

    net_state = net_sub.add_parser("state", help="Read NetworkManager general, device, connection, and Wi-Fi state.")
    net_state.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
    net_state.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    net_wifi = net_sub.add_parser("wifi", help="Enable or disable Wi-Fi radio.")
    net_wifi.add_argument("state", choices=("on", "off"), help="Target state: on or off.")
    net_wifi.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
    net_wifi.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    net_rescan = net_sub.add_parser("rescan", help="Trigger Wi-Fi scan.")
    net_rescan.add_argument("--timeout", dest="timeout", type=float, default=10.0, help="Per-command timeout seconds.")
    net_rescan.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    net_conn = net_sub.add_parser("connect", help="Activate a saved connection by UUID.")
    net_conn.add_argument("uuid", help="Connection UUID.")
    net_conn.add_argument("--timeout", dest="timeout", type=float, default=15.0, help="Activation timeout seconds.")
    net_conn.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    net_disc = net_sub.add_parser("disconnect", help="Disconnect a network device.")
    net_disc.add_argument("device", help="Device interface name.")
    net_disc.add_argument("--confirm", dest="confirm", action="store_true", default=False, help="Confirm cutting active session.")
    net_disc.add_argument("--timeout", dest="timeout", type=float, default=10.0, help="Per-command timeout seconds.")
    net_disc.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    net_join = net_sub.add_parser("join", help="Connect to a Wi-Fi SSID (password read from stdin only, never argv).")
    net_join.add_argument("ssid", help="Target Wi-Fi SSID.")
    net_join.add_argument("--security", dest="security", default="", help="Security hint (e.g. wpa, wep, open).")
    net_join.add_argument("--timeout", dest="timeout", type=float, default=15.0, help="Activation timeout seconds.")
    net_join.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    net_forget = net_sub.add_parser("forget", help="Delete a saved connection profile by UUID.")
    net_forget.add_argument("uuid", help="Connection UUID.")
    net_forget.add_argument("--confirm", dest="confirm", action="store_true", default=False, help="Confirm cutting active session.")
    net_forget.add_argument("--timeout", dest="timeout", type=float, default=10.0, help="Per-command timeout seconds.")
    net_forget.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    net_auto = net_sub.add_parser("autoconnect", help="Set connection autoconnect on or off.")
    net_auto.add_argument("uuid", help="Connection UUID.")
    net_auto.add_argument("state", choices=("on", "off"), help="Target state: on or off.")
    net_auto.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
    net_auto.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    net_met = net_sub.add_parser("metered", help="Set connection metered state.")
    net_met.add_argument("uuid", help="Connection UUID.")
    net_met.add_argument("value", choices=("yes", "no", "unknown"), help="Metered value.")
    net_met.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
    net_met.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    net_dns = net_sub.add_parser("dns", help="Set connection IPv4 DNS servers or 'auto'.")
    net_dns.add_argument("uuid", help="Connection UUID.")
    net_dns.add_argument("servers", help="Comma-separated IPv4/IPv6 addresses or 'auto'.")
    net_dns.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
    net_dns.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    # settings themes subcommand
    st_thm = st_sub.add_parser("themes", help="System themes (wallpaper, GTK, icons, cursor, Qt6ct).")
    thm_sub = st_thm.add_subparsers(dest="themes_action", required=True)

    thm_state = thm_sub.add_parser("state", help="Read current theme state and consistency conflicts.")
    thm_state.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
    thm_state.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    thm_gtk = thm_sub.add_parser("gtk", help="Set GTK theme (gsettings + gtk-3.0/gtk-4.0 settings.ini).")
    thm_gtk.add_argument("name", help="Installed GTK theme name.")
    thm_gtk.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
    thm_gtk.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    thm_icons = thm_sub.add_parser("icons", help="Set icon theme (gsettings + gtk-3.0/gtk-4.0 settings.ini).")
    thm_icons.add_argument("name", help="Installed icon theme name.")
    thm_icons.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
    thm_icons.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    thm_cursor = thm_sub.add_parser("cursor", help="Set cursor theme and optional size (16..64).")
    thm_cursor.add_argument("name", help="Installed cursor theme name.")
    thm_cursor.add_argument("size", nargs="?", type=int, default=None, help="Optional cursor size (16..64).")
    thm_cursor.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
    thm_cursor.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    thm_qt = thm_sub.add_parser("qt", help="Update qt6ct.conf style, icon theme, or color scheme.")
    thm_qt.add_argument("--style", dest="style", default=None, help="Qt6 style name.")
    thm_qt.add_argument("--icons", dest="icons", default=None, help="Qt6ct icon theme name.")
    thm_qt.add_argument("--colors", dest="colors", default=None, help="Qt6ct color scheme file/name.")
    thm_qt.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
    thm_qt.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    thm_wp = thm_sub.add_parser("wallpaper", help="Wallpaper actions.")
    thm_wp.add_argument("wp_action", choices=("open",), help="Action: open wallpaper picker.")
    thm_wp.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    # settings power subcommand
    st_pwr = st_sub.add_parser("power", help="Battery, CPU EPP/turbo, hypridle, and lid/sleep state.")
    pwr_sub = st_pwr.add_subparsers(dest="power_action", required=True)

    pwr_state = pwr_sub.add_parser("state", help="Read battery, CPU, hypridle, and lid/sleep state.")
    pwr_state.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
    pwr_state.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    pwr_epp = pwr_sub.add_parser("epp", help="Set CPU energy performance preference via pkexec (session-only).")
    pwr_epp.add_argument("value", help="EPP preference (e.g. performance, balance_performance, balance_power, power).")
    pwr_epp.add_argument("--timeout", dest="timeout", type=float, default=15.0, help="pkexec timeout seconds.")
    pwr_epp.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    pwr_turbo = pwr_sub.add_parser("turbo", help="Enable or disable Intel Turbo Boost via pkexec (session-only).")
    pwr_turbo.add_argument("mode", choices=("on", "off"), help="Target state: on or off.")
    pwr_turbo.add_argument("--timeout", dest="timeout", type=float, default=15.0, help="pkexec timeout seconds.")
    pwr_turbo.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    pwr_idle = pwr_sub.add_parser("idle", help="Update hypridle dim/lock/dpms timeouts in seconds and restart hypridle.")
    pwr_idle.add_argument("pairs", nargs="*", help="Optional role=seconds pairs (e.g. dim=300 lock=600 dpms=900).")
    pwr_idle.add_argument("--dim", dest="dim_sec", type=int, default=None, help="Dim timeout in seconds (30..86400).")
    pwr_idle.add_argument("--lock", dest="lock_sec", type=int, default=None, help="Lock timeout in seconds (30..86400).")
    pwr_idle.add_argument("--dpms", dest="dpms_sec", type=int, default=None, help="DPMS off timeout in seconds (30..86400).")
    pwr_idle.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
    pwr_idle.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    # settings system subcommand
    st_sys = st_sub.add_parser("system", help="Read-only system hardware and software overview.")
    sys_sub = st_sys.add_subparsers(dest="system_action", required=True)

    sys_info = sys_sub.add_parser("info", help="Read privacy-safe system information.")
    sys_info.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
    sys_info.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    # settings keyboard subcommand
    st_kb = st_sub.add_parser("keyboard", help="Inspect or open HyprDeck Keybind Studio.")
    kb_sub = st_kb.add_subparsers(dest="keyboard_action", required=True)

    kb_state = kb_sub.add_parser("state", help="Read Keybind Studio launcher availability and window state.")
    kb_state.add_argument("--timeout", dest="timeout", type=float, default=5.0, help="Per-command timeout seconds.")
    kb_state.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    kb_open = kb_sub.add_parser("open", help="Launch or focus the HyprDeck Keybind Studio window.")
    kb_open.add_argument("--timeout", dest="timeout", type=float, default=8.0, help="Window launch timeout seconds.")
    kb_open.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    # settings backups subcommand
    st_bak = st_sub.add_parser("backups", help="List, diff, and safely restore configuration backups.")
    sbak_sub = st_bak.add_subparsers(dest="backups_action", required=True)

    sbak_list = sbak_sub.add_parser("list", help="List enriched configuration backups.")
    sbak_list.add_argument("--path", dest="path", default=None, help="Filter backups by original file path.")
    sbak_list.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    sbak_diff = sbak_sub.add_parser("diff", help="Diff a backup snapshot against the current file on disk.")
    sbak_diff.add_argument("--id", dest="backup_id", required=True, help="Backup ID to diff.")
    sbak_diff.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

    sbak_res = sbak_sub.add_parser("restore", help="Safely restore a backup snapshot (dry-run unless --apply).")
    sbak_res.add_argument("--id", dest="backup_id", required=True, help="Backup ID to restore.")
    sbak_res.add_argument("--dry-run", dest="dry_run", action="store_true", default=False, help="Preview restore without writing.")
    sbak_res.add_argument("--apply", dest="apply", action="store_true", default=False, help="Write restored file and reload.")
    sbak_res.add_argument("--no-reload", dest="no_reload", action="store_true", default=False, help="Skip per-file reload after restore.")
    sbak_res.add_argument("--force", dest="force", action="store_true", default=False, help="Skip expected-sha256 check.")
    sbak_res.add_argument("--expected-sha256", dest="expected_sha256", default=None, help="Expected current file SHA-256.")
    sbak_res.add_argument("--json", dest="json_output", action="store_true", default=False, help="Emit JSON output.")

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
                "[HyprDeck Oracle] ERROR: `hyprctl binds -j` is unavailable.\n"
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
    lines.append(f"[HyprDeck Edit] Mode: {mode_label}")
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
            sys.stderr.write(f"hyprdeck sidecar: error: {msg}\n")
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
                    sys.stderr.write(f"hyprdeck sidecar: {msg}\n")
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
                    sys.stderr.write(f"hyprdeck sidecar: {msg}\n")
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
                        sys.stderr.write(f"hyprdeck sidecar: {msg}\n")
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
                    sys.stderr.write(f"hyprdeck sidecar: {msg}\n")
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
                    sys.stderr.write(f"hyprdeck sidecar: {msg}\n")
                return 1
            if new_match is None:
                msg = f"New bind '{args.new_id}' not found."
                if is_json:
                    sys.stdout.write(json.dumps({"error": msg}, indent=2) + "\n")
                else:
                    sys.stderr.write(f"hyprdeck sidecar: {msg}\n")
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
            sys.stderr.write(f"hyprdeck sidecar: unknown action '{action}'\n")
            return 2
    except SidecarStoreError as exc:
        if is_json:
            sys.stdout.write(json.dumps({"error": str(exc)}, indent=2) + "\n")
        else:
            sys.stderr.write(f"hyprdeck sidecar: error: {exc}\n")
        return 1
    except Exception as exc:
        if is_json:
            sys.stdout.write(json.dumps({"error": str(exc)}, indent=2) + "\n")
        else:
            sys.stderr.write(f"hyprdeck sidecar: error: {exc}\n")
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
            sys.stderr.write(f"hyprdeck: error: {msg}\n")
        return 2

    if getattr(args, "reload", False) and not getattr(args, "apply", False):
        msg = "--reload requires --apply"
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode="error", applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[msg]
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hyprdeck: error: {msg}\n")
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
            sys.stderr.write(f"hyprdeck: error: {msg}\n")
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
                sys.stderr.write(f"hyprdeck edit: error: {msg}\n")
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
                if args.dispatcher_id == "exec_cmd" and doc.environment.language == "lua" and rendered_args is not None:
                    from backend.editor.dispatchers import _decode_lua_string
                    new_args = _decode_lua_string(rendered_args)
                else:
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
                if args.dispatcher_id == "exec_cmd" and doc.environment.language == "lua" and rendered_args is not None:
                    from backend.editor.dispatchers import _decode_lua_string
                    new_args = _decode_lua_string(rendered_args)
                else:
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
                        sys.stderr.write(f"hyprdeck edit: error: {msg}\n")
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
                        sys.stderr.write(f"hyprdeck edit: error: {msg}\n")
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
                            sys.stderr.write(f"hyprdeck edit: error: {msg}\n")
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
            sys.stderr.write(f"hyprdeck edit: {msg}\n")
        return 1
    except EditConflict as exc:
        msg = f"conflict: {exc}"
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode=mode_name, applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[msg], **get_extra_fields()
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hyprdeck edit: {msg}\n")
        return 1
    except ValueError as exc:
        msg = str(exc)
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode=mode_name, applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[msg], **get_extra_fields()
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hyprdeck edit: error: {msg}\n")
        return 1
    except KeyError as exc:
        raw_msg = exc.args[0] if exc.args else str(exc)
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode=mode_name, applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[raw_msg], **get_extra_fields()
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hyprdeck edit: error: {raw_msg}\n")
        return 1
    except BackupError as exc:
        msg = f"backup error: {exc}"
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode=mode_name, applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[msg], **get_extra_fields()
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hyprdeck edit: {msg}\n")
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
    action = getattr(args, "action", "list") or "list"
    if action == "diff":
        from backend.settings.backups_ops import diff_backup

        backup_id = getattr(args, "backup_id", None)
        if not backup_id:
            msg = "Missing --id for 'backups diff'."
            if is_json:
                sys.stdout.write(json.dumps({"ok": False, "error": msg}, indent=2) + "\n")
            else:
                sys.stderr.write(f"hyprdeck backups diff: error: {msg}\n")
            return 1
        try:
            res = diff_backup(backup_id)
        except BackupError as exc:
            res = {"ok": False, "id": backup_id, "error": str(exc)}
        if is_json:
            sys.stdout.write(json.dumps(res, indent=2, ensure_ascii=False) + "\n")
        else:
            if res.get("ok"):
                sys.stdout.write(res.get("diff") or "(identical)\n")
            else:
                sys.stderr.write(f"hyprdeck backups diff: error: {res.get('error')}\n")
        sys.stdout.flush()
        return 0 if res.get("ok") else 1

    try:
        records = list_backups(path=args.path)
        if is_json:
            from backend.settings.backups_ops import list_enriched_backups
            enriched = list_enriched_backups(path=args.path)
    except BackupError as exc:
        msg = str(exc)
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode="backups", applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=None, errors=[msg], backups=[]
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hyprdeck backups: error: {msg}\n")
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
            backups=enriched,
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
                sys.stderr.write(f"hyprdeck restore: error: {msg}\n")
            return 1
        if not records:
            msg = "no backups available to restore."
            if is_json:
                sys.stdout.write(json.dumps(make_editor_json_output(
                    mode="restore", applied=False, rolled_back=False, diff="", verify=None,
                    warnings=[], backup=None, errors=[msg]
                ), indent=2) + "\n")
            else:
                sys.stderr.write(f"hyprdeck restore: error: {msg}\n")
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
                sys.stderr.write(f"hyprdeck: error: {msg}\n")
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
                    sys.stderr.write(f"hyprdeck restore: error: {msg}\n")
                return 1
        except BackupError as exc:
            msg = str(exc)
            if is_json:
                sys.stdout.write(json.dumps(make_editor_json_output(
                    mode="restore", applied=False, rolled_back=False, diff="", verify=None,
                    warnings=[], backup=None, errors=[msg]
                ), indent=2) + "\n")
            else:
                sys.stderr.write(f"hyprdeck restore: error: {msg}\n")
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
            sys.stderr.write("hyprdeck: error: restore requires --apply to write files (use --dry-run to preview)\n")
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
            sys.stdout.write("[HyprDeck Restore] Mode: DRY-RUN (no files modified)\n\n" + diff_text + "\nResult: PREVIEW\n")
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
            sys.stderr.write(f"hyprdeck restore: {msg}\n")
        return 1
    except BackupError as exc:
        msg = str(exc)
        if is_json:
            sys.stdout.write(json.dumps(make_editor_json_output(
                mode="restore", applied=False, rolled_back=False, diff="", verify=None,
                warnings=[], backup=matched, errors=[msg]
            ), indent=2) + "\n")
        else:
            sys.stderr.write(f"hyprdeck restore: error: {msg}\n")
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
        res = enter_submap(
            language=language,
            submap_name=submap,
            watch_pid=getattr(args, "watch_pid", None),
            watchdog_timeout=float(getattr(args, "watchdog_timeout", 20.0)),
        )
        res["action"] = "enter"
    elif action == "leave":
        res = leave_submap(language=language)
    elif action == "status":
        res = submap_status()
    elif action == "heal":
        res = heal_submap(language=language, submap_name=submap)
    else:
        sys.stderr.write(f"hyprdeck recorder: unknown action {action}\n")
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


def _handle_overrides(args: argparse.Namespace) -> int:
    from backend.core.constants import OVERRIDES_FILENAME
    from backend.core.include_block import IncludeBlockError, has_include
    from backend.core.overrides import OverridesError, parse_sections
    from backend.core.transaction import install_include, uninstall_include
    from backend.editor.backups import compute_file_sha256

    disc = discover_config(
        config_dir=args.config_dir,
        entrypoint=args.entrypoint,
        no_live=args.no_live,
    )
    env_info = disc.environment
    action = args.overrides_action

    if action == "status":
        overrides_path = os.path.join(env_info.config_dir, OVERRIDES_FILENAME)
        overrides_present = os.path.isfile(overrides_path)
        overrides_sha = compute_file_sha256(overrides_path) if overrides_present else None
        sections: list[str] = []
        sections_error: str | None = None
        if overrides_present:
            try:
                with open(overrides_path, "r", encoding="utf-8") as f:
                    sections = list(parse_sections(f.read()).keys())
            except OverridesError as exc:
                sections_error = str(exc)

        include_installed = False
        include_error: str | None = None
        if env_info.language == "lua" and os.path.isfile(env_info.entrypoint):
            try:
                with open(env_info.entrypoint, "r", encoding="utf-8") as f:
                    include_installed = has_include(f.read())
            except IncludeBlockError as exc:
                include_error = str(exc)

        payload = {
            "config_dir": env_info.config_dir,
            "entrypoint": env_info.entrypoint,
            "entrypoint_sha256": compute_file_sha256(env_info.entrypoint)
            if os.path.isfile(env_info.entrypoint)
            else None,
            "language": env_info.language,
            "include_installed": include_installed,
            "include_error": include_error,
            "overrides_path": overrides_path,
            "overrides_present": overrides_present,
            "overrides_sha256": overrides_sha,
            "sections": sections,
            "sections_error": sections_error,
        }
        if args.json_output:
            sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        else:
            lines = [
                f"Config dir:         {payload['config_dir']}",
                f"Entrypoint:         {payload['entrypoint']} ({payload['language']})",
                f"Entrypoint SHA-256: {payload['entrypoint_sha256']}",
                f"Include installed:  {payload['include_installed']}",
                f"Overrides file:     {payload['overrides_path']} (present={payload['overrides_present']})",
                f"Overrides SHA-256:  {payload['overrides_sha256']}",
                f"Sections:           {', '.join(sections) if sections else '(none)'}",
            ]
            if include_error:
                lines.append(f"Include error:      {include_error}")
            if sections_error:
                lines.append(f"Sections error:     {sections_error}")
            sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
        return 0

    dry_run = not bool(args.apply)
    if args.apply and not args.scan_sha256:
        msg = "--apply requires --scan-sha256 <entrypoint_sha256>."
        if args.json_output:
            sys.stdout.write(json.dumps({"applied": False, "errors": [msg]}, indent=2) + "\n")
        else:
            sys.stderr.write(f"hyprdeck overrides: error: {msg}\n")
        return 2

    reload_mode = "none" if args.no_live else "config-only"
    fn = install_include if action == "install-include" else uninstall_include
    res = fn(
        env_info.config_dir,
        env_info.entrypoint,
        expected_sha256=args.scan_sha256,
        reload_mode=reload_mode,
        dry_run=dry_run,
    )
    if args.json_output:
        sys.stdout.write(json.dumps(res.to_dict(), indent=2) + "\n")
    else:
        if res.errors:
            for e in res.errors:
                sys.stderr.write(f"hyprdeck overrides: error: {e}\n")
        if res.diff:
            sys.stdout.write(res.diff)
        else:
            sys.stdout.write("No changes.\n")
        if dry_run and not res.errors:
            sys.stdout.write(
                f"(dry-run; pass --apply --scan-sha256 {res.sha_before} to write)\n"
            )
        elif res.applied:
            sys.stdout.write(
                f"Applied ({res.sha_after})."
                + (f" Backup ID: {res.backup.id}" if res.backup else "")
                + "\n"
            )
    sys.stdout.flush()
    return 1 if res.errors else 0


def _read_json_any(source: str | None, inline_json: str | None = None) -> Any:
    if inline_json is not None:
        raw = inline_json
    elif source == "-":
        raw = sys.stdin.read()
    elif source is not None:
        with open(source, "r", encoding="utf-8") as f:
            raw = f.read()
    else:
        raise ValueError("Either a JSON source path/'-' or --inline is required")
    return json.loads(raw or "{}")


def _read_json_source(source: str | None, inline_json: str | None = None) -> dict[str, Any]:
    data = _read_json_any(source, inline_json)
    if not isinstance(data, dict):
        raise ValueError("JSON input must be an object")
    return data


def _resolve_settings_debug_overrides(
    args: argparse.Namespace,
) -> tuple[str | None, str | None, str | None]:
    """Return (config_dir, reload_mode_override, debug_backup_dir) honoring HYPRDECK_SETTINGS_DEBUG."""
    from backend.core.env import get_env, get_env_flag
    from backend.core.revert_guard import resolve_debug_companion_dir

    cfg_dir = getattr(args, "config_dir", None)
    reload_override = getattr(args, "reload_mode", None)
    debug_bdir: str | None = None
    if get_env_flag("SETTINGS_DEBUG"):
        if cfg_dir is None:
            env_cfg = get_env("SETTINGS_CONFIG_DIR")
            if env_cfg:
                cfg_dir = env_cfg
        if reload_override is None:
            env_rel = get_env("SETTINGS_RELOAD_MODE")
            if env_rel in ("none", "config-only", "full"):
                reload_override = env_rel
        if cfg_dir and not get_env("BACKUP_DIR"):
            debug_bdir = resolve_debug_companion_dir(cfg_dir, "backups")
    return cfg_dir, reload_override, debug_bdir


def _handle_settings_display(
    args: argparse.Namespace,
    cfg_dir: str | None,
    reload_override: str | None,
    debug_bdir: str | None,
) -> int:
    from backend.core.constants import OVERRIDES_FILENAME, SHA256_ABSENT
    from backend.editor.backups import compute_file_sha256
    from backend.settings.display.apply_flow import (
        apply_display_changes,
        confirm_display_changes,
        revert_display_changes,
    )
    from backend.settings.display.brightness import read_brightness, set_brightness
    from backend.settings.display.state import get_display_state, probe_monitors

    d_action = args.display_action

    if d_action == "brightness":
        if args.set_percent is not None:
            res = set_brightness(
                args.set_percent,
                device=args.device,
                use_ddc=args.use_ddc,
            )
            sys.stdout.write(json.dumps(res, indent=2) + "\n")
            sys.stdout.flush()
            return 0 if res.get("ok") else 1
        info = read_brightness(enable_ddc=args.use_ddc)
        sys.stdout.write(json.dumps(info.to_dict(), indent=2) + "\n")
        sys.stdout.flush()
        return 0 if info.available else 1

    if d_action == "confirm":
        res = confirm_display_changes(state_dir=getattr(args, "state_dir", None))
        sys.stdout.write(json.dumps(res, indent=2) + "\n")
        sys.stdout.flush()
        return 0 if res.get("ok") else 1

    if d_action == "revert":
        res = revert_display_changes(state_dir=getattr(args, "state_dir", None))
        sys.stdout.write(json.dumps(res, indent=2) + "\n")
        sys.stdout.flush()
        return 0 if res.get("ok") else 1

    if d_action == "state":
        st = get_display_state(
            config_dir=cfg_dir,
            entrypoint=args.entrypoint,
            no_live=args.no_live,
            enable_ddc=args.enable_ddc,
            state_dir=getattr(args, "state_dir", None),
        )
        sys.stdout.write(json.dumps(st, indent=2) + "\n")
        sys.stdout.flush()
        return 0

    # d_action == "apply"
    disc = discover_config(
        config_dir=cfg_dir,
        entrypoint=args.entrypoint,
        no_live=args.no_live,
    )
    env_info = disc.environment
    dry_run = not bool(args.apply)
    if args.apply and not args.scan_sha256:
        msg = "--apply requires --scan-sha256 <overrides_sha256_or_absent>."
        sys.stdout.write(json.dumps({"applied": False, "errors": [msg]}, indent=2) + "\n")
        return 2

    try:
        payload = _read_json_any(args.source, getattr(args, "inline_json", None))
    except (OSError, ValueError) as exc:
        sys.stdout.write(json.dumps({"applied": False, "errors": [str(exc)]}, indent=2) + "\n")
        return 1

    if not isinstance(payload, (list, dict)):
        sys.stdout.write(
            json.dumps({"applied": False, "errors": ["Display payload must be a JSON array or object"]}, indent=2)
            + "\n"
        )
        return 1

    try:
        current_outputs = probe_monitors()
    except Exception as exc:
        sys.stdout.write(json.dumps({"applied": False, "errors": [str(exc)]}, indent=2) + "\n")
        return 1

    ov_path = os.path.join(env_info.config_dir, OVERRIDES_FILENAME)
    cur_sha = compute_file_sha256(ov_path) if os.path.isfile(ov_path) else SHA256_ABSENT
    expected_sha = args.scan_sha256 if args.scan_sha256 else cur_sha
    if args.no_live:
        reload_mode = "none"
    elif reload_override is not None:
        reload_mode = reload_override
    else:
        reload_mode = "full"

    watch_pid: int | None = None
    if getattr(args, "watch_pid", None) is not None:
        wp_raw = str(args.watch_pid).strip().lower()
        if wp_raw == "ppid":
            watch_pid = os.getppid()
        else:
            try:
                watch_pid = int(wp_raw)
            except ValueError:
                sys.stdout.write(
                    json.dumps({"applied": False, "errors": [f"Invalid --watch-pid: {wp_raw!r}"]}, indent=2) + "\n"
                )
                return 2

    res = apply_display_changes(
        payload,
        current_outputs=current_outputs,
        config_dir=env_info.config_dir,
        entrypoint=env_info.entrypoint,
        expected_sha256=expected_sha,
        timeout_seconds=float(args.timeout),
        watch_pid=watch_pid,
        backup_dir=debug_bdir,
        state_dir=getattr(args, "state_dir", None),
        reload_mode=reload_mode,
        dry_run=dry_run,
    )
    sys.stdout.write(json.dumps(res.to_dict(), indent=2) + "\n")
    sys.stdout.flush()
    return 1 if res.errors else 0


def _handle_settings_input(
    args: argparse.Namespace,
    cfg_dir: str | None,
    reload_override: str | None,
    debug_bdir: str | None,
) -> int:
    from backend.core.constants import OVERRIDES_FILENAME, SHA256_ABSENT
    from backend.editor.backups import compute_file_sha256
    from backend.settings.input.apply_flow import (
        apply_input_changes,
        confirm_input_changes,
        get_input_state,
        revert_input_changes,
    )
    from backend.settings.input.devices import probe_devices

    i_action = args.input_action

    if i_action == "confirm":
        res = confirm_input_changes(state_dir=getattr(args, "state_dir", None))
        sys.stdout.write(json.dumps(res, indent=2) + "\n")
        sys.stdout.flush()
        return 0 if res.get("ok") else 1

    if i_action == "revert":
        res = revert_input_changes(state_dir=getattr(args, "state_dir", None))
        sys.stdout.write(json.dumps(res, indent=2) + "\n")
        sys.stdout.flush()
        return 0 if res.get("ok") else 1

    if i_action == "state":
        st = get_input_state(
            config_dir=cfg_dir,
            entrypoint=args.entrypoint,
            no_live=args.no_live,
            state_dir=getattr(args, "state_dir", None),
        )
        sys.stdout.write(json.dumps(st, indent=2) + "\n")
        sys.stdout.flush()
        return 0

    # i_action == "apply"
    disc = discover_config(
        config_dir=cfg_dir,
        entrypoint=args.entrypoint,
        no_live=args.no_live,
    )
    env_info = disc.environment
    dry_run = not bool(args.apply)
    if args.apply and not args.scan_sha256:
        msg = "--apply requires --scan-sha256 <overrides_sha256_or_absent>."
        sys.stdout.write(json.dumps({"applied": False, "errors": [msg]}, indent=2) + "\n")
        return 2

    try:
        payload = _read_json_any(args.source, getattr(args, "inline_json", None))
    except (OSError, ValueError) as exc:
        sys.stdout.write(json.dumps({"applied": False, "errors": [str(exc)]}, indent=2) + "\n")
        return 1

    if not isinstance(payload, dict):
        sys.stdout.write(
            json.dumps({"applied": False, "errors": ["Input payload must be a JSON object"]}, indent=2)
            + "\n"
        )
        return 1

    opt_changes = payload.get("options") if "options" in payload or "devices" in payload else payload
    dev_changes = payload.get("devices") if isinstance(payload, dict) else None

    try:
        current_devices = probe_devices() if dev_changes else None
    except Exception as exc:
        sys.stdout.write(json.dumps({"applied": False, "errors": [str(exc)]}, indent=2) + "\n")
        return 1

    ov_path = os.path.join(env_info.config_dir, OVERRIDES_FILENAME)
    cur_sha = compute_file_sha256(ov_path) if os.path.isfile(ov_path) else SHA256_ABSENT
    expected_sha = args.scan_sha256 if args.scan_sha256 else cur_sha
    if args.no_live:
        reload_mode = "none"
    elif reload_override is not None:
        reload_mode = reload_override
    else:
        reload_mode = "config-only"

    watch_pid: int | None = None
    if getattr(args, "watch_pid", None) is not None:
        wp_raw = str(args.watch_pid).strip().lower()
        if wp_raw == "ppid":
            watch_pid = os.getppid()
        else:
            try:
                watch_pid = int(wp_raw)
            except ValueError:
                sys.stdout.write(
                    json.dumps({"applied": False, "errors": [f"Invalid --watch-pid: {wp_raw!r}"]}, indent=2) + "\n"
                )
                return 2

    res = apply_input_changes(
        opt_changes if isinstance(opt_changes, dict) else {},
        device_changes=dev_changes,
        current_devices=current_devices,
        config_dir=env_info.config_dir,
        entrypoint=env_info.entrypoint,
        expected_sha256=expected_sha,
        timeout_seconds=float(args.timeout),
        watch_pid=watch_pid,
        backup_dir=debug_bdir,
        state_dir=getattr(args, "state_dir", None),
        reload_mode=reload_mode,
        dry_run=dry_run,
    )
    sys.stdout.write(json.dumps(res.to_dict(), indent=2) + "\n")
    sys.stdout.flush()
    return 1 if res.errors else 0


def _handle_settings_audio(args: argparse.Namespace) -> int:
    from backend.settings.audio.ops import (
        set_default_sink,
        set_default_source,
        set_sink_mute,
        set_sink_volume,
        set_source_mute,
        set_source_volume,
    )
    from backend.settings.audio.state import get_audio_state

    a_action = args.audio_action
    timeout = getattr(args, "timeout", 5.0)

    if a_action == "state":
        st = get_audio_state(timeout=timeout)
        sys.stdout.write(json.dumps(st, indent=2) + "\n")
        sys.stdout.flush()
        return 0

    if a_action in ("set-volume", "set-sink-volume", "set-source-volume"):
        kind = "source" if a_action == "set-source-volume" else getattr(args, "kind", "sink")
        fn = set_source_volume if kind == "source" else set_sink_volume
        res = fn(args.name, args.percent, max_percent=args.max_percent, timeout=timeout)
        sys.stdout.write(json.dumps(res, indent=2) + "\n")
        sys.stdout.flush()
        return 0 if res.get("ok") else 1

    if a_action in ("set-mute", "set-sink-mute", "set-source-mute"):
        kind = "source" if a_action == "set-source-mute" else getattr(args, "kind", "sink")
        fn = set_source_mute if kind == "source" else set_sink_mute
        res = fn(args.name, args.mode, timeout=timeout)
        sys.stdout.write(json.dumps(res, indent=2) + "\n")
        sys.stdout.flush()
        return 0 if res.get("ok") else 1

    # set-default, set-default-sink, set-default-source
    kind = "source" if a_action == "set-default-source" else getattr(args, "kind", "sink")
    fn = set_default_source if kind == "source" else set_default_sink
    res = fn(args.name, timeout=timeout)
    sys.stdout.write(json.dumps(res, indent=2) + "\n")
    sys.stdout.flush()
    return 0 if res.get("ok") else 1


def _handle_settings_bluetooth(args: argparse.Namespace) -> int:
    from backend.settings.bluetooth.ops import (
        connect_device,
        disconnect_device,
        pair_device,
        remove_device,
        scan_results,
        scan_start,
        scan_stop,
        set_alias,
        set_blocked,
        set_discoverable,
        set_pairable,
        set_powered,
        set_trusted,
    )
    from backend.settings.bluetooth.state import get_bluetooth_state

    b_action = args.bluetooth_action
    timeout = getattr(args, "timeout", 5.0)

    if b_action == "state":
        st = get_bluetooth_state(timeout=timeout)
        sys.stdout.write(json.dumps(st, indent=2) + "\n")
        sys.stdout.flush()
        return 0

    if b_action == "power":
        res = set_powered(args.state == "on", timeout=timeout)
    elif b_action == "pairable":
        res = set_pairable(args.state == "on", timeout=timeout)
    elif b_action == "discoverable":
        res = set_discoverable(
            args.state == "on",
            discoverable_timeout=args.discoverable_timeout,
            timeout=timeout,
        )
    elif b_action == "connect":
        res = connect_device(args.mac, timeout=timeout)
    elif b_action == "disconnect":
        res = disconnect_device(args.mac, timeout=timeout)
    elif b_action == "trust":
        res = set_trusted(args.mac, True, timeout=timeout)
    elif b_action == "untrust":
        res = set_trusted(args.mac, False, timeout=timeout)
    elif b_action == "block":
        res = set_blocked(args.mac, True, timeout=timeout)
    elif b_action == "unblock":
        res = set_blocked(args.mac, False, timeout=timeout)
    elif b_action == "alias":
        res = set_alias(args.mac, args.name, timeout=timeout)
    elif b_action == "remove":
        res = remove_device(args.mac, timeout=timeout)
    elif b_action == "pair":
        res = pair_device(args.mac, pair_timeout=int(timeout))
    elif b_action == "scan":
        if args.mode == "start":
            res = scan_start(timeout=timeout)
        elif args.mode == "stop":
            res = scan_stop(timeout=timeout)
        else:
            res = scan_results(timeout=timeout)
    else:
        res = {"ok": False, "error": f"Unknown bluetooth action: {b_action}"}

    sys.stdout.write(json.dumps(res, indent=2) + "\n")
    sys.stdout.flush()
    return 0 if res.get("ok") else 1


def _handle_settings_network(args: argparse.Namespace) -> int:
    from backend.settings.network.ops import (
        connect_new_wifi,
        connect_saved,
        disconnect,
        forget,
        rescan,
        set_autoconnect,
        set_ipv4_dns,
        set_metered,
        set_wifi_enabled,
    )
    from backend.settings.network.state import get_network_state

    n_action = args.network_action
    timeout = getattr(args, "timeout", 5.0)

    if n_action == "state":
        st = get_network_state(timeout=timeout)
        sys.stdout.write(json.dumps(st, indent=2) + "\n")
        sys.stdout.flush()
        return 0

    if n_action == "wifi":
        res = set_wifi_enabled(args.state == "on", timeout=timeout)
    elif n_action == "rescan":
        res = rescan(timeout=timeout)
    elif n_action == "connect":
        res = connect_saved(args.uuid, wait_timeout=timeout)
    elif n_action == "disconnect":
        res = disconnect(args.device, confirm=args.confirm, timeout=timeout)
    elif n_action == "join":
        pw: str | None = None
        if not sys.stdin.isatty():
            line = sys.stdin.readline().rstrip("\r\n")
            if line:
                pw = line
        res = connect_new_wifi(
            args.ssid,
            security=args.security,
            password=pw,
            wait_timeout=timeout,
        )
    elif n_action == "forget":
        res = forget(args.uuid, confirm=args.confirm, timeout=timeout)
    elif n_action == "autoconnect":
        res = set_autoconnect(args.uuid, args.state == "on", timeout=timeout)
    elif n_action == "metered":
        res = set_metered(args.uuid, args.value, timeout=timeout)
    elif n_action == "dns":
        res = set_ipv4_dns(args.uuid, args.servers, timeout=timeout)
    else:
        res = {"ok": False, "error": f"Unknown network action: {n_action}"}

    sys.stdout.write(json.dumps(res, indent=2) + "\n")
    sys.stdout.flush()
    return 0 if res.get("ok") else 1


def _handle_settings_themes(args: argparse.Namespace) -> int:
    from backend.settings.themes.ops import (
        open_wallpaper_picker,
        set_cursor,
        set_gtk_theme,
        set_icon_theme,
        set_qt,
    )
    from backend.settings.themes.state import get_themes_state

    t_action = args.themes_action
    timeout = getattr(args, "timeout", 5.0)

    if t_action == "state":
        st = get_themes_state(timeout=timeout)
        sys.stdout.write(json.dumps(st, indent=2) + "\n")
        sys.stdout.flush()
        return 0

    if t_action == "gtk":
        res = set_gtk_theme(args.name, timeout=timeout)
    elif t_action == "icons":
        res = set_icon_theme(args.name, timeout=timeout)
    elif t_action == "cursor":
        res = set_cursor(args.name, size=args.size, timeout=timeout)
    elif t_action == "qt":
        res = set_qt(
            style=args.style,
            icon_theme=args.icons,
            color_scheme_path=args.colors,
            timeout=timeout,
        )
    elif t_action == "wallpaper":
        res = open_wallpaper_picker()
    else:
        res = {"ok": False, "error": f"Unknown themes action: {t_action}"}

    sys.stdout.write(json.dumps(res, indent=2) + "\n")
    sys.stdout.flush()
    return 0 if res.get("ok") else 1


def _handle_settings_power(args: argparse.Namespace, backup_dir: str | None = None) -> int:
    from backend.settings.power.ops import set_epp, set_idle_timeouts, set_turbo
    from backend.settings.power.state import get_power_state

    p_action = args.power_action
    timeout = getattr(args, "timeout", 5.0)

    if p_action == "state":
        st = get_power_state(timeout=timeout)
        sys.stdout.write(json.dumps(st, indent=2) + "\n")
        sys.stdout.flush()
        return 0

    if p_action == "epp":
        res = set_epp(args.value, timeout=timeout)
    elif p_action == "turbo":
        res = set_turbo(args.mode == "on", timeout=timeout)
    elif p_action == "idle":
        changes: dict[str, Any] = {}
        for pair in getattr(args, "pairs", []) or []:
            if "=" not in pair:
                res = {"ok": False, "error": f"Expected role=seconds pair, got {pair!r}"}
                sys.stdout.write(json.dumps(res, indent=2) + "\n")
                sys.stdout.flush()
                return 1
            k, v = pair.split("=", 1)
            changes[k.strip()] = v.strip()
        if getattr(args, "dim_sec", None) is not None:
            changes["dim"] = args.dim_sec
        if getattr(args, "lock_sec", None) is not None:
            changes["lock"] = args.lock_sec
        if getattr(args, "dpms_sec", None) is not None:
            changes["dpms"] = args.dpms_sec
        res = set_idle_timeouts(changes, backup_dir=backup_dir, timeout=timeout)
    else:
        res = {"ok": False, "error": f"Unknown power action: {p_action}"}

    sys.stdout.write(json.dumps(res, indent=2) + "\n")
    sys.stdout.flush()
    return 0 if res.get("ok") else 1


def _handle_settings_system(args: argparse.Namespace) -> int:
    from backend.settings.power.state import get_system_info

    timeout = getattr(args, "timeout", 5.0)
    info = get_system_info(timeout=timeout)
    sys.stdout.write(json.dumps(info, indent=2) + "\n")
    sys.stdout.flush()
    return 0


def _handle_settings_keyboard(args: argparse.Namespace) -> int:
    from backend.settings.keyboard.ops import open_hks
    from backend.settings.keyboard.state import get_keyboard_state

    k_action = args.keyboard_action
    timeout = getattr(args, "timeout", 5.0)

    if k_action == "state":
        st = get_keyboard_state(timeout=timeout)
        sys.stdout.write(json.dumps(st, indent=2) + "\n")
        sys.stdout.flush()
        return 0

    if k_action == "open":
        res = open_hks(timeout=timeout)
    else:
        res = {"ok": False, "error": f"Unknown keyboard action: {k_action}"}

    sys.stdout.write(json.dumps(res, indent=2) + "\n")
    sys.stdout.flush()
    return 0 if res.get("ok") else 1


def _handle_settings_backups(args: argparse.Namespace, backup_dir: str | None = None) -> int:
    from backend.settings.backups_ops import diff_backup, list_enriched_backups, safe_restore_backup

    b_action = getattr(args, "backups_action", "")
    if b_action == "list":
        try:
            items = list_enriched_backups(path=getattr(args, "path", None), backup_dir=backup_dir)
            res: dict[str, Any] = {"ok": True, "backups": items, "count": len(items)}
        except BackupError as exc:
            res = {"ok": False, "backups": [], "error": str(exc)}
    elif b_action == "diff":
        try:
            res = diff_backup(args.backup_id, backup_dir=backup_dir)
        except BackupError as exc:
            res = {"ok": False, "id": args.backup_id, "error": str(exc)}
    elif b_action == "restore":
        apply_flag = bool(getattr(args, "apply", False)) and not bool(getattr(args, "dry_run", False))
        reload_flag = not bool(getattr(args, "no_reload", False))
        res = safe_restore_backup(
            args.backup_id,
            apply=apply_flag,
            reload=reload_flag,
            force=bool(getattr(args, "force", False)),
            expected_sha256=getattr(args, "expected_sha256", None),
            backup_dir=backup_dir,
            config_dir=getattr(args, "config_dir", None),
            entrypoint=getattr(args, "entrypoint", None),
        )
    else:
        res = {"ok": False, "error": f"Unknown backups action: {b_action}"}

    sys.stdout.write(json.dumps(res, indent=2, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0 if res.get("ok") else 1


def _handle_settings(args: argparse.Namespace) -> int:
    from backend.core.constants import OVERRIDES_FILENAME, SHA256_ABSENT
    from backend.editor.backups import compute_file_sha256
    from backend.settings.commit import commit_settings, reset_settings
    from backend.settings.preview import PreviewValidationError, preview_settings, revert_preview
    from backend.settings.state import current_state

    cfg_dir, reload_override, debug_bdir = _resolve_settings_debug_overrides(args)
    action = args.settings_action

    if action == "audio":
        return _handle_settings_audio(args)

    if action == "bluetooth":
        return _handle_settings_bluetooth(args)

    if action == "network":
        return _handle_settings_network(args)

    if action == "themes":
        return _handle_settings_themes(args)

    if action == "power":
        return _handle_settings_power(args, backup_dir=debug_bdir)

    if action == "system":
        return _handle_settings_system(args)

    if action == "keyboard":
        return _handle_settings_keyboard(args)

    if action == "backups":
        return _handle_settings_backups(args, backup_dir=debug_bdir)

    if action == "display":
        return _handle_settings_display(args, cfg_dir, reload_override, debug_bdir)

    if action == "input":
        return _handle_settings_input(args, cfg_dir, reload_override, debug_bdir)

    if action == "state":
        st = current_state(
            config_dir=cfg_dir,
            entrypoint=args.entrypoint,
            no_live=args.no_live,
        )
        sys.stdout.write(json.dumps(st, indent=2) + "\n")
        sys.stdout.flush()
        return 0

    if action == "preview":
        if reload_override == "none":
            try:
                payload = _read_json_source(args.source, getattr(args, "inline_json", None))
                from backend.settings.preview import validate_changes
                validate_changes(payload)
            except (OSError, ValueError, PreviewValidationError) as exc:
                sys.stdout.write(json.dumps({"ok": False, "error": str(exc)}, indent=2) + "\n")
                return 1
            sys.stdout.write(json.dumps({"ok": True, "rendered": "", "skipped_reload_mode": "none"}, indent=2) + "\n")
            sys.stdout.flush()
            return 0
        try:
            payload = _read_json_source(args.source, getattr(args, "inline_json", None))
            res = preview_settings(payload)
        except (OSError, ValueError, PreviewValidationError) as exc:
            sys.stdout.write(json.dumps({"ok": False, "error": str(exc)}, indent=2) + "\n")
            return 1
        sys.stdout.write(json.dumps(res, indent=2) + "\n")
        sys.stdout.flush()
        return 0 if res.get("ok") else 1

    if action == "revert-preview":
        if reload_override == "none":
            sys.stdout.write(json.dumps({"ok": True, "skipped_reload_mode": "none"}, indent=2) + "\n")
            sys.stdout.flush()
            return 0
        res = revert_preview()
        sys.stdout.write(json.dumps(res, indent=2) + "\n")
        sys.stdout.flush()
        return 0 if res.get("ok") else 1

    disc = discover_config(
        config_dir=cfg_dir,
        entrypoint=args.entrypoint,
        no_live=args.no_live,
    )
    env_info = disc.environment
    dry_run = not bool(args.apply)
    if args.apply and not args.scan_sha256:
        msg = "--apply requires --scan-sha256 <overrides_sha256_or_absent>."
        sys.stdout.write(json.dumps({"applied": False, "errors": [msg]}, indent=2) + "\n")
        return 2

    ov_path = os.path.join(env_info.config_dir, OVERRIDES_FILENAME)
    cur_sha = compute_file_sha256(ov_path) if os.path.isfile(ov_path) else SHA256_ABSENT
    expected_sha = args.scan_sha256 if args.scan_sha256 else cur_sha
    if args.no_live:
        reload_mode = "none"
    elif reload_override is not None:
        reload_mode = reload_override
    else:
        reload_mode = "config-only"

    if action == "commit":
        try:
            payload = _read_json_source(args.source, getattr(args, "inline_json", None))
        except (OSError, ValueError) as exc:
            sys.stdout.write(json.dumps({"applied": False, "errors": [str(exc)]}, indent=2) + "\n")
            return 1
        if "changes" in payload or "resets" in payload:
            changes = payload.get("changes") or {}
            resets = payload.get("resets") or []
        else:
            changes = payload
            resets = []
        res = commit_settings(
            changes,
            resets=resets,
            config_dir=env_info.config_dir,
            entrypoint=env_info.entrypoint,
            expected_sha256=expected_sha,
            backup_dir=debug_bdir,
            reload_mode=reload_mode,
            dry_run=dry_run,
        )
    else:
        res = reset_settings(
            section=args.section,
            option_id=args.option_id,
            config_dir=env_info.config_dir,
            entrypoint=env_info.entrypoint,
            expected_sha256=expected_sha,
            backup_dir=debug_bdir,
            reload_mode=reload_mode,
            dry_run=dry_run,
        )

    sys.stdout.write(json.dumps(res.to_dict(), indent=2) + "\n")
    sys.stdout.flush()
    return 1 if res.errors else 0


def _handle_migrate_data(args: argparse.Namespace) -> int:
    from backend.core.data_migration import migrate_data

    res = migrate_data(apply=bool(args.apply))
    if getattr(args, "json_output", False):
        sys.stdout.write(json.dumps(res, indent=2) + "\n")
        sys.stdout.flush()
    else:
        if not res.get("ok"):
            sys.stderr.write(f"migrate-data: {res.get('error', 'failed')}\n")
        else:
            mode = "APPLIED" if res.get("applied") else "DRY-RUN"
            sys.stdout.write(f"migrate-data ({mode}):\n")
            for pair in res.get("pairs", []):
                sys.stdout.write(f"  [{pair['kind']}] {pair['source']} -> {pair['destination']} ({pair['status']}, {len(pair.get('files', {}))} file(s))\n")
            if res.get("undo_commands"):
                sys.stdout.write("Undo command(s):\n")
                for cmd in res["undo_commands"]:
                    sys.stdout.write(f"  {cmd}\n")
        sys.stdout.flush()
    return 0 if res.get("ok") else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    if not args.subcommand:
        parser.print_usage(sys.stderr)
        sys.stderr.write(
            "hyprdeck: error: subcommand required (choose from 'scan', 'summary', 'sidecar-template', 'conflicts', 'edit', 'backups', 'restore')\n"
        )
        return 2

    try:
        if args.subcommand != "recorder" and not getattr(args, "no_live", False):
            try:
                heal_submap()
            except Exception:
                pass
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

        if args.subcommand == "overrides":
            return _handle_overrides(args)

        if args.subcommand == "migrate-data":
            return _handle_migrate_data(args)

        if args.subcommand == "settings":
            return _handle_settings(args)
    except DiscoveryError as exc:
        sys.stderr.write(f"hyprdeck: error: {exc}\n")
        return 2
    except OSError as exc:
        sys.stderr.write(f"hyprdeck: error: {exc}\n")
        return 2
    except Exception as exc:  # pragma: no cover - defensive guard against raw tracebacks
        sys.stderr.write(f"hyprdeck: internal error: {exc}\n")
        return 2

    return 2


if __name__ == "__main__":
    sys.exit(main())
