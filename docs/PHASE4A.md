> Historical document written under the name HKS.

# Hyprland Keybind Studio (HKS) — Phase 4a: Safe Edit Engine

## 1. Overview

Phase 4a introduces a backend-only **Safe Edit Engine** (`backend/editor/`) and CLI subcommands (`edit`, `backups`, `restore`) for safely commenting out (`-- HKS-disabled: ` / `# HKS-disabled: `) and uncommenting individual keybindings in `hyprland.lua` and `hyprland.conf`.

Every edit operation is **dry-run by default** and must pass a three-layer staged verification pipeline before any bytes are written to disk.

---

## 2. Architecture (`backend/editor/`)

### 2.1 `backups.py` — External Backups & Atomic Writes

- **Backup Directory**: `~/.local/share/hks/backups` (overridable via `HKS_BACKUP_DIR` for tests).
- **Outside Config Dir Guard**: `resolve_backup_dir()` refuses any path inside the Hyprland configuration directory so `source = ~/.config/hypr/*` globs can never accidentally load backup files.
- **Backup Format**: `<basename>.<YYYYmmdd-HHMMSS>-<shorthash8>` copied with `shutil.copy2` (preserving permissions and metadata) and indexed in an append-only `backups.json` manifest (`BackupRecord`: `id`, `original_path`, `backup_path`, `sha256`, `created_at`).
- **Safe Restore (`restore_backup`)**: Verifies the backup file's SHA-256 against the index record, checks `expected_current_sha256` against the current target file on disk (refusing with `BackupConflictError` if someone edited the file in the meantime, unless `force=True`), and writes atomically via a temporary file in the target directory + `os.fsync()` + `os.replace()` + directory fsync.

### 2.2 `edit_plan.py` — Line-Oriented Transformations

- **`EditOp` Dataclass**:
  - `kind`: `"comment_out" | "uncomment" | "delete_line" | "replace_line" | "insert_after"`
  - `file`: target file path
  - `line_number`: 1-based line number
  - `expected_text`: exact current line content (without line ending)
  - `new_text`: replacement/inserted line content (for `replace_line` and `insert_after`)
  - `language`: `"lua" | "hyprlang"`
- **Deterministic Formatting Preservation (`apply_ops_to_text`)**:
  - Splits lines while preserving original line endings (`\n` vs `\r\n`) and whether the file has a trailing newline.
  - Verifies every op's `expected_text` against the actual line before modifying anything; raises `EditConflict` with all mismatches if any line differs.
  - Applies operations in **reverse line-number order** so multi-line edits in the same file never shift earlier line numbers.
  - `comment_out` prefixes `-- HKS-disabled: ` (Lua) or `# HKS-disabled: ` (Hyprlang) after leading indentation so round-trip `comment_out` -> `uncomment` is byte-for-byte identical.
- **Loop-Generated Bind Guard (`build_op_for_bind`)**:
  - If `bind.generated` is `True` (a `for` loop in `hyprland.lua` emitting multiple binds from one call site), raises `NotEditableError` pointing to `file:line` and explaining how many binds are generated at that site.

### 2.3 `validator.py` — Three-Layer Candidate Verification

Candidate edits are staged in an isolated temporary copy of `config_dir` (`stage_candidate_config`, which skips `*.bak*`, `backups/`, and `.git/`) so relative `require` and `source` directives resolve naturally without touching the real config directory:

1. **Layer 1 — `verify_with_hyprland(candidate_entrypoint)`**:
   - Runs `Hyprland --verify-config --config <candidate_entrypoint>` with `stdin=DEVNULL` and a 20s timeout.
   - Parses output after `"Config parsing result:"`, ignoring pre-header IPC/Socket log noise (`[IPC::Socket2...]`), and extracts structured `file:line: message` errors (including C-function call errors reported on `=[C]:-1:`).
   - Degrades gracefully (`VerifyResult(ok=None, reason="hyprland_unavailable")`) if the `Hyprland` binary is not installed.
