"""Validation package for Hyprland Keybind Studio."""

from backend.validation.schema_validator import (
    SchemaValidationError,
    assert_valid_scan_dict,
    load_bindings_schema,
    validate_scan_dict,
)

__all__ = [
    "SchemaValidationError",
    "assert_valid_scan_dict",
    "load_bindings_schema",
    "validate_scan_dict",
]
