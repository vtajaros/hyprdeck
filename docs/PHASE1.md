# Hyprland Keybind Studio (HKS) — Phase 1 Architecture & Reference

## 1. Overview

Phase 1 of **Hyprland Keybind Studio (HKS)** provides a strictly read-only configuration discovery engine, a dual-language keybinding parser (Lua 5.4 and Hyprlang `.conf`), a deterministic JSON serializer with JSON Schema 2020-12 validation, and a live `hyprctl binds -j` oracle comparator.

Key guarantees:
- **Zero Side Effects**: Never writes, renames, reloads, or dispatches anything in `~/.config/hypr` or Hyprland.
- **No Directory Globbing**: Only the entrypoint (`hyprland.lua` or `hyprland.conf`) and files explicitly loaded (`dofile`, `loadfile`, `require`, `io.open`, `source = ...`) are read. Backup files (`*.bak*`, `*.pre-reload.bak`) are untouched.
- **Zero Silent Drops**: Every unsupported flag, unknown modifier, unresolved variable, or runtime failure is recorded as a structured diagnostic or a bind with `parse_status != "ok"`.

---

## 2. How to Run

```bash
# Scan active configuration and emit pretty-printed normalized JSON to stdout
python3 -m backend.cli scan

# Scan and compare against live `hyprctl binds -j` multiset oracle
python3 -m backend.cli scan --oracle

# Scan without invoking hyprctl (pure offline file-precedence mode)
python3 -m backend.cli scan --no-live

# Emit compact single-line JSON
python3 -m backend.cli scan --compact

# Print human-readable keybinding table (SHORTCUT | DISPATCHER | ARGS | file:line)
python3 -m backend.cli summary

# Run the unit test suite (uses isolated fixtures only)
python3 -m unittest discover -s backend/tests -v
```

### Exit Codes
- `0`: Success (and oracle multiset matched when `--oracle` is enabled).
- `1`: Oracle mismatch (or `hyprctl binds -j` unavailable when `--oracle` is requested).
- `2`: CLI usage or configuration discovery error (never prints a traceback).

---

## 3. Normalized JSON Field Reference (`schema_version: 1`)

Validated by [`shared/schemas/bindings.schema.json`](../shared/schemas/bindings.schema.json) and [`backend/validation/schema_validator.py`](../backend/validation/schema_validator.py).

### Top-Level Fields
| Field | Type | Description |
| :--- | :--- | :--- |
| `schema_version` | `int` | Always `1`. |
| `tool` | `object` | `{"name": "hyprland-keybind-studio", "version": "0.1.0"}`. |
| `generated_at` | `string` | ISO-8601 UTC timestamp (the only non-deterministic field). |
| `environment` | `object` | `{config_dir, entrypoint, language, detected_by, shadowed[], hyprland_version, python}`. |
| `files` | `array` | Loaded files with `{path, real_path, role, sha256, line_count}`. |
| `binds` | `array` | Normalized keybindings in definition/execution order. |
| `unbinds` | `array` | Normalized `unbind` directives (Hyprlang). |
| `diagnostics` | `array` | `{level, code, message, file, line}`. |
| `stats` | `object` | `{total_binds, by_type, by_dispatcher_path, flag_counts, by_modmask, generated_binds, partial, unsupported, unresolved, ignored_calls, ignored_keywords}`. |
| `complete` | `bool` | `true` if parsing completed without fatal runtime/sandbox errors. |
| `oracle` | `object\|null` | Present when `--oracle` is passed: `{matched, count_match, order_match, parser_count, live_count, missing_in_parser, extra_in_parser}`. |

### Per-Bind Object Fields
| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `string` | `"b_" + sha1("{abs_file}\|{line}\|{occurrence}\|{keys}\|{dispatcher.path}")[:12]`. |
| `language` | `string` | `"lua"` or `"hyprlang"`. |
| `bind_type` | `string` | Canonical `"bind"` + sorted flag letters (`bind`, `bindl`, `bindel`, `bindm`, `bindd`, etc.). |
| `declared_via` | `string\|null` | Call or keyword in source (`"bind"`, `"bindm"`, `"bindel"`, etc.). |
| `modifiers` | `string[]` | Canonical uppercase modifier names (`SUPER`, `SHIFT`, `CTRL`, `ALT`, `CAPS`, `MOD2`, `MOD3`, `MOD5`). |
| `modifiers_raw` | `string` | Raw modifier text before expansion/normalization. |
| `modmask` | `int` | Bitmask (`SHIFT=1, CAPS=2, CTRL=4, ALT=8, MOD2=16, MOD3=32, SUPER=64, MOD5=128`). |
| `key` | `string` | Key identifier verbatim (`Return`, `grave`, `mouse:272`, `XF86AudioMute`, `mouse_up`). |
| `key_kind` | `string` | `"keysym"`, `"mouse_button"`, `"keycode"`, or `"mouse_wheel"`. |
| `keys_raw` | `string` | Raw key combination string. |
| `flags` | `object` | `{ignore_mods, locked, long_press, mouse, non_consuming, release, repeating, transparent}`. |
| `flags_extra` | `object` | Extra or unrecognized options/flags. |
| `description` | `string\|null` | Optional human description (`description` opt or `bindd`). |
| `dispatcher` | `object` | `{path, args, arg_summary, callback_line?}`. |
| `submap` | `string` | Active submap name (`""` for default/global). |
| `source_file` | `string` | Absolute path of the file defining the bind. |
| `source_line` | `int` | 1-based physical line number of the bind call/directive. |
| `original_line` | `string` | Exact line text from `source_file` (line endings stripped). |
| `original_line_number` | `int` | Same as `source_line`. |
| `generated` | `bool` | `true` when `occurrences_at_site > 1` (e.g., created inside a loop). |
| `occurrence` | `int` | 0-based index of this bind at `(source_file, source_line)`. |
| `occurrences_at_site` | `int` | Total binds recorded at `(source_file, source_line)`. |
| `trace` | `array` | Call stack frames `[{file, line, what, istailcall}]`. |
| `parse_status` | `string` | `"ok"`, `"partial"`, `"unsupported"`, or `"unresolved"`. |

