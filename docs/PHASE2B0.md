# Hyprland Keybind Studio (HKS) — Phase 2b-0: Conflict Detection

## 1. Overview

Phase 2b-0 introduces read-only conflict detection and classification across parsed Hyprland keybindings (`hyprland.lua` and `hyprland.conf`).

In Hyprland, multiple keybindings bound to the exact same key combination are evaluated and executed sequentially in declaration order. This enables deliberate and idiomatic desktop interactions—most notably "stacked binds" such as:
```lua
hl.bind("ALT + Tab", hl.dsp.window.cycle_next())
hl.bind("ALT + Tab", hl.dsp.window.bring_to_top())
```
Because stacked binds are intentional and fully supported by Hyprland, HKS classifies multi-action groups as informational (`multiple_actions`, severity `info`). True redundant bindings with identical dispatchers and arguments are classified as duplicates (`duplicate`, severity `warning`).

All Phase 2b-0 changes are **additive** to `schema_version = 1`.

---

## 2. Detection Algorithm (`backend/conflicts/detect.py`)

### Grouping Key
Bindings are partitioned into conflict groups by the 5-tuple:
```python
(submap or "", modmask, key.strip().lower(), flags.release, flags.long_press)
```

- **Submap**: Bindings in distinct submaps (e.g. `""` default vs `"resize"`) never collide.
- **Modifier Mask (`modmask`)**: Bitmask of canonical modifiers (`SUPER`, `SHIFT`, `CTRL`, `ALT`, etc.).
- **Key Name (`key.lower()`)**: Compared case-insensitively (`"Tab"` and `"tab"` group together).
- **Press vs. Release**: A key press bind (`release=false`) and a key release bind (`release=true`) on the same key trigger at different moments and are never grouped together.
- **Long-Press**: Standard press binds (`long_press=false`) and long-press binds (`long_press=true`) trigger under different timings and are never grouped together.
- **Other Flags Omitted**: Flags such as `repeating`, `locked`, `mouse`, `non_consuming`, and `transparent` do not prevent key conflicts and are excluded from the grouping key.

### Group Filtering & Ordering
- Only groups with `count >= 2` produce a `ConflictRecord`.
- Conflict objects are assigned stable IDs (`conflict-1`, `conflict-2`, ...) and ordered strictly by the first appearance of the key combination in the configuration file.

### Classification Rules
Within a conflicting group:
1. **`duplicate` (severity: `warning`)**: At least two binds in the group share identical `dispatcher.path` AND identical `dispatcher.arg_summary`.
2. **`multiple_actions` (severity: `info`)**: Every bind in the group performs a distinct action.
3. **Worst Severity Wins**: If a group contains both duplicate binds and distinct binds, the entire group is classified as `duplicate` (warning).

### In-Place Bind Association
Every `BindRecord` belonging to a conflict group has the conflict's ID appended to its `conflict_ids` list (`["conflict-1"]`).

---

## 3. Rationale: Stacked Binds as Info, Not Errors

In traditional desktop environments (such as GNOME or XFCE), assigning two actions to the same shortcut is an error that overwrites or disables the previous assignment.

In Hyprland, the compositor executes **every** matching binding in sequence. This is a deliberate design choice that allows users to chain window management actions together (e.g. cycling the window focus and immediately bringing the active window to the top on `ALT + Tab`).

Treating stacked binds as warnings or errors would produce false positives for standard user configurations. HKS therefore distinguishes:
- **`multiple_actions` (`info`)**: Stacked binds chaining different actions on one shortcut.
- **`duplicate` (`warning`)**: Accidental re-declarations that run the exact same command or dispatcher redundantly.

---

## 4. Additive JSON Output (`schema_version = 1`)

### Top-Level `conflicts` Array
```json
"conflicts": [
  {
    "bind_ids": [
      "b_4d2091c50e05",
      "b_a9b1c74e12d3"
    ],
    "id": "conflict-1",
    "key": "Tab",
    "kind": "multiple_actions",
    "modifiers": [
      "ALT"
    ],
    "severity": "info",
    "sources": [
      {
        "file": "/home/user/.config/hypr/hyprland.lua",
        "line": 94
      },
      {
        "file": "/home/user/.config/hypr/hyprland.lua",
        "line": 95
      }
    ],
    "submap": ""
  }
]
```

### Per-Bind `conflict_ids`
Each item in `binds` contains a list of associated conflict IDs (empty list if no conflict):
```json
"conflict_ids": ["conflict-1"]
```

### `stats.conflicts`
Summary metrics added to the `stats` object:
```json
"conflicts": {
  "duplicate": 0,
  "multiple_actions": 2,
  "total": 2
}
```

---

## 5. CLI Usage

The `conflicts` subcommand prints a formatted plain-text table to stdout:

```bash
# Check conflicts in active Hyprland configuration
python3 -m backend.cli conflicts

# Inspect conflicts in a specific directory or entrypoint
python3 -m backend.cli conflicts --config-dir ~/.config/hypr --no-live
```

### Example Output
```text
Conflicts: 2 total (0 duplicate, 2 multiple_actions)

ID         | SEVERITY | KIND             | SHORTCUT          | BINDS | SOURCES
-----------+----------+------------------+-------------------+-------+----------------------------------
conflict-1 | info     | multiple_actions | ALT + Tab         | 2     | hyprland.lua:94, hyprland.lua:95
conflict-2 | info     | multiple_actions | ALT + SHIFT + Tab | 2     | hyprland.lua:96, hyprland.lua:97
```

If no conflicting binds exist, the command outputs:
```text
No conflicts found.
```

### Exit Codes
- `0`: Successful execution (regardless of whether conflicts are found).
- `2`: Command-line usage error or configuration discovery error.
