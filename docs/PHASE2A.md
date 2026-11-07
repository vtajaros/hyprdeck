# Hyprland Keybind Studio (HKS) — Phase 2a: Human Descriptions, Categories & Sidecar Overrides

## 1. Overview

Phase 2a enriches every parsed Hyprland keybinding (`hyprland.lua` and `hyprland.conf`) with:
- A deterministic, human-readable **effective description** (`description_effective`).
- A semantic **category** (`category` and `category_source`).
- Optional, strictly read-only **sidecar overrides** (`~/.config/hks/descriptions.json`) so users can customize descriptions and categories without modifying their Hyprland configuration files.

All Phase 2a changes are **additive** to `schema_version = 1`. Existing Phase 1 fields (`description` stays `string | null` from the config file) remain unchanged.

---

## 2. Additive Schema Fields

### `binds.items`

| Field | Type | Description |
| :--- | :--- | :--- |
| `description_effective` | `object` | `{ "text": string, "source": "config" \| "sidecar" \| "derived", "generic": boolean }` |
| `category` | `string` | One of: `"Apps"`, `"Windows"`, `"Workspaces"`, `"Media & Hardware"`, `"Screenshots"`, `"Notifications"`, `"System"`, `"Mouse"`, `"Other"` |
| `category_source` | `string` | `"sidecar" \| "derived"` |

### `stats.sidecar`

```json
{
  "path": "/home/user/.config/hks/descriptions.json",
  "loaded": true,
  "overrides": 10,
  "matched": 9,
  "unmatched": 1
}
```

---

## 3. Description Derivation Table (`backend/describe/derive.py`)

Both Lua (`hl.dsp.*`) and Hyprlang (`.conf`) dispatchers produce identical derived descriptions and `generic` flags:

