# Hyprland Keybind Studio (HKS)

**Phase 1 & 2a**: Read-only Hyprland configuration discovery engine and dual-language keybinding parser (`hyprland.lua` & `hyprland.conf`) with normalized JSON output, live `hyprctl` oracle verification, derived human descriptions, semantic categories, and read-only sidecar overrides.

## Requirements

- Python `3.14+` (standard library only; zero third-party packages)
- System `lua5.4` binary
- Optional: `hyprctl` (for live language cross-checking and `--oracle` verification)

## Quick Start

```bash
# 1. Scan active Hyprland config and print normalized JSON to stdout
python3 -m backend.cli scan

# 2. Scan and verify parsed binds against live `hyprctl binds -j`
python3 -m backend.cli scan --oracle

# 3. Print a human-readable summary table (includes DESCRIPTION & CATEGORY columns)
python3 -m backend.cli summary

# 4. Generate a sidecar override template (minimal example or pre-filled from active config)
python3 -m backend.cli sidecar-template
python3 -m backend.cli sidecar-template --all

# 5. Scan or summarize with an explicit sidecar file (or disable sidecar loading)
python3 -m backend.cli scan --sidecar ~/.config/hks/descriptions.json
python3 -m backend.cli summary --no-sidecar

# 6. Run the unit test suite (uses isolated fixtures only)
python3 -m unittest discover -s backend/tests -v
```

## Documentation

- [docs/PHASE1.md](docs/PHASE1.md): Phase 1 architecture, JSON schema field reference, sandbox threat model, known limitations, and real-config acceptance checklist.
- [docs/PHASE2A.md](docs/PHASE2A.md): Phase 2a human description derivation table, category precedence order, sidecar override format, and CLI usage.
- [docs/MILESTONES.md](docs/MILESTONES.md): Phase 1 & Phase 2a deliverables checklist.
- [shared/schemas/bindings.schema.json](shared/schemas/bindings.schema.json): JSON Schema 2020-12 specification.
