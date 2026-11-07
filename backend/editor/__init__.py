"""Safe configuration edit engine for Hyprland Keybind Studio (Phase 4a)."""

from __future__ import annotations

from backend.editor.backups import (
    BackupConflictError,
    BackupError,
    BackupRecord,
    atomic_write_bytes,
    compute_file_sha256,
    create_backup,
    list_backups,
    resolve_backup_dir,
    restore_backup,
)
from backend.editor.edit_plan import (
    HYPRLANG_DISABLED_PREFIX,
    LUA_DISABLED_PREFIX,
     VALID_EDIT_KINDS,
    EditConflict,
    EditError,
    EditOp,
    LineMismatch,
    NotEditableError,
    apply_ops_to_text,
    build_op_for_bind,
    generate_unified_diff,
)

__all__ = [
    "BackupConflictError",
    "BackupError",
    "BackupRecord",
    "EditConflict",
    "EditError",
    "EditOp",
    "HYPRLANG_DISABLED_PREFIX",
    "LUA_DISABLED_PREFIX",
    "LineMismatch",
    "NotEditableError",
    "VALID_EDIT_KINDS",
    "apply_ops_to_text",
    "atomic_write_bytes",
    "build_op_for_bind",
    "compute_file_sha256",
    "create_backup",
    "generate_unified_diff",
    "list_backups",
    "resolve_backup_dir",
    "restore_backup",
]
