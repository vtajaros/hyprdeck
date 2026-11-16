# HyprDeck (formerly Hyprland Keybind Studio / HKS) — Milestones

## Phase 1 Milestones

| Deliverable | Component | Status |
| :--- | :--- | :--- |
| Project layout & data models | `backend/models/types.py`, `.gitignore` | [x] Complete |
| Read-only config & entrypoint discovery (no globbing) | `backend/discovery/config_discovery.py` | [x] Complete |
| Live `hyprctl` cross-check (`version -j`, `binds -j`) | `backend/discovery/config_discovery.py` | [x] Complete |
| Sandboxed Lua 5.4 bind recorder & deterministic JSON encoder | `backend/parser/lua/recorder.lua` | [x] Complete |
| Subprocess runner with `setrlimit` & timeout isolation | `backend/parser/lua_runner.py` | [x] Complete |
| Lua bind normalization, modifier bitmask & ID generation | `backend/parser/lua_normalizer.py`, `backend/parser/modifiers.py` | [x] Complete |
| Hyprlang (`.conf`) line state machine & recursive `source` loader | `backend/parser/hyprlang_parser.py` | [x] Complete |
| JSON Schema 2020-12 & stdlib schema validator | `shared/schemas/bindings.schema.json`, `backend/validation/schema_validator.py` | [x] Complete |
| Live `hyprctl binds -j` multiset oracle comparator | `backend/validation/oracle.py` | [x] Complete |
| CLI (`scan`, `scan --oracle`, `summary`) with clean exit codes | `backend/cli.py`, `backend/serializer/json_serializer.py` | [x] Complete |
| Unit tests (Discovery, Lua fixture, Sandbox, Hyprlang, Serializer, Oracle) | `backend/tests/` | [x] Complete |
| Phase 1 architecture & acceptance documentation | `docs/PHASE1.md`, `docs/MILESTONES.md`, `README.md` | [x] Complete |

---

## Phase 2a Milestones (Descriptions, Categories & Sidecar Overrides)

| Deliverable | Component | Status |
| :--- | :--- | :--- |
| Additive schema fields (`description_effective`, `category`, `category_source`, `stats.sidecar`) | `shared/schemas/bindings.schema.json`, `backend/models/types.py` | [x] Complete |
| Dual-language human description derivation (`derive_description`) | `backend/describe/derive.py` | [x] Complete |
| Semantic category classification (`derive_category`) | `backend/describe/derive.py` | [x] Complete |
| Read-only sidecar override loader, validator & matcher | `backend/describe/sidecar.py` | [x] Complete |
| CLI summary `DESCRIPTION` & `CATEGORY` columns (<= 120 cols) & `sidecar-template [--all]` | `backend/cli.py`, `backend/serializer/json_serializer.py` | [x] Complete |
| Phase 2a parity, derivation & sidecar unit tests | `backend/tests/test_describe.py` | [x] Complete |
| Phase 2a documentation | `docs/PHASE2A.md`, `docs/MILESTONES.md`, `README.md` | [x] Complete |

---

## Phase 2b-0 Milestones (Conflict & Duplicate Detection)

| Deliverable | Component | Status |
| :--- | :--- | :--- |
| Conflict detection algorithm & duplicate classification | `backend/conflicts/detect.py`, `backend/conflicts/__init__.py` | [x] Complete |
| Additive schema fields (`conflicts`, `binds[].conflict_ids`, `stats.conflicts`) | `shared/schemas/bindings.schema.json`, `backend/models/types.py` | [x] Complete |
| CLI `conflicts` table command & plain-text formatter | `backend/cli.py`, `backend/serializer/json_serializer.py` | [x] Complete |
| Parity & synthetic conflict detection unit tests | `backend/tests/test_conflicts.py` | [x] Complete |
| Phase 2b-0 documentation & design rationale | `docs/PHASE2B0.md`, `docs/MILESTONES.md` | [x] Complete |

---

## Phase 2b-1 Milestones (Quickshell UI Foundation)

