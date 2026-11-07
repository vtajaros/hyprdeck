"""Conflict detection for Hyprland Keybind Studio (HKS)."""

from __future__ import annotations

from backend.models.types import BindRecord, ConflictRecord


def detect_conflicts(binds: list[BindRecord]) -> list[ConflictRecord]:
    """Detect and classify conflicting keybindings across parsed binds.

    Grouping key:
      (submap or "", modmask, key.lower(), flags.release, flags.long_press)

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
            b.key.strip().lower(),
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
