"""Description and category derivation package for HKS Phase 2a."""

from backend.describe.derive import (
    derive_category,
    derive_description,
    populate_bind_description,
    populate_bind_descriptions,
)
from backend.describe.sidecar import (
    SidecarOverride,
    SidecarValidationError,
    apply_sidecar_overrides,
    build_sidecar_template,
    load_and_apply_sidecar,
    resolve_sidecar_path,
    validate_sidecar_data,
)

__all__ = [
    "SidecarOverride",
    "SidecarValidationError",
    "apply_sidecar_overrides",
    "build_sidecar_template",
    "derive_category",
    "derive_description",
    "load_and_apply_sidecar",
    "populate_bind_description",
    "populate_bind_descriptions",
    "resolve_sidecar_path",
    "validate_sidecar_data",
]
