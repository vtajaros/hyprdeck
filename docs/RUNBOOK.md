# HyprDeck — Manual Verification Runbook

This runbook provides step-by-step procedures to verify HyprDeck manually, covering automated suites, backend CLI workflows, interactive recorder submaps, and the graphical desktop interface.

---

## 1. Automated Health Check

Run the consolidated automated test runner:
```bash
./scripts/hyprdeck-check
```
**Expected Results**:
- `[1/7]` Backend unit test suite: 373+ tests pass with zero errors or failures.
- `[2/7]` Frontend & Settings QML unit tests: 38 frontend + 29 settings tests pass in offscreen `qmltestrunner`.
- `[3/7]` QML static analysis: `qmllint` passes with 0 errors and 0 warnings across all 79 QML files.
- `[4/7]` HyprDeck theme token guard (`./scripts/hyprdeck-token-check`): verifies every `Deck.<token>` used in `frontend/` and `settings/` QML is defined in `frontend/theme/Deck.qml`.
- `[5/7]` Headless scene-warning guard (`./scripts/hyprdeck-scene-check`): visits Display and all Input tabs under `HYPRDECK_SETTINGS_DEBUG=1` and asserts 0 scene warnings in `InputPage`, `DisplayPage`, or `SettingRow` (set `HYPRDECK_SKIP_SCENE=1` on headless/CI hosts without Quickshell).
- `[6/7]` Headless responsive layout guard (`./scripts/hyprdeck-layout-check --target all`): audits `settings`, `keybind-studio`, `popup`, and `card` (Bar-embedded `760x560`) across the responsive size matrix under `QT_QPA_PLATFORM=offscreen` and asserts 0 layout violations or binding loops (pass `--target settings|keybind-studio|popup|card|all`, `HYPRDECK_LAYOUT_QUICK=1` for the 5-size subset, `HYPRDECK_SKIP_LAYOUT=1` to skip in `hyprdeck-check`, or `--screenshots` to also render PNGs and ImageMagick contact sheets via `python3 scripts/ui-capture/capture_layout_matrix.py` into `build/layout-shots/`).
- `[7/7]` Brand guard (`./scripts/hyprdeck-brand-check`): ensures no un-allowlisted legacy `HKS` / `Hyprland Keybind Studio` identifiers were reintroduced.
- Exit code is `0`.

---

## 2. CLI End-to-End Workflows (Safe Temp Copy)

Run these checks in a temporary sandbox directory to verify editing, sidecar synchronization, and undo completeness without touching `~/.config/hypr/`.

```bash
# Set up sandbox
SANDBOX=$(mktemp -d /tmp/hyprdeck-sandbox-XXXXXX)
mkdir -p "$SANDBOX/config" "$SANDBOX/backups"
cat << 'EOF' > "$SANDBOX/config/hyprland.lua"
local mainMod = "SUPER"
hl.bind(mainMod .. " + Return", hl.dsp.exec_cmd("kitty"))
hl.bind(mainMod .. " + Q",      hl.dsp.window.close())
EOF

export HYPRDECK_BACKUP_DIR="$SANDBOX/backups"
export HYPRDECK_SIDECAR="$SANDBOX/config/descriptions.json"
CFG="$SANDBOX/config/hyprland.lua"
```

### Test 2.1: Add Keybinding with Description
```bash
# Add SUPER+F12 with custom description
python3 -m backend.cli edit add \
  --mods SUPER --key F12 \
  --dispatcher exec_cmd --args pavucontrol \
  --desc "Volume Control" --cat "Media & Hardware" \
  --apply --no-live --entrypoint "$CFG" --json

# Verify config has the new bind and anchor comment
grep "F12" "$CFG"
grep "HKS: custom binds" "$CFG"

# Verify sidecar file was created and contains the override
cat "$SANDBOX/config/descriptions.json"
```

### Test 2.2: Undo Addition (Restore Latest)
```bash
# Restore latest backup
python3 -m backend.cli restore --latest --apply --json

# Verify config reverted to initial 2 binds
grep -v "F12" "$CFG"

# Verify sidecar was cleaned up
[ ! -f "$SANDBOX/config/descriptions.json" ] && echo "Sidecar cleanly unlinked!"
```

