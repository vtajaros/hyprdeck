# HyprDeck Roadmap

Next steps in priority order:

1. [x] **Cleanup (S12)**: fix remaining headless QML warnings (`InputPage.qml` ~309/520/615/752, `DisplayPage.qml` ~668: undefined-to-int, `"selected is not defined"`), plus `./scripts/hks-scene-check` guard.
2. [x] **Theme token guard & Settings keybind prep (S13)**: fix undefined `surfaceAlt` token, add `./scripts/hks-token-check`, prepare `SUPER+S` bind.
3. [x] **Sidecar test isolation (S14)**: isolate `HKS_SIDECAR` / XDG paths in backend tests so live config files never affect test runs.
4. [x] **Responsive layout system for Settings (S15)**: adaptive viewport/header/device-card/chip-flow components, `full`/`narrow`/`rail` sidebar, 10-size x 18-view headless audit (`./scripts/hks-layout-check`), and offscreen matrix capture (`scripts/ui-capture/capture_layout_matrix.py`).
5. **Responsive pass & polish for Keybind Studio (S16)**: apply responsive layout components (`PageViewport`, `PageHeader`, `ChipFlow`, adaptive rail sidebar) to `frontend/` window/popup shells and pages (`AllKeybindings`, `Conflicts`, `Disabled`, `Backups`, `Settings`), plus per-page polish for Display, Input, Bluetooth, Power.
6. **Single `Paths` singleton** for root resolution to replace the 13 duplicated `rootPath` lines (after S16).
7. **Full rename (after S16)**: `hks-*` scripts to `hyprdeck-*`, `HKS_*` env vars to `HYPRDECK_*`, with the old names kept as shims; update the Bar/Hyprland exec lines in one dedicated step.
8. **Overview/Home page** for Settings with quick status tiles, plus a cross-page settings search.
9. **Install story**: install script or PKGBUILD (AUR-style), dependency check at first run, `README` with screenshots, `LICENSE`, and a GitHub Actions workflow for backend tests.
10. **Safety/QA**: more tests for `hks-power-helper` and `pkexec` paths, config backup browser/restore UI, export/import of settings profiles.
11. **Robustness against Hyprland/Quickshell upgrades**: version detection and graceful degradation for catalog options.