| Lua Dispatcher | Hyprlang Dispatcher | Args / Condition | Derived `text` | `generic` |
| :--- | :--- | :--- | :--- | :--- |
| `window.drag` / `drag` | `movewindow` (mouse) | `mouse = true` or `bindm` | `"Drag window with mouse"` | `false` |
| `window.resize` / `resize` | `resizewindow` (mouse) | `mouse = true` or `bindm` | `"Resize window with mouse"` | `false` |
| `window.close` / `close` | `killactive` / `closewindow` | — | `"Close window"` | `false` |
| `window.fullscreen` | `fullscreen` | `{mode="maximized"}` or `"1"` | `"Maximize window"` | `false` |
| `window.fullscreen` | `fullscreen` | no args, `"0"`, or other | `"Toggle fullscreen"` | `false` |
| `window.float` / `float` | `togglefloating` | — | `"Toggle floating"` | `false` |
| `window.pseudo` / `pseudo` | `pseudo` | — | `"Toggle pseudo-tiling"` | `false` |
| `layout` | `togglesplit` / `layoutmsg` | `"togglesplit"` | `"Toggle split direction"` | `false` |
| `layout` | `layoutmsg` | `<other>` | `"Layout: <other>"` | `false` |
| `window.move` / `move` | `movewindow` | direction `l`/`r`/`u`/`d` or `left`/`right`/`up`/`down` | `"Move window <left\|right\|up\|down>"` | `false` |
| `window.move` / `move` | `movetoworkspace(silent)` | workspace `N` (integer or numeric string) | `"Move window to workspace N"` | `false` |
| `window.move` / `move` | `movetoworkspace(silent)` | `"special:<name>"` | `"Move window to special workspace <name>"` | `false` |
| `window.move` / `move` | `movetoworkspace(silent)` | `"e+1"` / `"+1"` or `"e-1"` / `"-1"` | `"Move window to next/previous workspace"` | `false` |
| `window.focus` / `focus` | `movefocus` | direction `l`/`r`/`u`/`d` or `left`/`right`/`up`/`down` | `"Focus window <left\|right\|up\|down>"` | `false` |
| `workspace.focus` / `focus` | `workspace` | workspace `N` | `"Switch to workspace N"` | `false` |
| `workspace.focus` / `focus` | `workspace` | `"e+1"` / `"+1"` or `"e-1"` / `"-1"` | `"Switch to next/previous workspace"` | `false` |
| `window.cycle_next` | `cyclenext` | `{prev=true}` or `"prev"` | `"Cycle to previous window"` | `false` |
| `window.cycle_next` | `cyclenext` | no args / `{prev=false}` | `"Cycle to next window"` | `false` |
| `window.bring_to_top` | `bringactivetotop` | — | `"Bring window to top"` | `false` |
| `workspace.toggle_special` | `togglespecialworkspace` | `<name>` (or empty) | `"Toggle special workspace <name>"` (or `"Toggle special workspace"`) | `false` |
| `exec_cmd` | `exec` / `execr` | 1 token, no whitespace or shell metacharacters (`;\|&><$()'"` `` ` ``) | `"Launch <basename>"` | `false` |
| `exec_cmd` | `exec` / `execr` | multi-token or shell command | `"Run: <cmd>"` (truncated to 60 chars total with `...`) | `false` |
| `<any other>` | `<any other>` | `<arg_summary>` | `"<dispatcher.path>: <arg_summary>"` | `true` |

---

## 4. Category Evaluation Order (`derive_category`)

Categories are evaluated in strict precedence order (first match wins):

1. **Sidecar override** (`category_source = "sidecar"`).
2. **`Mouse`**: bind has `flags.mouse == true` (or `bindm`).
3. **`System`**: `exec` / `exec_cmd` / `execr` matching `(^|[\s/])(hyprlock|swaylock|wlogout|loginctl|systemctl\s+(suspend|poweroff|reboot|hibernate))\b` or `hyprctl\s+dispatch\s+exit`.
4. **`Media & Hardware`**: `key` starts with `"XF86"`.
5. **`Workspaces`**: workspace-related dispatcher (`workspace.*`, `workspace`, `movetoworkspace`, `movetoworkspacesilent`, `togglespecialworkspace`, `focusworkspaceoncurrentmonitor`, `swapactiveworkspaces`, or `focus`/`window.move` with a workspace target), **except** moving a window to `special:<name>`, which falls through to `Windows`.
6. **`Windows`**: window-related dispatcher (`window.*`, `killactive`, `closewindow`, `fullscreen`, `togglefloating`, `pseudo`, `togglesplit`, `layoutmsg`, `layout`, `movefocus`, `movewindow`, `resizewindow`, `cyclenext`, `bringactivetotop`, `pin`, `centerwindow`, `alterzorder`, `focuswindow`, `swapwindow`, or moving a window to `special:<name>`).
7. **`Apps`**: any remaining `exec` / `exec_cmd` / `execr` bind.
8. **`Other`**: fallback for any other dispatcher.

*(Note: `"Screenshots"` and `"Notifications"` are valid categories in `VALID_CATEGORIES` available for sidecar overrides and future heuristics.)*

---

## 5. Precedence & Sidecar Overrides (`backend/describe/sidecar.py`)

### Precedence
- **`description_effective`**:
  1. Sidecar override (`source = "sidecar"`, `generic = false`)
  2. Config description (`bindd` in `.conf` or `{ description = "..." }` in Lua: `source = "config"`, `generic = false`)
  3. Derived description (`source = "derived"`)
- **`category`**:
  1. Sidecar override (`category_source = "sidecar"`)
  2. Derived category (`category_source = "derived"`)

### Sidecar Path Resolution
Resolved in order (read-only; missing files are silently ignored):
1. `--sidecar PATH` CLI flag
2. `$HKS_SIDECAR` environment variable
3. `$XDG_CONFIG_HOME/hks/descriptions.json`
4. `~/.config/hks/descriptions.json`

Pass `--no-sidecar` to disable loading any sidecar file.

### Sidecar Format & Matching Rules

```json
{
  "_note": "Keys starting with '_' are ignored as comments at any object level.",
  "version": 1,
  "overrides": [
    {
      "_note": "hyprland.lua:84",
      "match": {
        "modifiers": ["SUPER", "SHIFT"],
        "key": "S",
        "submap": "",
        "dispatcher": "exec_cmd"
      },
      "description": "Region screenshot to clipboard",
      "category": "Screenshots"
    }
  ]
}
```

- **`match.modifiers`**: Order-insensitive list of modifier strings canonicalized with the parser's modifier alias map (`WIN`/`MOD4`/`SUPER` -> `SUPER`, `CONTROL`/`CTRL` -> `CTRL`, etc.). Defaults to `[]`.
- **`match.key`**: Case-insensitive key name (`"return"` matches `"Return"`). Required.
- **`match.submap`**: Exact submap string (`""` for default submap). Defaults to `""`.
- **`match.dispatcher`**: Optional filter. Matches either the full `dispatcher.path` (`"window.cycle_next"`) or its leaf segment (`"cycle_next"`).
- **Stacked binds (`ALT + Tab`)**:
  - Without `match.dispatcher`: applies to all matching binds and emits an `info` diagnostic `sidecar_ambiguous` listing the matched bind IDs.
  - With `match.dispatcher`: applies only to the matching dispatcher without emitting `sidecar_ambiguous`.
- **Diagnostics**:
  - `sidecar_unmatched` (`warning`): an override did not match any bind.
  - `sidecar_ambiguous` (`info`): an override without `dispatcher` matched multiple binds.
  - `sidecar_invalid` (`error`): malformed JSON, unsupported `version`, unknown keys, unknown modifier/category, or missing both `description` and `category`. Leaves binds untouched and `complete = true`.

---

## 6. CLI Usage

```bash
# Print summary table (includes DESCRIPTION and CATEGORY columns within 120 cols)
python3 -m backend.cli summary

# Scan with an explicit sidecar file or with sidecar disabled
python3 -m backend.cli scan --sidecar /path/to/descriptions.json
python3 -m backend.cli scan --no-sidecar

# Print a minimal example sidecar template to stdout (writes no files)
python3 -m backend.cli sidecar-template

# Generate a full sidecar template pre-filled from the active config
python3 -m backend.cli sidecar-template --all
```
