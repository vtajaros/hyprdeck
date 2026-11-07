# Phase 2b-1: Quickshell UI Foundation (Read-Only Desktop Client)

Phase 2b-1 introduces a read-only desktop graphical interface for Hyprland Keybind Studio (HKS) built with **Quickshell 0.3.2** (QtQuick / QML) and Qt Quick Controls Basic style.

It provides both a dedicated workspace floating window and an instant Wayland layershell popup HUD for searching, exploring, and inspecting all Hyprland keybindings.

---

## 1. Architecture & Design Principles

```
┌──────────────────────────────────────────────────────────┐
│                      scripts/hks-window                  │
│                      scripts/hks-popup                   │
│               (toggle & graceful IPC launcher)          │
└────────────────────────────┬─────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│                    frontend/shell.qml                    │
│             Mode router: HKS_MODE=window|popup          │
│          IPC target "hks": close() & reload()            │
└──────────────┬────────────────────────────┬──────────────┘
               ▼                            ▼
┌───────────────────────────┐  ┌───────────────────────────┐
│ frontend/WindowShell.qml  │  │  frontend/PopupShell.qml  │
│ FloatingWindow (1000x700) │  │  Overlay Scrim + Popup   │
│ Sidebar + Status Bar      │  │  Card (760x560, Exclusive)│
└──────────────┬────────────┘  └────────────┬──────────────┘
               └──────────────┬─────────────┘
                              ▼
┌──────────────────────────────────────────────────────────┐
│             frontend/pages/AllKeybindings.qml            │
│       SearchField + CategoryChips + KeybindRow List     │
└─────────────────────────────┬────────────────────────────┘
                              ▼
┌──────────────────────────────────────────────────────────┐
│            frontend/services/KeybindData.qml             │
│        Process runner: python3 -m backend.cli scan       │
│           Filtering, formatting, and cache               │
└──────────────────────────────────────────────────────────┘
```

### Hard Rules & Invariants
- **Read-Only**: Never modifies, renames, or touches `~/.config/hypr` or `~/.config/quickshell`.
- **Backend Schema Unchanged**: Uses the existing Phase 2b-0 JSON contract from `python3 -m backend.cli scan --compact`.
- **System Theme Integration & Palette Switching**:
  - `HKS` theme singleton supports two modes:
    - `"Follow system (Matugen)"`: reads `~/.config/quickshell/theme/colors.json` via `FileView` with fallback defaults.
    - `"Fixed graphite"`: built-in neutral dark graphite palette (`#141414` bg, `#1c1c1e` surface, `#7fae8b` sage green accent).
  - Configurable on the fly from the Settings page. Note: the theme selection is currently maintained in-memory for the running process and not persisted to disk.
- **Qt Quick Controls Basic Style**: Avoids heavy styles like Material or Fusion; styled with custom QML primitives.

---

## 2. Modes & Launchers

HKS provides two entry modes toggled via dedicated scripts:

### Window Mode (`scripts/hks-window`)
- Launches a native desktop `FloatingWindow` (1000x700) titled `Hyprland Keybind Studio`.
- **Sidebar (210px)**:
  - App brand header.
  - Navigation: **All Keybindings**, **Conflicts** (flagged with `"soon"` badge for Phase 2b-2), and **Settings & Information**.
- **Settings View**:
  - Displays runtime environment details (repository root, entrypoint file, config language, Hyprland version).
  - Shows active theme swatches (`bg`, `surface`, `elevated`, `accent`, `fg`, `muted`, `warning`, `critical`).
- **Footer Status Bar**:
  - Displays config language, entrypoint file basename, Hyprland version, total keybindings count, scan execution time (ms), and shortcut hints.

### Popup Mode (`scripts/hks-popup`)
- Implements a fast Wayland Layershell HUD:
  - **Backdrop Scrim Window**: `WlrLayershell.namespace: "hks-backdrop"`, fullscreen `#b8090b0e` dimmed overlay, clicking dismisses.
  - **Centered Card Window**: `WlrLayershell.namespace: "hks-popup"`, 760x560 centered card with 10px rounded corners, subtle accent border, and `WlrKeyboardFocus.Exclusive`.
  - Pressing `Esc`, clicking outside, or clicking the `` button dismisses the popup.

### Toggle & IPC Control
Both launcher scripts implement toggle behavior:
1. Checks for an active instance via `pgrep -f '[q]uickshell.*frontend'`.
2. If already running, sends `quickshell ipc -p frontend call hks close`.
3. Waits up to ~300ms for graceful exit; falls back to `pkill -f` if required.
4. If not running, launches `quickshell -p frontend`.

Available IPC calls on target `"hks"`:
- `quickshell ipc -p frontend call hks close`: closes the active instance.
- `quickshell ipc -p frontend call hks reload`: re-scans the Hyprland configuration in the background without restarting the GUI.

---

## 3. UI Components & Interactivity

| Component | File | Description |
| :--- | :--- | :--- |
| `HKS` | `frontend/theme/HKS.qml` | `pragma Singleton` theme definitions, typography (`JetBrainsMono Nerd Font`), metrics, and alpha utility |
| `KeybindData` | `frontend/services/KeybindData.qml` | Headless CLI scan executor, data model cache, filtering, and key formatting |
| `Keycap` | `frontend/components/Keycap.qml` | Individual rounded keycap pill (e.g. `SUPER`, `SHIFT`, `Return`) |
| `SearchField` | `frontend/components/SearchField.qml` | Search input with icon, accent focus outline, and instant clear button |
| `CategoryChips` | `frontend/components/CategoryChips.qml` | Horizontal scrollable category filters with keybind count badges |
| `KeybindRow` | `frontend/components/KeybindRow.qml` | Virtualized row displaying keycaps, derived description, monospace action summary, category pill, conflict/loop badges, and click-to-expand details |
| `EmptyState` | `frontend/components/EmptyState.qml` | Empty state placeholder with clear filters button |
| `SidebarItem` | `frontend/components/SidebarItem.qml` | Sidebar menu item with icon, label, hover effect, and disabled badge |
| `AllKeybindings` | `frontend/pages/AllKeybindings.qml` | Primary page coordinating search, filtering, submaps, count header, and keyboard navigation |

### Keyboard Navigation
- **Typing**: Any alphanumeric key immediately routes focus to the search field.
- **Up / Down Arrows**: Navigate across keybinding rows in the list.
- **Enter / Space**: Expands or collapses the selected row to reveal the exact source file path, line number, and original configuration line.
- **Esc**:
  - If search text is present: clears the search input.
  - If search text is empty: dismisses the popup or requests window closure.
- **Ctrl+R**: Triggers a background scan reload.

---

## 4. Verification & Testing

Static analysis and test suite runner:
```bash
# Run backend unit tests and qmllint on all frontend files
./scripts/hks-check
```

Outputs:
- 56 passing unit tests across backend discovery, parser, sandbox, serializer, oracle, descriptions, and conflicts.
- 0 warnings and 0 errors from `qmllint` across all 12 QML files.
