# Intentionally Kept Legacy `HKS` Names

Some `HKS` / `hks` identifiers are intentionally retained after the S16 rebrand to **HyprDeck** so existing user configurations, external desktop shell integrations, and privileged helpers keep working without silent breakage.

| Identifier / Artifact | Category | Why Kept | Removal Condition |
| :--- | :--- | :--- | :--- |
| `hks-overrides.lua` | On-disk config format | Sourced directly by user `~/.config/hypr/hyprland.lua` include blocks. | Only after a user-driven config format v2 migration rewrites the include path. |
| `-- HKS-OVERRIDES-BEGIN` / `-- HKS-OVERRIDES-END` | On-disk config markers | Detects the installed include block in user `hyprland.lua`. | Same as above (config format v2). |
| `-- HKS-SECTION-BEGIN: <name>` / `-- HKS-SECTION-END: <name>` | On-disk config markers | Demarcates generated monitor, input, and device sections inside `hks-overrides.lua`. | Same as above (config format v2). |
| `-- HKS: custom binds` | On-disk config marker | Anchor comment where `edit add` inserts new custom keybinds. | Only if anchor format is versioned and migrated. |
| `-- HKS-disabled:` | On-disk config marker | Prefix used to recognize and re-enable disabled binds in user configs. | Only if user configs are migrated or dual-prefix parsing is dropped in v2. |
| `"Managed by Hyprland Keybind Studio"` (legacy header recognition) | On-disk config compatibility | Existing `hks-overrides.lua` files on user machines carry this header; newly created files write `"Managed by HyprDeck."`. | Once no existing files need untouched-header recognition. |
| `scripts/hks-power-helper` | Privileged helper | Executed via `pkexec`; renaming requires packaging / polkit coordination in a dedicated milestone. | Dedicated packaging/polkit milestone. |
| `scripts/hks-{window,settings,popup,check,scene-check,layout-check,token-check,recorder-test}` | Compatibility shims | User Hyprland binds and `~/.config/quickshell/` Bar/PowerMenu files may still invoke `scripts/hks-*`. Each shim silently `exec`s `scripts/hyprdeck-*`. | After live user configs are switched to `scripts/hyprdeck-*` and a deprecation cycle passes. |
| `HKS_*` environment variable fallbacks | Runtime env compatibility | `HYPRDECK_*` takes precedence; `HKS_*` falls back cleanly for external scripts and tests. | Next major version after external callers use `HYPRDECK_*`. |
| `~/.config/hks`, `~/.local/share/hks` fallback resolution | User data dirs | Existing sidecar (`descriptions.json`), backups, and revert-guard state live here until the user runs `python3 -m backend.cli migrate-data --apply`. | After `migrate-data --apply` is run and symlink compatibility is no longer needed. |
| `hks_record` submap, `"hks"` IPC target, `hks-popup` layer namespace | Runtime Hyprland/Quickshell identifiers | Used by IPC callers (`quickshell ipc ... call hks ...`, `popups toggle hks`) and recorder submap safety cleanup. | Next major IPC protocol update across Bar + Quickshell configs. |
