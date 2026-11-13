"""Read-only sidecar override loader, validator, matcher, and template generator."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from backend.models.types import (
    VALID_CATEGORIES,
    BindRecord,
    DescriptionEffective,
    Diagnostic,
    SidecarStats,
)
from backend.parser.modifiers import resolve_modifier_tokens

ALLOWED_ROOT_KEYS = frozenset({"version", "overrides"})
ALLOWED_OVERRIDE_KEYS = frozenset({"match", "description", "category"})
ALLOWED_MATCH_KEYS = frozenset({"modifiers", "key", "submap", "dispatcher"})


class SidecarValidationError(Exception):
    """Raised when a sidecar file fails structural or semantic validation."""


@dataclass(slots=True)
class SidecarOverride:
    index: int
    modifiers: tuple[str, ...]
    key: str
    key_lower: str
    submap: str
    dispatcher: str | None
    description: str | None
    category: str | None


def resolve_sidecar_path(
    cli_path: str | None = None,
    no_sidecar: bool = False,
    env: dict[str, str] | None = None,
) -> str | None:
    """Resolve sidecar file path following strict precedence:
    --sidecar PATH > $HKS_SIDECAR > $XDG_CONFIG_HOME/hks/descriptions.json > ~/.config/hks/descriptions.json
    """
    if no_sidecar:
        return None
    if cli_path is not None and cli_path.strip() != "":
        return os.path.abspath(os.path.expanduser(cli_path.strip()))

    src_env = env if env is not None else os.environ
    env_sidecar = (
        src_env.get("HKS_SIDECAR", "").strip()
        or src_env.get("HKS_SIDECAR_PATH", "").strip()
    )
    if env_sidecar:
        return os.path.abspath(os.path.expanduser(env_sidecar))

    xdg = src_env.get("XDG_CONFIG_HOME", "").strip()
    if xdg:
        return os.path.abspath(os.path.join(os.path.expanduser(xdg), "hks", "descriptions.json"))

    home = src_env.get("HOME", "").strip() or os.path.expanduser("~")
    return os.path.abspath(os.path.join(home, ".config", "hks", "descriptions.json"))


def _strip_underscore_keys(obj: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in obj.items() if not str(k).startswith("_")}


def validate_sidecar_data(data: Any) -> list[SidecarOverride]:
    """Validate parsed JSON sidecar payload and return normalized SidecarOverride items."""
    if not isinstance(data, dict):
        raise SidecarValidationError("Sidecar root must be a JSON object")

    root = _strip_underscore_keys(data)
    unknown_root = set(root.keys()) - ALLOWED_ROOT_KEYS
    if unknown_root:
        raise SidecarValidationError(
            f"Unknown root key(s) in sidecar: {', '.join(sorted(unknown_root))}"
        )

    version = root.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version != 1:
        raise SidecarValidationError(f"Unsupported or missing sidecar version: {version!r} (expected 1)")

    raw_overrides = root.get("overrides")
    if not isinstance(raw_overrides, list):
        raise SidecarValidationError("Sidecar 'overrides' must be a list")

    overrides: list[SidecarOverride] = []
    for idx, item in enumerate(raw_overrides):
        if not isinstance(item, dict):
            raise SidecarValidationError(f"Override at index {idx} must be an object")

        ov = _strip_underscore_keys(item)
        unknown_ov = set(ov.keys()) - ALLOWED_OVERRIDE_KEYS
        if unknown_ov:
            raise SidecarValidationError(
                f"Unknown key(s) in override[{idx}]: {', '.join(sorted(unknown_ov))}"
            )

        raw_match = ov.get("match")
        if not isinstance(raw_match, dict):
            raise SidecarValidationError(f"Override[{idx}] is missing required object 'match'")

        match_obj = _strip_underscore_keys(raw_match)
        unknown_match = set(match_obj.keys()) - ALLOWED_MATCH_KEYS
        if unknown_match:
            raise SidecarValidationError(
                f"Unknown key(s) in override[{idx}].match: {', '.join(sorted(unknown_match))}"
            )

        raw_mods = match_obj.get("modifiers", [])
        if not isinstance(raw_mods, list) or not all(isinstance(m, str) for m in raw_mods):
            raise SidecarValidationError(
                f"Override[{idx}].match.modifiers must be a list of strings"
            )
        parsed_mods = resolve_modifier_tokens(raw_mods)
        if parsed_mods.unknown_tokens:
            raise SidecarValidationError(
                f"Unknown modifier(s) in override[{idx}].match.modifiers: {', '.join(parsed_mods.unknown_tokens)}"
            )

        raw_key = match_obj.get("key")
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise SidecarValidationError(
                f"Override[{idx}].match.key must be a non-empty string"
            )
        clean_key = raw_key.strip()

        raw_submap = match_obj.get("submap", "")
        if not isinstance(raw_submap, str):
            raise SidecarValidationError(f"Override[{idx}].match.submap must be a string")

        raw_dsp = match_obj.get("dispatcher")
        clean_dsp: str | None = None
        if raw_dsp is not None:
            if not isinstance(raw_dsp, str) or not raw_dsp.strip():
                raise SidecarValidationError(
                    f"Override[{idx}].match.dispatcher must be a non-empty string when provided"
                )
            clean_dsp = raw_dsp.strip()

        desc = ov.get("description")
        if desc is not None and not isinstance(desc, str):
            raise SidecarValidationError(f"Override[{idx}].description must be a string")

        cat = ov.get("category")
        if cat is not None:
            if not isinstance(cat, str):
                raise SidecarValidationError(f"Override[{idx}].category must be a string")
            if cat not in VALID_CATEGORIES:
                raise SidecarValidationError(
                    f"Unknown category {cat!r} in override[{idx}] (must be one of {', '.join(VALID_CATEGORIES)})"
                )

        if desc is None and cat is None:
            raise SidecarValidationError(
                f"Override[{idx}] must specify at least one of 'description' or 'category'"
            )

        overrides.append(
            SidecarOverride(
                index=idx,
                modifiers=tuple(parsed_mods.modifiers),
                key=clean_key,
                key_lower=clean_key.lower(),
                submap=raw_submap,
                dispatcher=clean_dsp,
                description=desc,
                category=cat,
            )
        )

    return overrides


def _dispatcher_matches(bind_dsp_path: str, filter_dsp: str) -> bool:
    full = bind_dsp_path.strip()
    leaf = full.rsplit(".", 1)[-1]
    return filter_dsp == full or filter_dsp == leaf


def apply_sidecar_overrides(
    binds: list[BindRecord],
    overrides: list[SidecarOverride],
    disabled_binds: list[DisabledBindRecord] | None = None,
    sidecar_path: str | None = None,
) -> tuple[int, int, list[Diagnostic]]:
    """Apply validated sidecar overrides to binds in-place and return (matched, unmatched, diagnostics)."""
    diagnostics: list[Diagnostic] = []
    matched_count = 0
    unmatched_count = 0

    for ov in overrides:
        matched_binds: list[BindRecord] = []
        for b in binds:
            if frozenset(b.modifiers) != frozenset(ov.modifiers):
                continue
            if b.key.strip().lower() != ov.key_lower:
                continue
            if (b.submap or "") != ov.submap:
                continue
            if ov.dispatcher is not None and not _dispatcher_matches(
                b.dispatcher.path, ov.dispatcher
            ):
                continue
            matched_binds.append(b)

        if not matched_binds:
            matched_disabled = False
            if disabled_binds:
                from backend.describe.sidecar_store import match_override_to_disabled
                ov_dict = {
                    "modifiers": ov.modifiers,
                    "key": ov.key,
                    "submap": ov.submap,
                    "dispatcher": ov.dispatcher,
                }
                for d in disabled_binds:
                    if match_override_to_disabled(ov_dict, d):
                        if ov.description is not None:
                            d.description_hint = ov.description
                        matched_disabled = True
            if matched_disabled:
                matched_count += 1
                continue

            unmatched_count += 1
            diagnostics.append(
                Diagnostic(
                    level="warning",
                    code="sidecar_unmatched",
                    message=(
                        f"Sidecar override at index {ov.index} "
                        f"({'+'.join([*ov.modifiers, ov.key])}) did not match any bind"
                    ),
                    file=sidecar_path,
                    line=None,
                )
            )
            continue

        matched_count += 1
        if len(matched_binds) > 1 and ov.dispatcher is None:
            ids_str = ", ".join(b.id for b in matched_binds)
            diagnostics.append(
                Diagnostic(
                    level="info",
                    code="sidecar_ambiguous",
                    message=(
                        f"Sidecar override at index {ov.index} matched {len(matched_binds)} binds "
                        f"without a 'dispatcher' filter: {ids_str}"
                    ),
                    file=sidecar_path,
                    line=None,
                )
            )

        for b in matched_binds:
            if ov.description is not None:
                b.description_effective = DescriptionEffective(
                    text=ov.description,
                    source="sidecar",
                    generic=False,
                )
            if ov.category is not None:
                b.category = ov.category
                b.category_source = "sidecar"

    return matched_count, unmatched_count, diagnostics


def load_and_apply_sidecar(
    binds: list[BindRecord],
    disabled_binds: list[DisabledBindRecord] | None = None,
    cli_path: str | None = None,
    no_sidecar: bool = False,
    env: dict[str, str] | None = None,
) -> tuple[SidecarStats, list[Diagnostic]]:
    """Resolve, read, validate, and apply sidecar overrides to `binds`.

    Never writes or creates any file. Missing files are silently ignored.
    Invalid sidecar files emit `sidecar_invalid` and leave `binds` untouched.
    """
    path = resolve_sidecar_path(cli_path=cli_path, no_sidecar=no_sidecar, env=env)
    if path is None or not os.path.isfile(path):
        return (
            SidecarStats(path=path, loaded=False, overrides=0, matched=0, unmatched=0),
            [],
        )

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_text = f.read()
        parsed = json.loads(raw_text)
        overrides = validate_sidecar_data(parsed)
    except (OSError, json.JSONDecodeError, SidecarValidationError) as exc:
        return (
            SidecarStats(path=path, loaded=False, overrides=0, matched=0, unmatched=0),
            [
                Diagnostic(
                    level="error",
                    code="sidecar_invalid",
                    message=f"Invalid sidecar file '{path}': {exc}",
                    file=path,
                    line=None,
                )
            ],
        )

    matched, unmatched, diags = apply_sidecar_overrides(
        binds=binds,
        overrides=overrides,
        disabled_binds=disabled_binds,
        sidecar_path=path,
    )
    return (
        SidecarStats(
            path=path,
            loaded=True,
            overrides=len(overrides),
            matched=matched,
            unmatched=unmatched,
        ),
        diags,
    )


def build_sidecar_template(
    binds: list[BindRecord] | None = None,
    include_all: bool = False,
) -> dict[str, Any]:
    """Build a valid sidecar dictionary for `sidecar-template [--all]`."""
    if not include_all or binds is None:
        return {
            "_note": (
                "Hyprland Keybind Studio (HKS) sidecar overrides. "
                "Save to ~/.config/hks/descriptions.json or pass via --sidecar PATH. "
                "Keys starting with '_' are ignored by the validator."
            ),
            "version": 1,
            "overrides": [
                {
                    "_note": "Example override: customize description and/or category for a keybinding.",
                    "match": {
                        "modifiers": ["SUPER"],
                        "key": "Q",
                        "submap": "",
                        "dispatcher": "exec_cmd",
                    },
                    "description": "Open Firefox",
                    "category": "Apps",
                }
            ],
        }

    seen_keys: set[tuple[frozenset[str], str, str, str]] = set()
    overrides: list[dict[str, Any]] = []
    for b in binds:
        dedup_key = (
            frozenset(b.modifiers),
            b.key.strip().lower(),
            b.submap or "",
            b.dispatcher.path.strip(),
        )
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)
        overrides.append(
            {
                "_note": f"{os.path.basename(b.source_file)}:{b.source_line}",
                "match": {
                    "modifiers": list(b.modifiers),
                    "key": b.key,
                    "submap": b.submap or "",
                    "dispatcher": b.dispatcher.path,
                },
                "description": b.description_effective.text,
                "category": b.category,
            }
        )

    return {
        "_note": (
            "Hyprland Keybind Studio (HKS) full sidecar template (--all). "
            "Edit descriptions/categories as desired and save to ~/.config/hks/descriptions.json."
        ),
        "version": 1,
        "overrides": overrides,
    }
