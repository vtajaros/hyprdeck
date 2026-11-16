# HyprDeck Roadmap

Next steps in priority order:

1. **Cleanup**: fix remaining headless QML warnings (`InputPage.qml` ~309/520/615/752, `DisplayPage.qml` ~668: undefined-to-int, `"selected is not defined"`).
2. **S12 full rename**: `hks-*` scripts to `hyprdeck-*`, `HKS_*` env vars to `HYPRDECK_*`, with the old names kept as shims; update the Bar/Hyprland exec lines in one dedicated step.
3. **Single `Paths` singleton** for root resolution to replace the 13 duplicated `rootPath` lines.
4. **Declutter pass** for the pages not yet done: Display, Input, Bluetooth, Power, using `SectionCard` and `Details` toggles for consistency.
5. **Overview/Home page** for Settings with quick status tiles, plus a cross-page settings search.
6. **Install story**: install script or PKGBUILD (AUR-style), dependency check at first run, `README` with screenshots, `LICENSE`, and a GitHub Actions workflow for backend tests.
7. **Safety/QA**: more tests for `hks-power-helper` and `pkexec` paths, config backup browser/restore UI, export/import of settings profiles.
8. **Robustness against Hyprland/Quickshell upgrades**: version detection and graceful degradation for catalog options.