| Deliverable | Component | Status |
| :--- | :--- | :--- |
| Theme singleton & Matugen color palette integration | `frontend/theme/HKS.qml`, `frontend/theme/qmldir` | [x] Complete |
| Headless CLI scanner data service & reactive filters | `frontend/services/KeybindData.qml`, `frontend/services/qmldir` | [x] Complete |
| Shared UI components (Keycap, KeybindRow, CategoryChips, SearchField, EmptyState, SidebarItem) | `frontend/components/` | [x] Complete |
| Primary list page with virtualization, submaps & keyboard nav | `frontend/pages/AllKeybindings.qml` | [x] Complete |
| Window shell with navigation sidebar & runtime info | `frontend/WindowShell.qml` | [x] Complete |
| Wayland Layershell HUD popup with backdrop dismissal | `frontend/PopupShell.qml` | [x] Complete |
| Unified mode router & IPC target ("hks") | `frontend/shell.qml` | [x] Complete |
| Window and popup toggle launcher scripts | `scripts/hks-window`, `scripts/hks-popup` | [x] Complete |
| Verification runner (unit tests + qmllint) | `scripts/hks-check` | [x] Complete |
| Phase 2b-1 documentation & milestones update | `docs/PHASE2B1.md`, `docs/MILESTONES.md`, `README.md` | [x] Complete |

---

## Phase 2b-2a Milestones (Conflicts Page UI)

| Deliverable | Component | Status |
| :--- | :--- | :--- |
| Sidebar Conflicts navigation enabled with count badge | `frontend/WindowShell.qml`, `frontend/components/SidebarItem.qml` | [x] Complete |
| Conflicts page with header summary, duplicate/stacked ordering & empty state | `frontend/pages/Conflicts.qml`, `frontend/pages/qmldir` | [x] Complete |
| Conflict card layout, keycaps, explanatory sentence & fixed-column bind table | `frontend/pages/Conflicts.qml` | [x] Complete |
| Safe bind ID lookup & unknown ID graceful degradation | `frontend/services/KeybindData.qml`, `frontend/pages/Conflicts.qml` | [x] Complete |
| "Show in list" cross-page search navigation | `frontend/pages/Conflicts.qml`, `frontend/pages/AllKeybindings.qml`, `frontend/WindowShell.qml` | [x] Complete |
| Phase 2b-2a documentation & acceptance tests | `docs/PHASE2B2A.md`, `docs/MILESTONES.md`, `README.md` | [x] Complete |

---

## Phase 4a Milestones (Safe Edit Engine — Backend Only)

| Deliverable | Component | Status |
| :--- | :--- | :--- |
| External backup manager & atomic file writer (`HKS_BACKUP_DIR`) | `backend/editor/backups.py` | [x] Complete |
| Line-oriented edit plan (`comment_out`, `uncomment`, loop guard, CRLF preservation) | `backend/editor/edit_plan.py` | [x] Complete |
| Staged 3-layer verification (`Hyprland --verify-config`, recorder, bind-set diff) | `backend/editor/validator.py` | [x] Complete |
| Safe apply pipeline, companion parity warning & live reload auto-rollback | `backend/editor/apply.py`, `backend/editor/__init__.py` | [x] Complete |
| CLI `edit` (dry-run default), `backups` & `restore` subcommands | `backend/cli.py` | [x] Complete |
| Isolated unit test suite for backups, edit plan, validator, apply & CLI | `backend/tests/test_editor.py` | [x] Complete |
| Phase 4a architecture & known limitations documentation | `docs/PHASE4A.md`, `docs/MILESTONES.md`, `README.md` | [x] Complete |

---

## Phase 3a Milestones (Editing UI & Services)

