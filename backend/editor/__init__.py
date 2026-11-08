"""Safe configuration edit engine for Hyprland Keybind Studio (Phase 4a)."""

from __future__ import annotations

from backend.editor.apply import (
    ApplyResult,
    apply_edit,
    make_expected_bind,
    resolve_insert_op,
    resolve_replace_op,
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
from backend.editor.codegen import (
    generate_hyprlang_bind,
    generate_lua_bind,
    validate_code_tokens,
)
from backend.editor.disabled import detect_disabled_binds
from backend.editor.dispatchers import (
    DISPATCHER_CATALOG,
    get_catalog,
    get_dispatcher_by_id,
    render_from_catalog,
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
from backend.editor.insert_policy import (
    HYPRLANG_ANCHOR,
    LUA_ANCHOR,
    InsertPlan,
    plan_insert_bind,
)
from backend.editor.recorder_submap import (
    enter as enter_submap,
    heal as heal_submap,
    leave as leave_submap,
    status as submap_status,
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
    "HYPRLANG_ANCHOR",
    "HYPRLANG_DISABLED_PREFIX",
    "LUA_ANCHOR",
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
    "detect_disabled_binds",
    "enter_submap",
    "generate_hyprlang_bind",
    "generate_lua_bind",
    "generate_unified_diff",
    "heal_submap",
    "leave_submap",
    "list_backups",
    "make_expected_bind",
    "plan_insert_bind",
    "resolve_backup_dir",
    "resolve_insert_op",
    "resolve_replace_op",
    "resolve_uncomment_op",
    "restore_backup",
    "stage_candidate_config",
    "submap_status",
    "validate_code_tokens",
    "verify_with_hyprland",
    "verify_with_recorder",
]
