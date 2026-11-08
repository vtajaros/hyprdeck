# Hyprland Keybind Studio (HKS) — Phase 3b: Keybind Modification, Addition & Sidecar Persistence

**Status**: 100% Complete & Verified  
**Date**: November 8, 2026  
**Authors**: Antigravity Pair Programming Team

---

## 1. Executive Summary

Phase 3b completes the editing lifecycle in Hyprland Keybind Studio (HKS), advancing the application from disable/delete operations (Phase 3a/4a) into full keybinding modification, arbitrary additions, interactive shortcut recording, and persistent sidecar metadata synchronization.

### Key Milestones Delivered
- **Phase 3b-0**: End-to-end backend replace and insert verification, Lua/Hyprlang code generation (`backend/editor/codegen.py`), and insertion policy (`backend/editor/insert_policy.py`).
- **Phase 3b-1**: Interactive keybind recording coordinator (`backend/editor/recorder_submap.py`), Qt modifier bitmask mapping (`frontend/components/keymap.js`), and QML recorder component (`frontend/components/KeybindRecorder.qml`).
- **Phase 3b-2**: Data-driven dispatcher catalog (`backend/editor/dispatchers.py`), full keybind edit modal (`frontend/components/KeybindEditDialog.qml`), and live conflict detection service (`frontend/services/ConflictCheckService.qml`).
- **Phase 3b-3**: Arbitrary keybinding addition workflow with flag support (`locked`, `repeating`), candidate conflict checks, anchor placement, and atomic config write.
- **Phase 3b-4**: Persistent sidecar store (`backend/describe/sidecar_store.py`) with atomic writes, `fcntl` file locking, automatic override migration upon key replacement, orphan detection, and sidecar backup/undo integration.
- **Phase 3b Hardening**: Mock isolation verification, undo completeness across all mutation workflows, structured collision warning objects (`sidecar_warning`), and duplicate match sharing indicators in the UI.

---

## 2. Architecture & Design Decisions

### A. Submap Strategy & Safe Interception (Strategy A)
In Hyprland v0.57.1, entering an undeclared submap with no bound keys is rejected by the compositor. HKS resolves this via **Strategy A**:
1. When recording begins (`recorder enter`), HKS queries `hyprctl binds -j` to identify an unused media/hardware key from a candidate pool (`XF86Tools`, `XF86Launch5`–`XF86Launch9`, `XF86Explorer`, `XF86Shop`).
2. It dynamically registers the `hks_record` submap via `hyprctl eval` containing a dummy reset bind on that key.
3. It switches the active submap to `hks_record`, isolating keyboard focus so desktop shortcuts do not trigger while the user presses keys.
4. When recording finishes (`recorder leave`), HKS switches the submap back to `default`, unbinds the temporary dummy key, and verifies that the compositor returned to `default` submap.
5. In live verification, `hyprctl binds -j | jq length` before and after enter/leave is byte-identical (123 binds before, 123 binds after).

### B. Dual-Language Code Generation & Format Preservation
When replacing or inserting keybindings:
- **Lua Formats**: Preserves `mainMod` expression style (e.g. `mainMod .. " + Return"` vs literal `"SUPER + Return"`), column spacing between arguments, indentation of neighbouring binds, and comments.
- **Hyprlang Formats**: Emits canonical `bind = MODS, KEY, dispatcher, args`, preserving `$mainMod` where used.
- **Anchor Insertion Policy**: When adding keybindings to a top-level file, HKS places new binds below a dedicated anchor comment (`-- HKS: custom binds` in Lua, `# HKS: custom binds` in Hyprlang), preserving top-level indentation and grouping.

### C. Persistent Sidecar Storage & Migration
Sidecar metadata (`descriptions.json`) stores user-defined human descriptions and semantic categories:
- **Matching Criteria**: Overrides match on `(modifiers, key, submap)` with an optional `dispatcher` filter to disambiguate stacked binds sharing the same shortcut.
- **File Locking**: All reads and mutations use `fcntl.flock(LOCK_EX)` with an atomic temporary file write and `os.replace` to eliminate race conditions.
- **Automatic Migration**: When a user replaces shortcut $A$ with shortcut $B$, HKS automatically migrates the existing sidecar override from $A$ to $B$.
- **Collision Handling**: If destination $B$ already possesses an override, migration halts to prevent overwriting user data, and HKS emits a structured `sidecar_warning` with `code: "collision"`, preserving the original description on shortcut $A$ (which becomes an orphan in Settings).

### D. Comprehensive Undo Integration
Every mutation in HKS is transactional and reversible:
- **Config Edits (`edit replace`, `edit add`)**: `create_backup` snapshots the target configuration file AND captures a companion snapshot of `descriptions.json`. Restoring reverts both files simultaneously. If an add operation created `descriptions.json` from scratch, restore unlinks the file cleanly.
- **Sidecar-Only Edits (`sidecar set`, `sidecar clear`)**: A pre-mutation snapshot is recorded in `backups.json`. The user toast displays an instant "Undo" button, and `restore --latest` reverts the sidecar file to its exact pre-edit state.

---

## 3. Structured Warning Schema (`sidecar_warning`)

When sidecar operations encounter non-fatal issues during config application, HKS returns a structured object:

```json
{
  "code": "collision | write_failed",
  "message": "Human-readable sentence explaining the condition.",
  "old_match": {
    "modifiers": ["SUPER"],
    "key": "Q",
    "submap": "",
    "dispatcher": "window.close"
  },
  "new_match": {
    "modifiers": ["SUPER"],
    "key": "C",
    "submap": "",
    "dispatcher": "window.close"
  },
  "orphaned_old": true
}
```

- **Collision**: `orphaned_old = True`. The UI confirmation dialog and toast display a clean warning sentence. The config edit succeeds, and the old override is accessible on the Settings -> Orphans page.
- **Write Failure**: `orphaned_old = False`. Emits a clean diagnostic without crashing or aborting the config edit.

---

## 4. Known Limitations & Boundaries

1. **Loop-Generated Binds (Workspace 1–10)**:
   - Evaluated dynamically in Lua sandboxes (`for i = 1, 10 do hl.bind(...) end`).
   - HKS parses and derives descriptions for each generated bind (e.g. `SUPER + 1` -> `Workspace 1`).
   - Line rewriting is intentionally blocked with `NotEditableError` because replacing a single loop bind in-place would corrupt the loop structure.
   - Users **can** customize descriptions and categories for loop binds via sidecar overrides.
2. **Headless / Nested Screencopy**:
   - `grim` running inside nested Wayland sessions requires explicit output selection (`-o WAYLAND-1`) to avoid waiting on compositor frame callbacks.
3. **External Synthetic Input Tools**:
   - Automated keystroke injection from outside the compositor depends on external tools like `wtype` or `ydotool`. Where not installed, HKS relies on native QtTest headless event synthesis (`qmltestrunner`) and Hyprland dispatch IPC.