2. **Layer 2 — `verify_with_recorder(candidate_entrypoint, candidate_config_dir)`**:
   - Runs the HKS Lua 5.4 sandbox recorder (`parse_lua_config`) or Hyprlang parser (`parse_hyprlang_config`) on the staged candidate.
   - Raises `RecorderVerificationError` if `complete` is `False` or any `"error"`-level diagnostic is emitted.
3. **Layer 3 — `compare_bind_sets(before_binds, after_binds, ops)`**:
   - Computes directory-independent semantic signatures (`submap`, `modmask`, `key`, `flags`, `dispatcher.path`, `dispatcher.arg_summary`) before and after the edit.
   - Verifies that no partial/broken binds were introduced and that the multiset delta matches the exact binds targeted by `ops` (even when commenting out one bind from a stacked/duplicate shortcut group).

### 2.4 `apply.py` — End-to-End Pipeline & Auto-Rollback

`apply_edit(ops, config_dir, entrypoint, dry_run=True, reload=False, scan_sha256=...)`:

1. Reads the target file and verifies `scan_sha256` (if provided) to reject stale scans on concurrent edits.
2. Applies `ops` in memory via `apply_ops_to_text` and generates a unified diff (`generate_unified_diff`).
3. Stages the candidate in a temp directory and runs Layer 1 (`verify_with_hyprland`), Layer 2 (`verify_with_recorder`), and Layer 3 (`compare_bind_sets`). If any layer fails, returns `ApplyResult(applied=False)` with zero disk writes and zero backups created.
4. Checks whether a companion `hyprland.conf` / `hyprland.lua` exists in `config_dir` and is now out of sync (`companion_warning`), without modifying the companion file.
5. If `dry_run=True` (the default), returns `ApplyResult(applied=False, verify=..., diff=...)`.
6. If `dry_run=False` (`--apply`):
   - Re-checks the target file's SHA-256 to prevent TOCTOU races during verification.
   - Creates a backup via `create_backup`.
   - Writes the new bytes atomically via `atomic_write_bytes` and verifies the written file's SHA-256.
   - If `reload=True` (`--reload`): runs `hyprctl reload config-only`, sleeps `1.0s`, and inspects `hyprctl configerrors`. If `reload` fails or `configerrors` is non-empty, **automatically rolls back** to the backup via `restore_backup(..., force=True)` and returns `ApplyResult(applied=False, rolled_back=True, errors=[...])`.

---

## 3. Known Limitations

1. **Unverified Bad Dispatcher Arguments at Config Parse Time**:
   - Certain invalid dispatcher arguments—such as shell command typos inside `hl.dsp.exec_cmd("nonexistent_binary --bad-flag")` or raw string arguments that Hyprland only evaluates at key-press dispatch time rather than config parse time—pass `Hyprland --verify-config`, pass the Lua 5.4 recorder sandbox, and produce no `hyprctl configerrors` on reload.
   - While structural Lua/Hyprlang errors and C-binding argument validation errors (e.g., `hl.dsp.window.move({ direction = "invalid" })`) are caught by `Hyprland --verify-config`, runtime-only command strings are not validated by Hyprland until triggered.
2. **Lua ConfigManager vs `.conf` Verification**:
   - On Hyprland builds using `Config::Lua::CConfigManager`, `Hyprland --verify-config --config file.conf` may report `config ok` without evaluating `.conf` directives. Layer 2 (`verify_with_recorder` via `parse_hyprlang_config`) and Layer 3 (`compare_bind_sets`) enforce `.conf` bind syntax and bind-set delta checks.
3. **Single-Line Bind Directives**:
   - `comment_out` and `uncomment` operate on single-line bind declarations (`source_line`). Multi-line Lua statements or loop-generated binds (`generated=true`) are not edited automatically.

---

## 4. CLI Usage & Exit Codes

