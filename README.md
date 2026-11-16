# HyprDeck

**System Settings & Control Center for Hyprland** — built with Quickshell (QtQuick / QML) and a zero-dependency Python backend.

HyprDeck provides a unified **System Settings** application for configuring Hyprland, displays, input, audio, networking, Bluetooth, themes, power, and config backups, alongside **Keybind Studio** for inspecting, recording, and safely editing `hyprland.lua` / `hyprland.conf` keybindings.

---

## Features

### HyprDeck Settings (`./scripts/hyprdeck-settings`)

- **Appearance & Desktop** — Live `hyprctl eval` preview, staged writes to `hks-overrides.lua`, and per-section reset.
- **Display** — Monitor arrangement, resolution, refresh rate, scale, transform, panel/DDC brightness (5% safety floor), and a 15-second revert-guard watchdog.
- **Input** — Keyboard layouts, XKB options, mouse, touchpad, and per-device overrides.
- **Audio** — PipeWire/Pulse sinks and sources, volume/mute controls, and default device switching.
- **Bluetooth** — Adapter power, bounded scanning, pairing, trust, connect, and device removal.
- **Network** — NetworkManager status, Wi-Fi scanning/connection, and saved profiles.
- **Themes** — Wallpaper, GTK (`settings.ini`), icon/cursor themes, and Qt (`qt6ct.conf`).
- **Power** — Battery health, CPU EPP/turbo controls, `hypridle.conf` dim/lock/DPMS timeouts, and sleep info.
- **System Info** — Hardware, kernel, Hyprland, and session summary.
- **Keyboard Shortcuts** — Status overview and quick launcher into Keybind Studio.
- **Backups** — Snapshot browser grouped by file, unified diff viewer, safe restore with pre-restore snapshots, automatic rollback on reload failure, and one-click **Undo**.

### Keybind Studio & Popup (`./scripts/hyprdeck-window`, `./scripts/hyprdeck-popup`)

- Dual-language parser (`hyprland.lua` and `hyprland.conf`) with live `hyprctl binds -j` oracle verification.
- Conflict/duplicate detection, human-readable descriptions with persistent sidecar overrides (`~/.config/hyprdeck/descriptions.json`), interactive keybind recorder, and a Bar-embeddable card.

### Responsive Layout

- Adaptive sidebar (`full` / `narrow` / `rail`), wrapping controls, clamped modals, and horizontal safety scrolling across desktop, tiled, and compact window sizes.

---

## Safety Model

Every config-mutating operation in HyprDeck is designed to fail closed and recover automatically:

- **Staged validation**: Lua changes are staged in a temporary copy and validated before touching live config files.
- **Concurrency & integrity checks**: Target files and backup snapshots are verified by SHA-256 before and after writes.
- **Snapshots & rollback**: Edits and restores create snapshots in `~/.local/share/hyprdeck/backups` (`HYPRDECK_BACKUP_DIR` override supported). Failed post-write reloads roll back automatically.
- **Display revert-guard**: Display changes require explicit confirmation within 15 seconds or revert automatically.

---

## Requirements

- **Python** `3.14+` (standard library only — no third-party Python packages)
- **`lua5.4`** (for `hyprland.lua` parsing)
- **`quickshell`** (Qt 6 / QtQuick desktop UI)
- **`hyprctl`** / Hyprland (live state, `eval` preview, reload, and `--oracle` verification)
- Optional runtime tools used by individual Settings pages: `pactl` / `wpctl`, `bluetoothctl`, `nmcli`, `hypridle`, `ddcutil` / `brightnessctl`, `pkexec`

---

## Quick Start

### Launch the GUI

```bash
# HyprDeck System Settings
./scripts/hyprdeck-settings

# Keybind Studio (floating window)
./scripts/hyprdeck-window

# Keybind Popup HUD (Wayland layershell)
./scripts/hyprdeck-popup
```

Running a launcher while the window is already running toggles it cleanly via Quickshell IPC.

### Useful CLI Commands

```bash
# Inspect merged Hyprland settings state
python3 -m backend.cli settings state

# List, diff, or dry-run restore config backups
python3 -m backend.cli settings backups list --json
python3 -m backend.cli backups diff --id <BACKUP_ID> --json
python3 -m backend.cli settings backups restore --id <BACKUP_ID> --dry-run --json

# Scan keybindings and verify against live hyprctl
python3 -m backend.cli scan --oracle
python3 -m backend.cli conflicts

# Migrate legacy ~/.config/hks and ~/.local/share/hks data (dry-run by default)
python3 -m backend.cli migrate-data
```

---

## Repository Structure

```text
settings/       HyprDeck Settings QML app (pages, services, components, tests)
frontend/       Keybind Studio, Popup HUD, shared Deck theme, and responsive components
backend/        Stdlib-only Python CLI, config parsers, settings ops, backup/restore engine, tests
scripts/        Launchers (hyprdeck-settings, hyprdeck-window, hyprdeck-popup) & verification guards
shared/         JSON schemas (bindings.schema.json)
docs/           Runbook, roadmap, legacy compatibility inventory, and architecture notes
```

---

## Verification & Development

Run the full verification suite (backend tests, QML unit tests, `qmllint`, theme token check, headless scene-warning check, multi-size responsive layout audit, and brand guard):

```bash
./scripts/hyprdeck-check
```

Generate offscreen layout contact sheets in `build/layout-shots/`:

```bash
python3 scripts/ui-capture/capture_layout_matrix.py --target all
```

---

## Documentation

- [docs/RUNBOOK.md](docs/RUNBOOK.md) — Manual verification checklist and sandboxed CLI workflows
- [docs/ROADMAP.md](docs/ROADMAP.md) — Project priorities and upcoming work
- [docs/LEGACY_NAMES.md](docs/LEGACY_NAMES.md) — Legacy compatibility shims, environment variables, and migration path
- [docs/HANDOFF.md](docs/HANDOFF.md) — Architecture and engineering overview
- [docs/MILESTONES.md](docs/MILESTONES.md) — Completed milestone summary
- [shared/schemas/bindings.schema.json](shared/schemas/bindings.schema.json) — Bindings JSON Schema
