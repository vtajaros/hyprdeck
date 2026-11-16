# HyprDeck (formerly Hyprland Keybind Studio / HKS) — Engineering Handoff

**Project Root**: `/home/delata/Shared/Projects/hyprdeck`  
**Current Date**: November 8, 2026  
**Status**: Phases 1, 2a, 2b-0, 2b-1, 2b-2a, 3a, 4a, and 3b are **100% Complete & Verified**.  
**Test Suite**: 148/148 backend unit tests passing in ~4.8s (`python3 -m unittest discover -s backend/tests -v`).  
**QML Unit Tests**: 19/19 tests passing in offscreen runner (`qmltestrunner`).  
**QML Lint**: `qmllint` passing with 0 errors / 0 warnings across all 34 QML files.  
**Live Verification**: Tested on real user Hyprland config (123 active binds, 3 disabled binds, exact oracle match against `hyprctl binds -j`).

---

## 1. Executive Summary & Mission

**HyprDeck** (formerly Hyprland Keybind Studio / HKS) is a standalone, lightweight, native desktop application and CLI tool suite built for the Hyprland Wayland compositor on Arch Linux. Its purpose is to discover, parse, categorize, detect conflicts in, and safely edit user keybindings, alongside a unified System Settings center.

### Key Architectural Invariants
1. **Zero External Python Dependencies**: Built entirely on the Python 3.14 standard library (`subprocess`, `dataclasses`, `json`, `difflib`, `resource`, `argparse`, `unittest`, `fcntl`, `hashlib`). Zero pip packages required.
2. **Dual-Language Configuration Support**:
   - Modern Lua configs: `~/.config/hypr/hyprland.lua` (executed in an isolated Lua 5.4 sandbox with `setrlimit` resource quotas and memory limits).
   - Classic Hyprlang configs: `~/.config/hypr/hyprland.conf` (parsed via recursive line-state machine handling `source = ...` directives, variables, and submaps).
3. **Safe Editing Engine (Preview-First, Atomic Writes & Rollback)**:
   - Modifications (`disable`, `enable`, `delete`, `replace`, `add`, `restore`) operate via line-oriented edit plans.
   - 3-Layer Verification before disk writes: syntax validation -> sandbox recorder check -> bind set diff.
   - Pre-edit atomic backups saved to `~/.local/share/hks/backups/`.
   - If `hyprctl reload` fails after an edit, HKS automatically rolls back to the immediate backup.
4. **Native Desktop UI (Quickshell / QML)**:
   - Built on **Quickshell 0.3.2** (QtQuick / QML) using Qt Quick Controls Basic style.
   - Dual runtime shells: Full desktop application (`WindowShell.qml`) and instant layershell HUD overlay (`PopupShell.qml`).
   - Dynamic theming tracking Matugen / live wallpaper palette (`~/.config/quickshell/theme/colors.json`).
5. **Persistent Sidecar Storage**:
   - Custom descriptions and categories are persisted in `descriptions.json` under atomic file locks.
   - Automatic migration of descriptions when keybindings are replaced.
   - Transactional undo restores both configuration files and sidecar metadata together.

---

## 2. Directory Structure & Codebase Map

