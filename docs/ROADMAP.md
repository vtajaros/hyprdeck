# HyprDeck Roadmap

Next steps in priority order:

1. [x] **Cleanup (S12)**: fix remaining headless QML warnings (`InputPage.qml`, `DisplayPage.qml`: undefined-to-int, `"selected is not defined"`), plus `./scripts/hyprdeck-scene-check` guard.
2. [x] **Theme token guard & Settings keybind prep (S13)**: fix undefined `surfaceAlt` token, add `./scripts/hyprdeck-token-check`, prepare `SUPER+S` bind.
3. [x] **Sidecar test isolation (S14)**: isolate `HYPRDECK_SIDECAR` / XDG paths in backend tests so live config files never affect test runs.
4. [x] **Responsive layout system for Settings (S15)**: adaptive viewport/header/device-card/chip-flow components, `full`/`narrow`/`rail` sidebar, 10-size x 18-view headless audit (`./scripts/hyprdeck-layout-check`), and offscreen matrix capture (`scripts/ui-capture/capture_layout_matrix.py`).
5. [x] **Complete HyprDeck rename (S16)**: `Deck` theme singleton, `HYPRDECK_*` env vars, `scripts/hyprdeck-*` with silent `hks-*` shims, `~/.config/hyprdeck` & `~/.local/share/hyprdeck` + `migrate-data` CLI, `docs/LEGACY_NAMES.md`, `./scripts/hyprdeck-brand-check`, and live-switch preparation.
6. [x] **Responsive layout system for Keybind Studio (S17)**: adaptive `WindowShell` (`full`/`narrow`/`rail` sidebar, centered ~1100px cap, horizontal safety scroll <320px), responsive `KeybindRow` (`columns`/`two-line`/`stacked` + overflow menu + wrapping `ShortcutKeys`), wrapping toolbar/`CategoryChips` (`ChipFlow`), responsive `Conflicts` & dialogs (`KeybindEditDialog`, `KeybindRecorder`, `EditConfirmDialog` clamped with internal scroll), `PopupShell` + Bar card compatibility, `--target` layout audit & screenshots, and S16 hardening.
7. **Backups page in Settings**: list, diff, and restore config backups via the existing backup engine.
8. **`hyprland.conf` companion-drift decision**: retire or add a sync option (currently 123 vs 118 binds, warned on every apply).
9. **Single `rootPath`/`Paths` helper**: replace the ~13 duplicated `rootPath` lines across QML services.
10. **Install / packaging story**: `README` with screenshots, `LICENSE`, `PKGBUILD`, and installing `hks-power-helper` to a root-owned location instead of running it from the repo under `pkexec`.
11. **Overview/Home page & robustness**: quick status tiles, cross-page settings search, and Hyprland/Quickshell version detection.
