"""Validation package for Hyprland Keybind Studio."""

from backend.validation.oracle import (
    OracleReport,
    bind_record_to_tuple,
    compare_with_oracle,
    extract_live_short_dispatcher,
    extract_parser_short_dispatcher,
    format_oracle_stderr_summary,
    live_entry_to_tuple,
)
from backend.validation.schema_validator import (
    SchemaValidationError,
    assert_valid_scan_dict,
    load_bindings_schema,
    validate_scan_dict,
)

__all__ = [
    "OracleReport",
    "SchemaValidationError",
    "assert_valid_scan_dict",
    "bind_record_to_tuple",
    "compare_with_oracle",
    "extract_live_short_dispatcher",
    "extract_parser_short_dispatcher",
    "format_oracle_stderr_summary",
    "live_entry_to_tuple",
    "load_bindings_schema",
    "validate_scan_dict",
]