```
hyprdeck/
├── README.md
├── HANDOFF.md                          # Main engineering handoff document
├── docs/
│   ├── HANDOFF.md                      # Mirror of main handoff document
│   ├── MILESTONES.md                   # Completed deliverables matrix
│   ├── PHASE1.md                       # Discovery, dual-parser, sandbox & oracle docs
│   ├── PHASE2A.md                      # Human descriptions, categories & sidecar format
│   ├── PHASE2B0.md                     # Conflict & duplicate detection algorithm
│   ├── PHASE2B1.md                     # Quickshell UI architecture & IPC
│   ├── PHASE2B2A.md                    # Conflicts page design
│   ├── PHASE3A.md                      # Editing UI, EditService & confirmation modal
│   ├── PHASE3B.md                      # Keybind modification, addition & persistence
│   ├── PHASE4A.md                      # Safe edit engine backend, backups & rollback
│   └── RUNBOOK.md                      # Manual test checklist & verification procedures
├── shared/
│   └── schemas/
│       └── bindings.schema.json        # JSON Schema 2020-12 specification
├── backend/
│   ├── __init__.py
│   ├── cli.py                          # Unified CLI entry point & subcommands
│   ├── conflicts/
│   │   ├── __init__.py
│   │   └── detect.py                   # Conflict & duplicate detection engine
│   ├── describe/
│   │   ├── __init__.py
│   │   ├── derive.py                   # Description & category derivation
│   │   ├── sidecar.py                  # Sidecar override matcher & template generator
│   │   └── sidecar_store.py            # Persistent sidecar storage, locking & migration
│   ├── discovery/
│   │   ├── __init__.py
│   │   └── config_discovery.py         # Entrypoint & language discovery
│   ├── editor/
│   │   ├── __init__.py
│   │   ├── apply.py                    # Atomic writer & safe apply pipeline
│   │   ├── backups.py                  # Hash-tagged backup store & restore logic
│   │   ├── codegen.py                  # Dual-language line generator & formatter
│   │   ├── disabled.py                 # Disabled bind scanner & extractor
│   │   ├── dispatchers.py              # Data-driven dispatcher catalog & schemas
│   │   ├── edit_plan.py                # Line-oriented comment/delete plan
│   │   ├── insert_policy.py            # Anchor placement & new bind insertion policy
│   │   ├── recorder_submap.py          # Dynamic submap recorder coordinator
│   │   └── validator.py                # 3-layer verification & bind diff validator
│   ├── models/
│   │   ├── __init__.py
│   │   └── types.py                    # Dataclasses & type definitions
│   ├── parser/
│   │   ├── __init__.py
│   │   ├── hyprlang_parser.py          # Classic .conf recursive parser
│   │   ├── lua_normalizer.py           # AST / table normalizer
│   │   ├── lua_runner.py               # Subprocess runner with setrlimit
│   │   ├── modifiers.py                # Modmask resolver & token mapping
│   │   └── lua/
│   │       └── recorder.lua            # Sandboxed Lua 5.4 bind recorder
│   ├── serializer/
│   │   ├── __init__.py
│   │   └── json_serializer.py          # JSON serializer & table formatters
│   ├── validation/
│   │   ├── __init__.py
│   │   ├── oracle.py                   # Live hyprctl oracle comparator
│   │   └── schema_validator.py         # JSON Schema validator
│   └── tests/
│       ├── __init__.py
│       ├── test_conflicts.py           # Conflict detection unit tests
│       ├── test_describe.py            # Description derivation & sidecar tests
│       ├── test_discovery.py           # Configuration discovery tests
│       ├── test_editor.py              # Edit plan, validator & backup tests
│       ├── test_hardening.py           # Hardening pass safety & undo tests
│       ├── test_hyprlang.py            # Hyprlang parser tests
│       ├── test_oracle.py              # Oracle comparison tests
│       ├── test_phase3b0.py            # Codegen & replace/insert backend tests
│       ├── test_phase3b2.py            # Dispatcher catalog tests
│       ├── test_phase3b3.py            # Addition string escaping & flag tests
│       ├── test_phase3b4.py            # Sidecar persistence & locking tests
│       ├── test_sandbox.py             # Lua sandbox isolation tests
│       ├── test_serializer.py          # JSON serialization tests
│       └── test_skeleton.py            # Baseline skeleton tests
├── frontend/
│   ├── shell.qml                       # Mode router & IPC receiver
│   ├── WindowShell.qml                 # Desktop window application
│   ├── PopupShell.qml                  # Layershell HUD overlay
│   ├── theme/
│   │   ├── HKS.qml                     # Theme singleton & color tokens
│   │   └── qmldir
│   ├── components/
│   │   ├── ActionButton.qml            # Styled push button
│   │   ├── CategoryChips.qml           # Category filter pills
│   │   ├── EditConfirmDialog.qml       # Diff review modal & warning banners
│   │   ├── EmptyState.qml              # Empty placeholder view
│   │   ├── KeybindEditDialog.qml       # Edit & Add keybinding modal dialog
│   │   ├── KeybindRecorder.qml         # Interactive keyboard shortcut recorder
│   │   ├── KeybindRow.qml              # Keybinding row delegate
│   │   ├── keymap.js                   # Keycode / keysym translation table
│   │   ├── Keycap.qml                  # Styled keyboard badge
│   │   ├── SearchField.qml             # Search input field
│   │   ├── SidebarItem.qml             # Sidebar navigation tab
│   │   └── qmldir
│   ├── services/
│   │   ├── ConflictCheckService.qml    # Reactive conflict evaluator
│   │   ├── DispatcherCatalog.qml       # Dispatcher metadata & argument schema
│   │   ├── EditService.qml             # Async CLI process runner & undo coordinator
│   │   ├── KeybindData.qml             # Primary scan data provider
│   │   ├── RecorderService.qml         # Submap recording lifecycle manager
│   │   ├── SidecarService.qml          # Sidecar override & orphan manager
│   │   └── qmldir
│   ├── pages/
│   │   ├── AllKeybindings.qml          # Primary keybinding list
│   │   ├── Backups.qml                 # Backup history & restore page
│   │   ├── Conflicts.qml               # Conflict & duplicate browser
│   │   ├── Disabled.qml                # HKS-disabled keybindings browser
│   │   ├── Settings.qml                # Sidecar storage & orphan override manager
│   │   └── qmldir
│   ├── dev/
│   │   └── RecorderHarness.qml         # Standalone recorder test harness
│   └── tests/
│       ├── mocks/                      # Headless mocks isolated from production
│       │   └── Quickshell/
│       │       └── Quickshell.qml
│       ├── tst_components.qml          # QtTest headless component verification
│       └── tst_keymap.qml              # QtTest keymap translation test
└── scripts/
    ├── hks-check                       # Verification runner (tests + qmllint)
    ├── hks-popup                       # Layershell popup toggle launcher
    ├── hks-recorder-test               # Standalone recorder harness launcher
    └── hks-window                      # Desktop window toggle launcher
```

