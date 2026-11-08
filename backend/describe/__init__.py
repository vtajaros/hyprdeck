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
from backend.describe.sidecar_store import (
    SidecarCollisionError,
    SidecarStoreError,
    backup_sidecar_file,
    delete_override,
    list_orphans,
    migrate_override,
    save_override,
)

__all__ = [
    "SidecarCollisionError",
    "SidecarOverride",
    "SidecarStoreError",
    "SidecarValidationError",
    "apply_sidecar_overrides",
    "backup_sidecar_file",
    "build_sidecar_template",
    "delete_override",
    "derive_category",
    "derive_description",
    "list_orphans",
    "load_and_apply_sidecar",
    "migrate_override",
    "populate_bind_description",
    "populate_bind_descriptions",
    "resolve_sidecar_path",
    "save_override",
    "validate_sidecar_data",
]
