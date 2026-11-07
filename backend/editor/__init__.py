"""Safe configuration edit engine for Hyprland Keybind Studio (Phase 4a)."""

from __future__ import annotations

from backend.editor.apply import (
    ApplyResult,
    apply_edit,
    resolve_uncomment_op,
)
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
from backend.editor.validator import (
    BindSetComparison,
    RecorderVerificationError,
    VerifyResult,
    bind_semantic_signature,
    compare_bind_sets,
    stage_candidate_config,
    verify_with_hyprland,
    verify_with_recorder,
)

__all__ = [
    "ApplyResult",
    "BackupConflictError",
    "BackupError",
    "BackupRecord",
    "BindSetComparison",
    "EditConflict",
    "EditError",
    "EditOp",
    "HYPRLANG_DISABLED_PREFIX",
    "LUA_DISABLED_PREFIX",
    "LineMismatch",
    "NotEditableError",
    "RecorderVerificationError",
    "VALID_EDIT_KINDS",
    "VerifyResult",
    "apply_edit",
    "apply_ops_to_text",
    "atomic_write_bytes",
    "bind_semantic_signature",
    "build_op_for_bind",
    "compare_bind_sets",
    "compute_file_sha256",
    "create_backup",
    "generate_unified_diff",
    "list_backups",
    "resolve_backup_dir",
    "resolve_uncomment_op",
    "restore_backup",
    "stage_candidate_config",
    "verify_with_hyprland",
    "verify_with_recorder",
]
