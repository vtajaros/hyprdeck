# Hyprland Keybind Studio (HKS)

**Phases 1, 2a, 2b-0 & 2b-1**: Read-only Hyprland configuration discovery engine, dual-language keybinding parser (`hyprland.lua` & `hyprland.conf`), live `hyprctl` oracle verification, human description derivation, conflict detection, and a desktop GUI built with Quickshell (QtQuick / QML).

## Requirements

- Python `3.14+` (standard library only; zero third-party packages)
- System `lua5.4` binary
- Optional: `quickshell` (for desktop GUI window & popup HUD)
- Optional: `hyprctl` (for live language cross-checking and `--oracle` verification)

## Quick Start

### Graphical Client (Quickshell)

```bash
# 1. Launch floating desktop window (sidebar, search, category chips, settings)
./scripts/hks-window

# 2. Launch instant Wayland layershell popup HUD (centered card with backdrop scrim)
./scripts/hks-popup

# Note: Running either script while the app is active will toggle it closed gracefully via IPC.

# 3. Run verification check (all backend tests + qmllint on frontend QML)
./scripts/hks-check
```

### Command Line Interface

```bash
# 1. Scan active Hyprland config and print normalized JSON to stdout
python3 -m backend.cli scan

# 2. Scan and verify parsed binds against live `hyprctl binds -j`
python3 -m backend.cli scan --oracle

# 3. Print a human-readable summary table (includes DESCRIPTION & CATEGORY columns)
python3 -m backend.cli summary

# 4. Check for conflicting, stacked, and duplicate keybindings
python3 -m backend.cli conflicts

# 5. Generate a sidecar override template (minimal example or pre-filled from active config)
python3 -m backend.cli sidecar-template
python3 -m backend.cli sidecar-template --all

# 6. Scan or summarize with an explicit sidecar file (or disable sidecar loading)
python3 -m backend.cli scan --sidecar ~/.config/hks/descriptions.json
python3 -m backend.cli summary --no-sidecar

# 7. Run the unit test suite (uses isolated fixtures only)
python3 -m unittest discover -s backend/tests -v
```

## Documentation

- [docs/PHASE1.md](docs/PHASE1.md): Phase 1 architecture, JSON schema field reference, sandbox threat model, known limitations, and real-config acceptance checklist.
- [docs/PHASE2A.md](docs/PHASE2A.md): Phase 2a human description derivation table, category precedence order, sidecar override format, and CLI usage.
- [docs/PHASE2B0.md](docs/PHASE2B0.md): Phase 2b-0 conflict detection algorithm, stacked binds rationale, and CLI conflicts usage.
- [docs/PHASE2B1.md](docs/PHASE2B1.md): Phase 2b-1 Quickshell desktop UI architecture, window/popup modes, theme integration, keyboard navigation, and IPC.
- [docs/MILESTONES.md](docs/MILESTONES.md): Deliverables checklist across all project phases.
- [shared/schemas/bindings.schema.json](shared/schemas/bindings.schema.json): JSON Schema 2020-12 specification.
