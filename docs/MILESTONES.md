# Hyprland Keybind Studio (HKS) — Phase 1 Milestones

| Deliverable | Component | Status |
| :--- | :--- | :--- |
| Project layout & data models | `backend/models/types.py`, `.gitignore` | [x] Complete |
| Read-only config & entrypoint discovery (no globbing) | `backend/discovery/config_discovery.py` | [x] Complete |
| Live `hyprctl` cross-check (`version -j`, `binds -j`) | `backend/discovery/config_discovery.py` | [x] Complete |
| Sandboxed Lua 5.4 bind recorder & deterministic JSON encoder | `backend/parser/lua/recorder.lua` | [x] Complete |
| Subprocess runner with `setrlimit` & timeout isolation | `backend/parser/lua_runner.py` | [x] Complete |
| Lua bind normalization, modifier bitmask & ID generation | `backend/parser/lua_normalizer.py`, `backend/parser/modifiers.py` | [x] Complete |
| Hyprlang (`.conf`) line state machine & recursive `source` loader | `backend/parser/hyprlang_parser.py` | [x] Complete |
| JSON Schema 2020-12 & stdlib schema validator | `shared/schemas/bindings.schema.json`, `backend/validation/schema_validator.py` | [x] Complete |
| Live `hyprctl binds -j` multiset oracle comparator | `backend/validation/oracle.py` | [x] Complete |
| CLI (`scan`, `scan --oracle`, `summary`) with clean exit codes | `backend/cli.py`, `backend/serializer/json_serializer.py` | [x] Complete |
| Unit tests (Discovery, Lua fixture, Sandbox, Hyprlang, Serializer, Oracle) | `backend/tests/` | [x] Complete |
| Phase 1 architecture & acceptance documentation | `docs/PHASE1.md`, `docs/MILESTONES.md`, `README.md` | [x] Complete |

---

## Verified on Real Config

- **Binds**: 126 binds
- **Oracle Comparison**: MATCH (exact count and order match against live `hyprctl binds -j`)
- **Parity**: Hyprlang vs Lua parity equal
- **Performance**: Scan time about 0.1 s
