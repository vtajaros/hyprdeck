# Hyprland Keybind Studio (HKS)

**Phase 1**: Read-only Hyprland configuration discovery engine and dual-language keybinding parser (`hyprland.lua` & `hyprland.conf`) with normalized JSON output and live `hyprctl` oracle verification.

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

# 3. Print a human-readable summary table of all shortcuts
python3 -m backend.cli summary

# 4. Run the unit test suite (uses isolated fixtures only)
python3 -m unittest discover -s backend/tests -v
```

## Documentation

- [docs/PHASE1.md](docs/PHASE1.md): Full architecture, JSON schema field reference, sandbox threat model, known limitations, and real-config acceptance checklist.
- [docs/MILESTONES.md](docs/MILESTONES.md): Phase 1 deliverables checklist.
- [shared/schemas/bindings.schema.json](shared/schemas/bindings.schema.json): JSON Schema 2020-12 specification.
