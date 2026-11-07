"""Data models for Hyprland Keybind Studio (HKS) Phase 1."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Diagnostic:
    level: str  # "info" | "warning" | "error"
    code: str
    message: str
    file: str | None = None
    line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "file": self.file,
            "level": self.level,
            "line": self.line,
            "message": self.message,
        }


@dataclass(slots=True)
class ShadowedFile:
    path: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "reason": self.reason,
        }


@dataclass(slots=True)
class EnvironmentInfo:
    config_dir: str
    entrypoint: str
    language: str  # "lua" | "hyprlang"
    detected_by: str  # "file-precedence" | "live-hyprctl"
    entrypoint_source: str = "auto"  # "auto" | "explicit"
    shadowed: list[ShadowedFile] = field(default_factory=list)
    hyprland_version: str | None = None
    python: str = ""

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "config_dir": self.config_dir,
            "detected_by": self.detected_by,
            "entrypoint": self.entrypoint,
            "entrypoint_source": self.entrypoint_source,
            "hyprland_version": self.hyprland_version,
            "language": self.language,
            "python": self.python,
            "shadowed": [s.to_dict() for s in self.shadowed],
        }
        return res


@dataclass(slots=True)
class FileRecord:
    path: str
    real_path: str
    role: str  # "entrypoint" | "loaded"
    sha256: str
    line_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_count": self.line_count,
            "path": self.path,
            "real_path": self.real_path,
            "role": self.role,
            "sha256": self.sha256,
        }


@dataclass(slots=True)
class TraceFrame:
    file: str
    line: int
    what: str
    istailcall: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "istailcall": self.istailcall,
            "line": self.line,
            "what": self.what,
        }


@dataclass(slots=True)
class DispatcherInfo:
    path: str
    args: list[Any] = field(default_factory=list)
    arg_summary: str = ""
    callback_line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "arg_summary": self.arg_summary,
            "args": self.args,
            "path": self.path,
        }
        if self.callback_line is not None:
            res["callback_line"] = self.callback_line
        return res


def default_flags() -> dict[str, bool]:
    return {
        "ignore_mods": False,
        "locked": False,
        "long_press": False,
        "mouse": False,
        "non_consuming": False,
        "release": False,
        "repeating": False,
        "transparent": False,
    }


VALID_CATEGORIES = (
    "Apps",
    "Windows",
    "Workspaces",
    "Media & Hardware",
    "System",
    "Mouse",
    "Other",
)


@dataclass(slots=True)
class DescriptionEffective:
    text: str
    source: str  # "sidecar" | "config" | "derived"
    generic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "generic": self.generic,
            "source": self.source,
            "text": self.text,
        }


@dataclass(slots=True)
class BindRecord:
    id: str
    language: str  # "lua" | "hyprlang"
    bind_type: str
    declared_via: str | None
    modifiers: list[str]
    modifiers_raw: str
    modmask: int
    key: str
    key_kind: str  # "keysym" | "mouse_button" | "keycode" | "mouse_wheel"
    keys_raw: str
    flags: dict[str, bool]
    flags_extra: dict[str, Any]
    description: str | None
    dispatcher: DispatcherInfo
    submap: str
    source_file: str
    source_line: int
    original_line: str
    original_line_number: int
    generated: bool
    occurrence: int
    occurrences_at_site: int
    trace: list[TraceFrame]
    parse_status: str  # "ok" | "partial" | "unsupported" | "unresolved"
    key_raw: str = ""
    args_raw: str = ""
    description_effective: DescriptionEffective = field(
        default_factory=lambda: DescriptionEffective(text="", source="derived", generic=True)
    )
    category: str = "Other"
    category_source: str = "derived"  # "sidecar" | "derived"
    conflict_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "args_raw": self.args_raw,
            "bind_type": self.bind_type,
            "category": self.category,
            "category_source": self.category_source,
            "conflict_ids": list(self.conflict_ids),
            "declared_via": self.declared_via,
            "description": self.description,
            "description_effective": self.description_effective.to_dict(),
            "dispatcher": self.dispatcher.to_dict(),
            "flags": dict(sorted(self.flags.items())),
            "flags_extra": dict(sorted(self.flags_extra.items())),
            "generated": self.generated,
            "id": self.id,
            "key": self.key,
            "key_kind": self.key_kind,
            "key_raw": self.key_raw or self.key,
            "keys_raw": self.keys_raw,
            "language": self.language,
            "modifiers": list(self.modifiers),
            "modifiers_raw": self.modifiers_raw,
            "modmask": self.modmask,
            "occurrence": self.occurrence,
            "occurrences_at_site": self.occurrences_at_site,
            "original_line": self.original_line,
            "original_line_number": self.original_line_number,
            "parse_status": self.parse_status,
            "source_file": self.source_file,
            "source_line": self.source_line,
            "submap": self.submap,
            "trace": [t.to_dict() for t in self.trace],
        }


@dataclass(slots=True)
class UnbindRecord:
    modifiers: list[str]
    modifiers_raw: str
    modmask: int
    key: str
    key_raw: str
    submap: str
    source_file: str
    source_line: int
    original_line: str
    parse_status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "key_raw": self.key_raw,
            "modifiers": list(self.modifiers),
            "modifiers_raw": self.modifiers_raw,
            "modmask": self.modmask,
            "original_line": self.original_line,
            "parse_status": self.parse_status,
            "source_file": self.source_file,
            "source_line": self.source_line,
            "submap": self.submap,
        }


@dataclass(slots=True)
class SandboxStats:
    instructions_used: int
    instruction_limit: int
    elapsed_ms: float
    cpu_limit_s: float
    wall_timeout_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu_limit_s": self.cpu_limit_s,
            "elapsed_ms": self.elapsed_ms,
            "instruction_limit": self.instruction_limit,
            "instructions_used": self.instructions_used,
            "wall_timeout_s": self.wall_timeout_s,
        }


@dataclass(slots=True)
class SidecarStats:
    path: str | None = None
    loaded: bool = False
    overrides: int = 0
    matched: int = 0
    unmatched: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "loaded": self.loaded,
            "matched": self.matched,
            "overrides": self.overrides,
            "path": self.path,
            "unmatched": self.unmatched,
        }


@dataclass(slots=True)
class ConflictStats:
    total: int = 0
    duplicate: int = 0
    multiple_actions: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "duplicate": self.duplicate,
            "multiple_actions": self.multiple_actions,
            "total": self.total,
        }


@dataclass(slots=True)
class ConflictRecord:
    id: str
    kind: str  # "duplicate" | "multiple_actions"
    severity: str  # "warning" | "info"
    submap: str
    modifiers: list[str]
    key: str
    bind_ids: list[str]
    sources: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "bind_ids": list(self.bind_ids),
            "id": self.id,
            "key": self.key,
            "kind": self.kind,
            "modifiers": list(self.modifiers),
            "severity": self.severity,
            "sources": [
                {"file": s["file"], "line": s["line"]}
                for s in self.sources
            ],
            "submap": self.submap,
        }


@dataclass(slots=True)
class StatsRecord:
    total_binds: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    by_dispatcher_path: dict[str, int] = field(default_factory=dict)
    flag_counts: dict[str, int] = field(default_factory=dict)
    by_modmask: dict[str, int] = field(default_factory=dict)
    generated_binds: int = 0
    partial: int = 0
    unsupported: int = 0
    unresolved: int = 0
    ignored_calls: dict[str, int] = field(default_factory=dict)
    ignored_keywords: dict[str, int] = field(default_factory=dict)
    sandbox: SandboxStats | None = None
    sidecar: SidecarStats = field(default_factory=SidecarStats)
    conflicts: ConflictStats = field(default_factory=ConflictStats)

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "by_dispatcher_path": dict(sorted(self.by_dispatcher_path.items())),
            "by_modmask": dict(sorted(self.by_modmask.items(), key=lambda kv: int(kv[0]))),
            "by_type": dict(sorted(self.by_type.items())),
            "conflicts": self.conflicts.to_dict(),
            "flag_counts": dict(sorted(self.flag_counts.items())),
            "generated_binds": self.generated_binds,
            "ignored_calls": dict(sorted(self.ignored_calls.items())),
            "ignored_keywords": dict(sorted(self.ignored_keywords.items())),
            "partial": self.partial,
            "sidecar": self.sidecar.to_dict(),
            "total_binds": self.total_binds,
            "unresolved": self.unresolved,
            "unsupported": self.unsupported,
        }
        if self.sandbox is not None:
            res["sandbox"] = self.sandbox.to_dict()
        return res


@dataclass(slots=True)
class ScanDocument:
    schema_version: int
    tool: dict[str, str]
    generated_at: str
    environment: EnvironmentInfo
    files: list[FileRecord]
    binds: list[BindRecord]
    unbinds: list[UnbindRecord]
    diagnostics: list[Diagnostic]
    stats: StatsRecord
    complete: bool
    conflicts: list[ConflictRecord] = field(default_factory=list)
    oracle: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "binds": [b.to_dict() for b in self.binds],
            "complete": self.complete,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "environment": self.environment.to_dict(),
            "files": [f.to_dict() for f in self.files],
            "generated_at": self.generated_at,
            "schema_version": self.schema_version,
            "stats": self.stats.to_dict(),
            "tool": dict(sorted(self.tool.items())),
            "unbinds": [u.to_dict() for u in self.unbinds],
        }
        if self.oracle is not None:
            res["oracle"] = self.oracle
        return res