---

## 4. Sandbox Threat Model

The Lua front end (`backend/parser/lua/recorder.lua` invoked by `backend/parser/lua_runner.py`) **executes the user's own Lua configuration with a stubbed `hl` API; it prevents accidental side effects; it is NOT a security boundary against a deliberately hostile configuration.**

Defense-in-depth layers applied during execution:
1. **Restricted Lua Environment (`E`)**: Exposes only pure standard library primitives (`assert`, `error`, `ipairs`, `pairs`, `next`, `pcall`, `xpcall`, `select`, `tonumber`, `tostring`, `type`, `rawget`, `rawset`, `rawequal`, `rawlen`, `setmetatable`, `getmetatable`, `string`, `table`, `math`, `utf8`). `debug`, `package`, and `collectgarbage` are hidden.
2. **Filtered `os` & `io` Tables**:
   - `os.getenv` only permits `HOME`, `XDG_CONFIG_HOME`, `XDG_SESSION_TYPE`, `USER`, `LANG`. `os.time`, `os.date`, `os.clock` are allowed. Any other `os.*` call (`os.execute`, `os.remove`, etc.) is blocked and emits `sandbox_denied`.
   - `io.open` only permits read modes (`"r"`, `"rb"`) on paths that normalize inside `config_dir`. Write modes and `io.popen` are blocked with `sandbox_denied`.
   - `loadfile`, `dofile`, and `require` only load text chunks (`mode = "t"`) inside `config_dir` bound to sandbox environment `E`.
3. **Instruction Budget**: `debug.sethook` fires every `100,000` VM instructions and aborts after `500` hooks (`50,000,000` instructions total) with diagnostic `instruction_limit`, preserving all binds recorded prior to the loop.
4. **OS Process Isolation (`lua_runner.py`)**:
   - Cleared environment variables, `stdin=DEVNULL`, fresh empty temporary working directory, `15s` wall-clock timeout.
   - Kernel resource limits via `resource.setrlimit`: `RLIMIT_CPU = 10s`, `RLIMIT_AS = 512 MiB`, `RLIMIT_FSIZE = 0` (kernel blocks all file writes), `RLIMIT_NOFILE = 64`.
- **TODO (Future Phase)**: Add optional `bubblewrap` (`bwrap --ro-bind ... --unshare-all`) containerization around the `lua5.4` subprocess.

---

## 5. Known Limitations & TODOs

- **Lua Submap Semantics Unverified**: We have not verified how Hyprland's Lua API scopes submaps. All Lua binds set `submap = ""` and emit a `lua_submap_unsupported` warning if any `hl.dsp` path or `hl.*` call contains `"submap"`.
- **Hyprlang Flag Letters & `##` Escape (`TODO`)**: The Hyprlang parser supports flag letters `l, r, e, n, m, t, i, o, s, d` and treats `##` as an escaped literal `#` while single `#` starts a comment. Verify any newly added flag letters or edge-case comment escaping rules against the official Hyprland wiki when targeting newer Hyprland releases.

---

## 6. Real-Config Acceptance Checklist

When running against the primary user configuration (`~/.config/hypr/hyprland.lua`):

```bash
python3 -m backend.cli scan --oracle
```

Expected results:
- [ ] **Total binds**: `126`
- [ ] **Flag counts**: `locked`: `25`, `repeating`: `10`, `mouse`: `2`
- [ ] **Submaps**: None (`submap == ""` on all 126 binds)
- [ ] **Modmask histogram**:
  - `64` (`SUPER`): `51`
  - `65` (`SUPER + SHIFT`): `26`
  - `0` (no modifiers): `21`
  - `8` (`ALT`): `9`
  - `68` (`SUPER + CTRL`): `6`
  - `72` (`SUPER + ALT`): `4`
  - `1` (`SHIFT`): `4`
  - `9` (`ALT + SHIFT`): `2`
  - `69` (`SUPER + CTRL + SHIFT`): `2`
  - `12` (`CTRL + ALT`): `1`
- [ ] **Dispatcher short names**:
  - `exec_cmd`: `47`
  - `move`: `35`
  - `focus`: `30`
  - `close`: `2`
  - `fullscreen`: `2`
  - `cycle_next`: `2`
  - `bring_to_top`: `2`
  - `float`: `1`
  - `pseudo`: `1`
  - `layout`: `1`
  - `toggle_special`: `1`
  - `drag`: `1`
  - `resize`: `1`
- [ ] **Oracle exit code**: `0` (`matched: true`, `missing_in_parser: []`, `extra_in_parser: []`)
