"""Standard-library JSON Schema 2020-12 validator for HKS scan documents."""

from __future__ import annotations

import json
import os
import re
from typing import Any

DEFAULT_SCHEMA_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "shared",
        "schemas",
        "bindings.schema.json",
    )
)


class SchemaValidationError(Exception):
    """Raised when a document fails schema validation."""


def load_bindings_schema(schema_path: str | None = None) -> dict[str, Any]:
    path = schema_path or DEFAULT_SCHEMA_PATH
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Schema root must be a JSON object")
    return data


def _matches_type(value: Any, expected_type: str) -> bool:
    if expected_type == "null":
        return value is None
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return True


def _validate_node(value: Any, schema: dict[str, Any], path: str, errors: list[str]) -> None:
    if "type" in schema:
        t_spec = schema["type"]
        if isinstance(t_spec, list):
            if not any(_matches_type(value, t) for t in t_spec):
                errors.append(f"{path}: expected type in {t_spec}, got {type(value).__name__}")
                return
        elif isinstance(t_spec, str):
            if not _matches_type(value, t_spec):
                errors.append(f"{path}: expected type '{t_spec}', got {type(value).__name__}")
                return

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {value!r}")

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} not in enum {schema['enum']}")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            errors.append(f"{path}: string shorter than minLength {schema['minLength']}")
        if "pattern" in schema and not re.search(str(schema["pattern"]), value):
            errors.append(f"{path}: string {value!r} does not match pattern {schema['pattern']!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: number {value} < minimum {schema['minimum']}")

    if isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(value):
                _validate_node(item, item_schema, f"{path}[{idx}]", errors)

    if isinstance(value, dict):
        required = schema.get("required")
        if isinstance(required, list):
            for req_key in required:
                if req_key not in value:
                    errors.append(f"{path}: missing required property '{req_key}'")

        props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        add_props = schema.get("additionalProperties", True)

        for k, v in value.items():
            sub_path = f"{path}.{k}"
            if k in props:
                _validate_node(v, props[k], sub_path, errors)
            elif add_props is False:
                errors.append(f"{path}: unexpected additional property '{k}'")
            elif isinstance(add_props, dict):
                _validate_node(v, add_props, sub_path, errors)


def validate_scan_dict(
    data: dict[str, Any], schema: dict[str, Any] | None = None
) -> list[str]:
    """Validate a serialized scan dictionary against bindings.schema.json. Returns list of errors."""
    active_schema = schema if schema is not None else load_bindings_schema()
    errors: list[str] = []
    _validate_node(data, active_schema, "$", errors)
    return errors


def assert_valid_scan_dict(
    data: dict[str, Any], schema: dict[str, Any] | None = None
) -> None:
    """Raise SchemaValidationError if the scan dictionary violates bindings.schema.json."""
    errors = validate_scan_dict(data, schema=schema)
    if errors:
        raise SchemaValidationError(
            "Document failed schema validation:\n  - " + "\n  - ".join(errors)
        )