---

## 3. Verified System State & Baseline Health

- **Unit Tests**: 148 backend tests passing (`Ran 148 tests in 4.840s`, OK).
- **QML Component Tests**: 19 tests passing in `qmltestrunner` (11 keymap tests + 8 headless UI component tests).
- **QML Lint**: 0 errors, 0 warnings across all 34 files.
- **Oracle Agreement**: Exactly 123 active binds in running Hyprland match parsed output. 3 binds are disabled via HKS comments (`-- HKS-DISABLED:`), reconciling $126 - 3 = 123$.
- **Git State**: Clean branch `main`, zero uncommitted tags or release commits.

---

## 4. Key Workflows & Pipelines

### A. Discovery & Scan Pipeline
```
[config_discovery.py] --> Detect hyprland.lua or hyprland.conf
        |
        v
[Parser Engine]       --> Lua Sandbox (setrlimit) or Hyprlang Parser
        |
        v
[BindRecord list]     --> Discovered active & disabled keybindings
        |
        v
[derive.py]           --> Semantic categorization & human descriptions
        |
        v
[sidecar_store.py]    --> Load custom overrides from descriptions.json
        |
        v
[detect.py]           --> Classify duplicate & stacked shortcut conflicts
        |
        v
[json_serializer.py]  --> Output normalized JSON Schema document
        |
        v
[KeybindData.qml]     --> Frontend reactive state singleton
```

### B. Safe Edit, Verify & Rollback Pipeline
```
[User Action]         --> Modify / Add in KeybindEditDialog.qml
        |
        v
[EditService.qml]     --> Invoke `python3 -m backend.cli edit ... --dry-run`
        |
        v
[codegen / policy]    --> Plan line changes & anchor placement
        |
        v
[validator.py]        --> 3-Layer Check: verify-config -> recorder -> bind diff
        |
        v
[EditConfirmDialog]   --> User reviews unified diff & sidecar warning banners
        |
        v
[Apply Execution]     --> Invoke `backend.cli edit ... --apply --reload`
        |
        v
[backups.py]          --> Pre-write atomic backup of config & descriptions.json
        |
        v
[Atomic Write]        --> Temp file fsync + os.replace
        |
        v
[hyprctl reload]      --> Reload compositor configuration
        |
   +----+----+
   |         |
(Success) (Failure)
   |         |
   v         v
[Toast]   [Rollback]  --> Auto-restore previous backup, emit error
```

---

## 5. Completed Phase 3b Deliverables

1. **Interactive Keybind Recorder**:
   - Dynamic `hks_record` submap entry and verified restore to default submap.
   - Qt modifier and keysym normalizer (`keymap.js`) translating hardware events to canonical Hyprland tokens.
2. **Keybind Edit Dialog**:
   - Full dispatcher catalog integration with typed schemas.
   - Live conflict check banner evaluating candidates before submission.
   - Duplicate match indicator displaying `"shared with N other bind(s)"`.
3. **Keybind Add Flow**:
   - Flag options (`locked`, `repeating`).
   - Anchor placement (`-- HKS: custom binds`) preserving file structure.
   - String escaping safety for Lua and Hyprlang argument payloads.
4. **Persistent Sidecar Storage**:
   - Atomic file locking (`fcntl`).
   - Automatic migration on shortcut replace.
   - Structured collision handling (`sidecar_warning`).
   - Unified multi-file transactional undo.

---

## 6. Rename Compatibility

- **Repository / directory fallback**: QML services check `HYPRDECK_ROOT` first, then `HKS_ROOT`, and finally `$HOME/Shared/Projects/hyprdeck` (keep a symlink from the old path if migrating an existing checkout).
- **Retained compatibility shims**: `scripts/hks-*` launcher scripts, `HKS_*` environment variables, `frontend/theme/HKS.qml`, and `hks-overrides.lua` / `-- Managed by Hyprland Keybind Studio.` markers remain unchanged until a dedicated rename milestone (S12).
