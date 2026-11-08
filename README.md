# Hyprland Keybind Studio (HKS)

**Phases 1, 2a, 2b-0, 2b-1, 2b-2a, 3a, 4a & 3b**: Hyprland configuration discovery engine, dual-language keybinding parser (`hyprland.lua` & `hyprland.conf`), live `hyprctl` oracle verification, human description derivation, conflict detection, a desktop GUI built with Quickshell (QtQuick / QML), safe editing UI with preview-first modal verification and undo toast, interactive keybind recorder, dispatcher catalog, arbitrary additions, persistent sidecar synchronization, and automatic multi-file rollback.

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

# 7. Safely modify, add, disable, delete keybindings, or restore backups
python3 -m backend.cli edit replace --id <BIND_ID> --mods SUPER --key Return --apply --reload
python3 -m backend.cli edit add --mods SUPER --key F12 --dispatcher exec_cmd --args pavucontrol --desc "Volume" --apply --reload
python3 -m backend.cli edit --comment-out <BIND_ID> --apply --reload
python3 -m backend.cli edit --uncomment <BIND_ID> --apply --reload
python3 -m backend.cli edit --delete <BIND_ID> --apply --reload
python3 -m backend.cli backups [--json]
python3 -m backend.cli restore <BACKUP_ID> --apply --reload
python3 -m backend.cli restore --latest --apply --reload

# 8. Manage persistent sidecar overrides and orphan metadata
python3 -m backend.cli sidecar get --id <BIND_ID>
python3 -m backend.cli sidecar set --id <BIND_ID> --desc "Custom Description" --cat "Apps"
python3 -m backend.cli sidecar clear --id <BIND_ID>
python3 -m backend.cli sidecar list [--orphans]

# 9. Control interactive recorder submap
python3 -m backend.cli recorder enter
python3 -m backend.cli recorder status
python3 -m backend.cli recorder leave
python3 -m backend.cli recorder heal

# 10. Run the test suite and verification check
./scripts/hks-check
```

## Documentation

- [HANDOFF.md](HANDOFF.md): Engineering handoff and comprehensive architecture guide.
- [docs/PHASE1.md](docs/PHASE1.md): Phase 1 architecture, JSON schema field reference, sandbox threat model, and acceptance checklist.
- [docs/PHASE2A.md](docs/PHASE2A.md): Phase 2a human description derivation, category precedence, and sidecar format.
- [docs/PHASE2B0.md](docs/PHASE2B0.md): Phase 2b-0 conflict detection algorithm, duplicate classification, and CLI usage.
- [docs/PHASE2B1.md](docs/PHASE2B1.md): Phase 2b-1 Quickshell desktop UI architecture, window/popup modes, theme integration, and IPC.
- [docs/PHASE2B2A.md](docs/PHASE2B2A.md): Phase 2b-2a Conflicts page, card breakdown, and cross-page navigation.
- [docs/PHASE3A.md](docs/PHASE3A.md): Phase 3a editing UI, EditService coordinator, modal confirmation, and undo toast.
- [docs/PHASE3B.md](docs/PHASE3B.md): Phase 3b modification, addition, interactive recorder, dispatcher catalog, and sidecar persistence.
- [docs/PHASE4A.md](docs/PHASE4A.md): Phase 4a safe edit engine, 3-layer verification pipeline, backups/atomic writes, and rollback.
- [docs/RUNBOOK.md](docs/RUNBOOK.md): Step-by-step manual test checklist & verification runbook.
- [docs/MILESTONES.md](docs/MILESTONES.md): Deliverables checklist across all project phases.
- [shared/schemas/bindings.schema.json](shared/schemas/bindings.schema.json): JSON Schema 2020-12 specification.