### Test 2.3: Modify Keybinding with Sidecar Migration
```bash
# 1. Create sidecar override on SUPER+Q
Q_ID=$(python3 -m backend.cli scan --entrypoint "$CFG" --no-live | jq -r '.binds[] | select(.key=="Q") | .id')
python3 -m backend.cli sidecar set --id "$Q_ID" --desc "Close active window" --cat "Windows" --entrypoint "$CFG" --no-live

# 2. Replace SUPER+Q with SUPER+C
python3 -m backend.cli edit replace --id "$Q_ID" --mods SUPER --key C --apply --no-live --entrypoint "$CFG" --json

# 3. Verify sidecar migrated from Q to C
cat "$SANDBOX/config/descriptions.json" | jq '.overrides[0].match.key'  # Output: "C"

# 4. Restore and verify revert
python3 -m backend.cli restore --latest --apply --json
cat "$SANDBOX/config/descriptions.json" | jq '.overrides[0].match.key'  # Output: "Q"
grep "SUPER + Q" "$CFG"
```

### Clean up sandbox:
```bash
rm -rf "$SANDBOX"
unset HYPRDECK_BACKUP_DIR HYPRDECK_SIDECAR
```

---

## 3. Live Recorder Submap Safety Probe

Verify that interactive submap recording enters and leaves cleanly on a running Hyprland compositor without stranding keys or changing bind counts.

```bash
BEFORE=$(hyprctl binds -j | jq length)
trap 'hyprctl dispatch "hl.dsp.submap(\"reset\")" 2>/dev/null || hyprctl dispatch submap reset 2>/dev/null' EXIT

# Enter recording submap
python3 -m backend.cli recorder enter
STATUS=$(python3 -m backend.cli recorder status | jq -r .submap)
echo "Current submap: $STATUS"  # Expected: "hks_record"

# Leave recording submap
python3 -m backend.cli recorder leave
AFTER=$(hyprctl binds -j | jq length)

echo "Before count: $BEFORE, After count: $AFTER"
[ "$BEFORE" -eq "$AFTER" ] && echo "Submap test PASSED: Bind counts match exactly!"
```

### Emergency Recorder Submap Recovery
If the UI or backend crashes while inside `hks_record`, the detached OS watchdog resets the submap automatically within the timeout (or immediately on parent exit). To force-reset manually from a TTY or terminal:

```bash
hyprctl dispatch 'hl.dsp.submap("reset")'
```

---

## 4. Desktop UI Interactive Verification

### Test 4.1: Launch Desktop Window
```bash
./scripts/hyprdeck-window
```
**Verify Visual Elements**:
1. Floating window opens centered with rounded corners and Matugen theme colors.
2. Sidebar displays: **All Keybindings**, **Conflicts**, **Disabled**, **Backups**, **Settings**.
3. Status bar at the bottom displays: detected language (`lua`), active entrypoint (`hyprland.lua`), and Hyprland version.
4. Pressing Escape or clicking the close button dismisses the window cleanly.

### Test 4.2: Add Keybinding Flow
1. Click **+ Add Keybinding** in the upper left.
2. Modal dialog appears with **Keyboard Shortcut**, **Action**, **Options**, and **Description & Category**.
3. Click **Record shortcut**. The button enters recording state with amber highlight.
4. Press a key combination (e.g. `SUPER` + `Alt` + `T`). The shortcut fields populate with keycaps.
5. In **Action**, select dispatcher `exec_cmd` and input arguments `alacritty`.
6. Notice live conflict evaluation banner updates in real-time.
7. Click **Review addition**. The unified diff modal opens displaying proposed changes.
8. Click **Apply changes**. The window updates, and an action toast appears with an **Undo** button.
9. Clicking **Undo** restores the previous state.

### Test 4.3: Edit Keybinding Flow
1. In the All Keybindings list, hover over a user keybinding row and click **Edit** (pencil icon).
2. The edit modal opens with pre-populated values.
3. If multiple active binds share the shortcut (e.g. stacked dispatcher binds), verify that a subtle `"shared with N other bind(s)"` badge appears in Section 4.
4. Change the description or category and click **Save** (or change shortcut and review diff).
5. Toast confirmation appears with **Undo** trigger.

### Test 4.4: Settings & Orphan Management
1. In the sidebar, navigate to **Settings**.
2. Under **Sidecar Storage**, inspect total overrides and orphaned overrides count.
3. If orphaned overrides exist, click **Delete** on an orphan card to remove it.
