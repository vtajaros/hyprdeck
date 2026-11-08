"""Conflict detection for Hyprland Keybind Studio (HKS)."""

from __future__ import annotations

from backend.models.types import BindRecord, ConflictRecord


KEY_ALIASES: dict[str, str] = {
    "enter": "return",
    "return": "return",
    "`": "grave",
    "grave": "grave",
    "esc": "escape",
    "escape": "escape",
    "slash": "/",
    "/": "/",
    "backslash": "\\",
    "\\": "\\",
    "minus": "-",
    "-": "-",
    "equal": "=",
    "=": "=",
    "space": "space",
    "tab": "tab",
}


def normalize_key(k: str) -> str:
    """Normalize key string and aliases to a canonical lower-case representation."""
    clean = k.strip().lower()
    return KEY_ALIASES.get(clean, clean)


def detect_conflicts(binds: list[BindRecord]) -> list[ConflictRecord]:
    """Detect and classify conflicting keybindings across parsed binds.

    Grouping key:
      (submap or "", modmask, normalize_key(key), flags.release, flags.long_press)

    Rules:
    - Press and release binds on the same key are never grouped together.
    - Long-press binds are partitioned separately from standard press binds.
    - Only groups with size >= 2 produce a conflict.
    - If at least two binds in the group share identical dispatcher.path AND
      dispatcher.arg_summary, kind is 'duplicate' and severity is 'warning'.
    - Otherwise, kind is 'multiple_actions' and severity is 'info'.
    - If a group contains some duplicate and some distinct actions, kind is 'duplicate'.
    - Populates each matching bind's `conflict_ids` in-place.
    """
    groups: dict[tuple[str, int, str, bool, bool], list[BindRecord]] = {}

    for b in binds:
        # Reset or initialize conflict_ids list
        if not hasattr(b, "conflict_ids") or b.conflict_ids is None:
            b.conflict_ids = []

        grp_key = (
            b.submap or "",
            b.modmask,
            normalize_key(b.key),
            bool(b.flags.get("release", False)),
            bool(b.flags.get("long_press", False)),
        )
        if grp_key not in groups:
            groups[grp_key] = []
        groups[grp_key].append(b)

    conflicts: list[ConflictRecord] = []
    conflict_idx = 1

    for group_binds in groups.values():
        if len(group_binds) < 2:
            continue

        conflict_id = f"conflict-{conflict_idx}"
        conflict_idx += 1

        actions_seen: set[tuple[str, str]] = set()
        has_duplicate = False
        for b in group_binds:
            action_key = (b.dispatcher.path.strip(), b.dispatcher.arg_summary.strip())
            if action_key in actions_seen:
                has_duplicate = True
            actions_seen.add(action_key)

        if has_duplicate:
            kind = "duplicate"
            severity = "warning"
        else:
            kind = "multiple_actions"
            severity = "info"

        first_bind = group_binds[0]
        bind_ids = [b.id for b in group_binds]
        sources = [
            {"file": b.source_file, "line": b.source_line}
            for b in group_binds
        ]

        for b in group_binds:
            if conflict_id not in b.conflict_ids:
                b.conflict_ids.append(conflict_id)

        conflicts.append(
            ConflictRecord(
                id=conflict_id,
                kind=kind,
                severity=severity,
                submap=first_bind.submap or "",
                modifiers=list(first_bind.modifiers),
                key=first_bind.key,
                bind_ids=bind_ids,
                sources=sources,
            )
        )

    return conflicts


def check_candidate_conflict(
    binds: list[BindRecord],
    mods: list[str] | str | int,
    key: str,
    submap: str = "",
    exclude_id: str | None = None,
    disabled_binds: list[Any] | None = None,
) -> dict[str, Any]:
    """Fast pre-flight check of candidate shortcut against existing active and disabled binds."""
    import re
    from backend.parser.modifiers import resolve_modifier_tokens

    if isinstance(mods, int):
        target_modmask = mods
    elif isinstance(mods, str) and mods.strip().isdigit():
        target_modmask = int(mods.strip())
    else:
        if isinstance(mods, str):
            tokens = [t.strip() for t in re.split(r"[,+\s]+", mods) if t.strip()]
        else:
            tokens = list(mods)
        parsed = resolve_modifier_tokens(tokens)
        target_modmask = parsed.modmask

    target_key = normalize_key(key)
    target_submap = (submap or "").strip()

    conflicts: list[dict[str, Any]] = []
    for b in binds:
        if exclude_id and b.id == exclude_id:
            continue
        if (b.submap or "").strip() != target_submap:
            continue
        if b.modmask != target_modmask:
            continue
        if normalize_key(b.key) != target_key:
            continue

        desc = ""
        if hasattr(b, "description_effective") and b.description_effective:
            desc = getattr(b.description_effective, "text", "")
        if not desc:
            d_path = b.dispatcher.path if b.dispatcher else ""
            d_arg = b.dispatcher.arg_summary if (b.dispatcher and b.dispatcher.arg_summary) else ""
            desc = f"{d_path} {d_arg}".strip()

        conflicts.append({
            "id": b.id,
            "shortcut": b.keys_raw or ((" + ".join(b.modifiers) + " + " if b.modifiers else "") + b.key),
            "description": desc,
            "file": b.source_file,
            "line": b.source_line,
            "kind": "conflicting",
        })

    disabled_held = False
    matched_disabled: list[dict[str, Any]] = []
    if disabled_binds:
        for d in disabled_binds:
            hint = getattr(d, "key_hint", "") or getattr(d, "original_text", "")
            if not hint:
                continue
            # Extract key and mods from hint
            tokens = [t.strip() for t in re.split(r"[,+\s]+", hint) if t.strip()]
            if not tokens:
                continue
            d_key = normalize_key(tokens[-1])
            if d_key != target_key:
                continue
            d_parsed = resolve_modifier_tokens(tokens[:-1])
            if d_parsed.modmask == target_modmask:
                disabled_held = True
                matched_disabled.append({
                    "id": getattr(d, "id", ""),
                    "key_hint": hint,
                    "file": getattr(d, "file", ""),
                    "line": getattr(d, "line", 0),
                    "description": getattr(d, "description_hint", "") or "",
                })

    return {
        "ok": True,
        "has_conflicts": len(conflicts) > 0,
        "conflicts": conflicts,
        "disabled_held": disabled_held,
        "disabled_binds": matched_disabled,
    }