| Deliverable | Component | Status |
| :--- | :--- | :--- |
| Real-config round trip gate test on `SUPER+grave` | `backend/editor/`, `~/.config/hypr/hyprland.lua` | [x] Complete |
| Scan detection of disabled binds (`disabled_binds`, `stats.disabled_binds`) | `backend/editor/disabled.py`, schema, models | [x] Complete |
| CLI `--delete BIND_ID`, `--json` output across edit/backups/restore | `backend/cli.py`, `backend/tests/test_editor.py` | [x] Complete |
| Edit service singleton with async Process execution & toast coordinator | `frontend/services/EditService.qml`, `frontend/services/qmldir` | [x] Complete |
| Row-level Disable and Delete actions with loop-generated guard | `frontend/components/KeybindRow.qml` | [x] Complete |
| Modal confirmation dialog with verification badges, diff viewer & delete confirm | `frontend/components/EditConfirmDialog.qml`, `frontend/components/qmldir` | [x] Complete |
| Floating action toast with instant Undo restore trigger | `frontend/WindowShell.qml` | [x] Complete |
| Disabled keybindings page with Enable action | `frontend/pages/Disabled.qml`, `frontend/pages/qmldir` | [x] Complete |
| Configuration backups page with Restore action | `frontend/pages/Backups.qml`, `frontend/pages/qmldir` | [x] Complete |
| Companion file warning banner (`hyprland.conf is not modified by HKS`) | `frontend/pages/AllKeybindings.qml`, `frontend/services/KeybindData.qml` | [x] Complete |
| Phase 3a documentation & milestones update | `docs/PHASE3A.md`, `docs/MILESTONES.md`, `README.md` | [x] Complete |

---

## Phase 3b Milestones (Keybinding Modification, Arbitrary Addition & Sidecar Persistence)

| Deliverable | Component | Status |
| :--- | :--- | :--- |
| Dual-language line generation & mainMod preservation | `backend/editor/codegen.py` | [x] Complete |
| Top-level anchor insertion policy & indentation preservation | `backend/editor/insert_policy.py` | [x] Complete |
| Dynamic submap recording coordinator (Strategy A) | `backend/editor/recorder_submap.py` | [x] Complete |
| Qt modifier & keysym hardware normalizer | `frontend/components/keymap.js` | [x] Complete |
| Interactive keybind recorder component & test harness | `frontend/components/KeybindRecorder.qml`, `frontend/dev/RecorderHarness.qml` | [x] Complete |
| Data-driven dispatcher catalog & argument validation | `backend/editor/dispatchers.py`, `frontend/services/DispatcherCatalog.qml` | [x] Complete |
| Full keybind edit modal dialog & live conflict evaluation | `frontend/components/KeybindEditDialog.qml`, `frontend/services/ConflictCheckService.qml` | [x] Complete |
| Duplicate shortcut match badge ("shared with N other bind(s)") | `frontend/components/KeybindEditDialog.qml` | [x] Complete |
| Arbitrary addition flow (`edit add`, flags, submaps, escaping) | `backend/cli.py`, `backend/editor/apply.py`, `frontend/services/EditService.qml` | [x] Complete |
| Persistent sidecar storage, `fcntl` locking & atomic writes | `backend/describe/sidecar_store.py` | [x] Complete |
| Sidecar override migration on key replace & orphan detection | `backend/describe/sidecar_store.py`, `backend/cli.py` | [x] Complete |
| Structured collision warnings (`sidecar_warning`) | `backend/cli.py`, `frontend/components/EditConfirmDialog.qml` | [x] Complete |
| Sidecar settings & orphan management UI | `frontend/pages/Settings.qml`, `frontend/services/SidecarService.qml` | [x] Complete |
| Multi-file transactional undo (config + sidecar) | `backend/editor/backups.py`, `frontend/services/EditService.qml` | [x] Complete |
| Headless component tests & mock isolation verification | `backend/tests/test_hardening.py`, `frontend/tests/tst_components_headless.qml` | [x] Complete |
| Phase 3b documentation & runbook | `docs/PHASE3B.md`, `docs/RUNBOOK.md`, `docs/HANDOFF.md` | [x] Complete |

---

## Verified on Real Config

- **Binds**: 123 active binds (3 disabled)
- **Oracle Comparison**: MATCH (exact count and order match against live `hyprctl binds -j`)
- **Parity**: Hyprlang vs Lua parity equal
- **Test Suite**: 148 backend unit tests, 19 QML unit tests
- **QML Lint**: 0 errors / 0 warnings across 34 files
- **Performance**: Scan time about 0.1 s

---

## Milestone S11 (Rebrand to HyprDeck)