```bash
# 1. Dry-run (default): preview unified diff and 3-layer verification without modifying files
python3 -m backend.cli edit --comment-out <BIND_ID>

# 2. Apply edit atomically (creates backup in ~/.local/share/hks/backups first)
python3 -m backend.cli edit --apply --comment-out <BIND_ID>

# 3. Apply edit and trigger live reload with automatic rollback on configerrors
python3 -m backend.cli edit --apply --reload --comment-out <BIND_ID>

# 4. Uncomment a previously HKS-disabled bind
python3 -m backend.cli edit --apply --uncomment <BIND_ID>

# 5. List backups
python3 -m backend.cli backups

# 6. Restore a backup by ID (requires --apply)
python3 -m backend.cli restore <BACKUP_ID> --apply
```

### Exit Codes

- `0`: Success (dry-run verified cleanly, edit applied, backups listed, or backup restored).
- `1`: Verification failed, bind is loop-generated (`NotEditableError`), line/hash conflict (`EditConflict` / `BackupConflictError`), bind ID not found, or live reload failed and rolled back.
- `2`: CLI usage error (e.g., missing `--comment-out`/`--uncomment`, `--reload` without `--apply`, `restore` without `--apply`).

---

## 5. Real-Config Apply/Undo Round-Trip Verification (SUPER+grave)

A live end-to-end gate was executed against `~/.config/hypr/hyprland.lua` under explicit user approval using only `python3 -m backend.cli edit/restore`:

| Check | Expected | Actual | PASS/FAIL |
| :--- | :--- | :--- | :--- |
| **Step 1**: Pre-edit hash $H_0$ | `12c896420f61a39ee1492e661503e17a9e12b1fc5ac125f3792af8eeb79838f2` | `12c896420f61a39ee1492e661503e17a9e12b1fc5ac125f3792af8eeb79838f2` | **PASS** |
| **Step 1**: Pre-edit live count $N_0$ | `123` | `123` | **PASS** |
| **Step 1**: Pre-edit `hyprctl configerrors` | Empty | Empty (`""`) | **PASS** |
| **Step 1**: Pre-edit oracle comparison | Status: MATCH (parser=123, live=123) | Status: MATCH (parser=123, live=123) | **PASS** |
| **Step 2**: Dynamic bind lookup (`SUPER+grave`) | Single match `b_3d670662aa1d` at line 230 | Single match `b_3d670662aa1d` at line 230 | **PASS** |
| **Step 2**: Dry-run preview | Exit code 0, unified diff displayed, zero disk writes | Exit code 0, unified diff displayed, zero disk writes | **PASS** |
| **Step 3**: Apply `--comment-out` + `--reload` | Exit code 0, `rolled_back=false`, `Result: APPLIED` | Exit code 0, `rolled_back=false`, `Result: APPLIED` | **PASS** |
| **Step 3**: Post-apply live count | $N_0 - 1 = 122$ | `122` | **PASS** |
| **Step 3**: Post-apply `hyprctl configerrors` | Empty | Empty (`""`) | **PASS** |
| **Step 3**: Disabled line content | Starts with `-- HKS-disabled:` | `-- HKS-disabled: hl.bind(mainMod .. " + grave", ...)` | **PASS** |
| **Step 3**: Backup creation | Created in `~/.local/share/hks/backups/` | `hyprland.lua.20261107-112406-12c89642` created | **PASS** |
| **Step 3**: Post-apply oracle comparison | Status: MATCH (parser=122, live=122) | Status: MATCH (parser=122, live=122) | **PASS** |
| **Step 4**: Undo `restore --apply` + live reload | Exit code 0, restored from backup | Exit code 0, restored from backup | **PASS** |
| **Step 4**: Post-restore hash | Exactly $H_0$ (`12c89642...`) | Byte-identical to $H_0$ | **PASS** |
| **Step 4**: Post-restore live count | $N_0 = 123$ | `123` | **PASS** |
| **Step 4**: Post-restore `hyprctl configerrors` | Empty | Empty (`""`) | **PASS** |
| **Step 4**: Post-restore oracle comparison | Status: MATCH (parser=123, live=123) | Status: MATCH (parser=123, live=123) | **PASS** |
| **Step 5**: Injected runner reload failure test | Automatic rollback to backup on reload failure | `TestApplyPipeline.test_reload_failure_triggers_automatic_rollback` verified | **PASS** |