| Deliverable | Component | Status |
| :--- | :--- | :--- |
| Rebrand user-visible titles to `HyprDeck Keybind Studio` & `HyprDeck Settings` | `frontend/AppInfo.qml`, `settings/AppInfo.qml`, `scripts/hks-window`, `scripts/hks-settings`, `backend/settings/keyboard/state.py` | [x] Complete |
| Update `rootPath` resolution (`HYPRDECK_ROOT` -> `HKS_ROOT` -> `$HOME/Shared/Projects/hyprdeck`) | `settings/services/*.qml`, `frontend/services/*.qml`, `scripts/ui-capture/capture.qml` | [x] Complete |
| Set `__tool_name__ = "hyprdeck"` and `bindings.schema.json` `$id` (`hyprdeck.local`) | `backend/__init__.py`, `shared/schemas/bindings.schema.json`, `docs/PHASE1.md` | [x] Complete |
| Update docs, handoff compatibility note, and roadmap | `README.md`, `HANDOFF.md`, `docs/HANDOFF.md`, `docs/RUNBOOK.md`, `docs/MILESTONES.md`, `docs/ROADMAP.md` | [x] Complete |

---

## Milestone S12 (Scene Warnings Cleanup & Guard)

| Deliverable | Component | Status |
| :--- | :--- | :--- |
| Fix `ReferenceError: selected is not defined` on Mirror "None" chip | `settings/pages/DisplayPage.qml` | [x] Complete |
| Fix `Unable to assign [undefined] to int` (`HKS.fontSizeBody` -> `HKS.fontSize`) | `settings/pages/InputPage.qml` | [x] Complete |
| Add headless scene-warning regression guard & wire into `hks-check` | `scripts/hks-scene-check`, `scripts/hks-check`, `settings/WindowShell.qml`, `settings/shell.qml`, `docs/RUNBOOK.md` | [x] Complete |

---

## Milestone S15 (Responsive Layout System — Settings)

| Deliverable | Component | Status |
| :--- | :--- | :--- |
| Responsive layout tokens, hysteresis breakpoints (`ResponsiveLogic`), and 3 unit tests | `frontend/theme/HKS.qml`, `frontend/components/ResponsiveLogic.qml`, `settings/tests/tst_settings_controls.qml` | [x] Complete |
| Shared adaptive UI components & elision/wrap hardening | `frontend/components/{PageViewport,PageHeader,DeviceCard,ChipFlow}.qml`, `SidebarItem.qml`, `ActionButton.qml` | [x] Complete |
| Adaptive window shell (`full`/`narrow`/`rail` sidebar, overlay search, min size) & `SettingRow` stacking | `settings/WindowShell.qml`, `settings/components/SettingRow.qml` | [x] Complete |
| Retrofit all 10 Settings pages for `360px`..`3400px` widths & 2-col wide `OptionsPage` | `settings/pages/*.qml` | [x] Complete |
| Headless 10-size x 18-view layout audit (`0` violations) & offscreen PNG/contact-sheet generator | `scripts/hks-layout-check`, `scripts/ui-capture/capture_layout_matrix.py`, `scripts/hks-check` (`[6/6]`) | [x] Complete |

---

## Milestone S16 (Complete HyprDeck Rename & Compatibility Shims)

| Deliverable | Component | Status |
| :--- | :--- | :--- |
| Theme singleton rename `HKS` -> `Deck` across QML + token guard | `frontend/theme/Deck.qml`, `frontend/theme/qmldir`, `scripts/hyprdeck-token-check` | [x] Complete |
| `HYPRDECK_* > HKS_* > default` env resolution helpers & wrapper exports | `backend/core/env.py`, `scripts/lib-hyprdeck-env.sh`, `Deck.env()` | [x] Complete |
| Rename `scripts/hks-*` -> `scripts/hyprdeck-*` with silent shims + tests | `scripts/hyprdeck-*`, `scripts/hks-*`, `backend/tests/test_hyprdeck_window.py` | [x] Complete |
| Canonical `~/.config/hyprdeck` & `~/.local/share/hyprdeck` + `migrate-data` CLI | `backend/core/data_migration.py`, `backend/cli.py`, `backend/tests/test_data_migration.py` | [x] Complete |
| Legacy inventory, brand guard (`[7/7]`), and live-switch preparation | `docs/LEGACY_NAMES.md`, `scripts/hyprdeck-brand-check`, `scripts/hyprdeck-check` | [x] Complete |
