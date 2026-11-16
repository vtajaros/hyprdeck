"""Dispatcher catalog and schema definitions for HyprDeck (Phase 3b)."""

from __future__ import annotations

import json
import re
from typing import Any

DISPATCHER_CATALOG: list[dict[str, Any]] = [
    {
        "id": "exec_cmd",
        "label": "Execute Command",
        "category": "Application",
        "lua_template": 'hl.dsp.exec_cmd({cmd})',
        "hyprlang_name": "exec",
        "args_schema": [
            {
                "name": "cmd",
                "label": "Command",
                "type": "text",
                "required": True,
                "placeholder": "kitty",
                "description": "Shell command or executable to launch.",
            }
        ],
    },
    {
        "id": "window.close",
        "label": "Close Active Window",
        "category": "Window",
        "lua_template": "hl.dsp.window.close()",
        "hyprlang_name": "killactive",
        "args_schema": [],
    },
    {
        "id": "togglefloating",
        "label": "Toggle Floating",
        "category": "Window",
        "lua_template": 'hl.dsp.window.float({ action = "toggle" })',
        "hyprlang_name": "togglefloating",
        "args_schema": [],
    },
    {
        "id": "fullscreen",
        "label": "Toggle Fullscreen",
        "category": "Window",
        "lua_template": 'hl.dsp.window.fullscreen({ mode = "{mode}" })',
        "hyprlang_name": "fullscreen",
        "args_schema": [
            {
                "name": "mode",
                "label": "Mode",
                "type": "enum",
                "options": ["fullscreen", "maximized"],
                "default": "fullscreen",
                "description": "Fullscreen mode (true fullscreen or maximized).",
            }
        ],
    },
    {
        "id": "movefocus",
        "label": "Move Focus Direction",
        "category": "Navigation",
        "lua_template": 'hl.dsp.focus({ direction = "{direction}" })',
        "hyprlang_name": "movefocus",
        "args_schema": [
            {
                "name": "direction",
                "label": "Direction",
                "type": "direction",
                "options": ["left", "right", "up", "down"],
                "default": "left",
                "description": "Direction to move window focus.",
            }
        ],
    },
    {
        "id": "movewindow",
        "label": "Move Window Direction",
        "category": "Window",
        "lua_template": 'hl.dsp.window.move({ direction = "{direction}" })',
        "hyprlang_name": "movewindow",
        "args_schema": [
            {
                "name": "direction",
                "label": "Direction",
                "type": "direction",
                "options": ["left", "right", "up", "down"],
                "default": "left",
                "description": "Direction to shift active window in layout.",
            }
        ],
    },
    {
        "id": "workspace",
        "label": "Switch Workspace",
        "category": "Workspace",
        "lua_template": 'hl.dsp.focus({ workspace = "{workspace}" })',
        "hyprlang_name": "workspace",
        "args_schema": [
            {
                "name": "workspace",
                "label": "Workspace",
                "type": "workspace",
                "required": True,
                "placeholder": "1",
                "description": "Target workspace number (1-10) or relative name (e+1, e-1).",
            }
        ],
    },
    {
        "id": "movetoworkspace",
        "label": "Move Window to Workspace",
        "category": "Workspace",
        "lua_template": 'hl.dsp.window.move({ workspace = "{workspace}"{silent_opt} })',
        "hyprlang_name": "movetoworkspace",
        "args_schema": [
            {
                "name": "workspace",
                "label": "Workspace",
                "type": "workspace",
                "required": True,
                "placeholder": "1",
                "description": "Target workspace name or number.",
            },
            {
                "name": "silent",
                "label": "Silent",
                "type": "bool",
                "default": False,
                "description": "Do not follow window to the destination workspace.",
            },
        ],
    },
    {
        "id": "resizeactive",
        "label": "Resize Window",
        "category": "Window",
        "lua_template": "hl.dsp.window.resize({ x = {dx}, y = {dy}, relative = true })",
        "hyprlang_name": "resizeactive",
        "args_schema": [
            {
                "name": "dx",
                "label": "Horizontal Delta",
                "type": "int",
                "default": 20,
                "description": "Pixels to resize horizontally (positive to grow, negative to shrink).",
            },
            {
                "name": "dy",
                "label": "Vertical Delta",
                "type": "int",
                "default": 0,
                "description": "Pixels to resize vertically.",
            },
        ],
    },
    {
        "id": "pin",
        "label": "Pin Window",
        "category": "Window",
        "lua_template": "hl.dsp.window.pin()",
        "hyprlang_name": "pin",
        "args_schema": [],
    },
    {
        "id": "togglesplit",
        "label": "Toggle Split Direction",
        "category": "Window",
        "lua_template": 'hl.dsp.layout("togglesplit")',
        "hyprlang_name": "togglesplit",
        "args_schema": [],
    },
    {
        "id": "submap",
        "label": "Switch Submap",
        "category": "System",
        "lua_template": 'hl.dsp.submap("{submap}")',
        "hyprlang_name": "submap",
        "args_schema": [
            {
                "name": "submap",
                "label": "Submap Name",
                "type": "text",
                "required": True,
                "placeholder": "reset",
                "description": "Name of submap to activate ('reset' to return to default).",
            }
        ],
    },
    {
        "id": "custom",
        "label": "Custom Expression",
        "category": "Advanced",
        "lua_template": "{expr}",
        "hyprlang_name": "custom",
        "args_schema": [
            {
                "name": "expr",
                "label": "Expression",
                "type": "text",
                "required": True,
                "placeholder": "hl.dsp.exec_cmd('...')",
                "description": "Raw Lua expression or Hyprlang dispatcher and arguments.",
            }
        ],
    },
]


LUA_TO_HYPRLANG_DISPATCHER_MAP: dict[str, str] = {
    "exec_cmd": "exec",
    "window.close": "killactive",
    "window.float": "togglefloating",
    "window.fullscreen": "fullscreen",
    "focus": "movefocus",
    "window.move": "movewindow",
    "window.resize": "resizeactive",
    "window.pin": "pin",
    "layout": "layoutmsg",
    "submap": "submap",
}

_WORKSPACE_SELECTOR_RE = re.compile(
    r"^(?:\d+|[+-]\d+|[erm][+-]\d+|name:[^,\n\r]+|special(?::[^,\n\r]+)?|previous|empty)$"
)
_SUBMAP_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_INT_RE = re.compile(r"^[+-]?\d+$")
_DIRECTION_MAP: dict[str, str] = {
    "left": "l",
    "right": "r",
    "up": "u",
    "down": "d",
    "l": "l",
    "r": "r",
    "u": "u",
    "d": "d",
}
_LUA_ESCAPES: dict[str, str] = {
    "\\": "\\",
    '"': '"',
    "'": "'",
    "n": "\n",
    "t": "\t",
    "r": "\r",
}


def _decode_lua_string(raw: str) -> str:
    """Decode a single quoted Lua string literal, or raise ValueError."""
    s = raw.strip()
    if len(s) < 2 or s[0] not in ('"', "'") or s[-1] != s[0]:
        raise ValueError(f"Lua string {raw!r} is not supported for Hyprlang")
    quote = s[0]
    out: list[str] = []
    i = 1
    end = len(s) - 1
    while i < end:
        ch = s[i]
        if ch == "\\":
            if i + 1 >= end:
                raise ValueError(f"Unterminated escape in Lua string {raw!r} is not supported for Hyprlang")
            esc = s[i + 1]
            if esc.isdigit():
                j = i + 1
                while j < end and j < i + 4 and s[j].isdigit():
                    j += 1
                code = int(s[i + 1 : j])
                if code > 255:
                    raise ValueError(f"Out-of-range decimal escape in Lua string {raw!r} is not supported for Hyprlang")
                out.append(chr(code))
                i = j
                continue
            if esc not in _LUA_ESCAPES:
                raise ValueError(f"Unsupported escape '\\{esc}' in Lua string {raw!r} is not supported for Hyprlang")
            out.append(_LUA_ESCAPES[esc])
            i += 2
            continue
        if ch == quote:
            raise ValueError(f"Malformed Lua string {raw!r} is not supported for Hyprlang")
        out.append(ch)
        i += 1
    return "".join(out)


def _maybe_decode_lua_string(raw: str) -> str:
    """If raw looks like a Lua quoted/long string, decode it or raise ValueError; otherwise return raw."""
    s = raw.strip()
    if not s:
        return s
    if s.startswith("[[") or s.startswith("[="):
        raise ValueError(f"Lua long string {raw!r} is not supported for Hyprlang")
    if s[0] in ('"', "'"):
        return _decode_lua_string(s)
    return s


def _is_valid_workspace_selector(val: str) -> bool:
    """Return True iff val matches a documented Hyprland workspace selector."""
    if not val or val != val.strip():
        return False
    if not _WORKSPACE_SELECTOR_RE.fullmatch(val):
        return False
    if val.startswith("name:") and not val[len("name:"):].strip():
        return False
    if val.startswith("special:") and not val[len("special:"):].strip():
        return False
    return True


def _parse_lua_table(raw: str) -> dict[str, Any]:
    """Parse a flat Lua table literal like `{ workspace = 2, silent = true }`."""
    s = raw.strip()
    if not (s.startswith("{") and s.endswith("}")):
        raise ValueError(f"Expected Lua table, got {raw!r}")
    inner = s[1:-1].strip()
    if not inner:
        return {}
    # Split on top-level commas respecting quotes
    parts: list[str] = []
    cur: list[str] = []
    in_str: str | None = None
    in_esc = False
    for ch in inner:
        if in_esc:
            in_esc = False
            cur.append(ch)
            continue
        if ch == "\\" and in_str is not None:
            in_esc = True
            cur.append(ch)
            continue
        if in_str is not None:
            if ch == in_str:
                in_str = None
            cur.append(ch)
            continue
        if ch in ('"', "'"):
            in_str = ch
            cur.append(ch)
            continue
        if ch in ("(", "[", "{"):
            raise ValueError(f"Nested Lua expression {raw!r} is not supported for Hyprlang")
        if ch == ",":
            parts.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    if cur:
        parts.append("".join(cur).strip())

    result: dict[str, Any] = {}
    for item in parts:
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"Positional table entry {item!r} is not supported for Hyprlang")
        k, v = item.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k.isidentifier():
            raise ValueError(f"Unsupported Lua table key {k!r} for Hyprlang")
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            result[k] = _decode_lua_string(v)
        elif v == "true":
            result[k] = True
        elif v == "false":
            result[k] = False
        elif _INT_RE.fullmatch(v):
            result[k] = int(v)
        else:
            raise ValueError(f"Unsupported Lua table value {v!r} for Hyprlang")
    return result


def map_lua_dispatcher_to_hyprlang(
    dispatcher: str,
    args: str | None = None,
    is_mouse: bool = False,
    decode_lua_literals: bool = True,
) -> tuple[str, str | None]:
    """Losslessly map a Lua or catalog dispatcher (+ optional Lua table args) to Hyprlang.

    Raises ValueError with 'not supported for Hyprlang' when the dispatcher or its
    arguments have no safe, lossless Hyprlang equivalent.
    """
    clean = dispatcher.strip()
    key = clean.lower()
    if key.startswith("hl.dsp."):
        key = key[len("hl.dsp."):]

    clean_args = args.strip() if args is not None else ""
    is_table = clean_args.startswith("{") and clean_args.endswith("}")
    table: dict[str, Any] | None = None
    if is_table:
        try:
            table = _parse_lua_table(clean_args)
        except ValueError as exc:
            raise ValueError(f"Dispatcher '{clean}' args are not supported for Hyprlang: {exc}") from exc

    if key in ("exec_cmd", "exec"):
        if table is not None:
            if set(table.keys()) != {"cmd"} or not isinstance(table["cmd"], str) or not table["cmd"].strip():
                raise ValueError(f"Dispatcher '{clean}' table args {clean_args!r} are not supported for Hyprlang")
            return "exec", table["cmd"].strip()
        decoded = _maybe_decode_lua_string(clean_args) if decode_lua_literals else clean_args
        if not decoded.strip():
            raise ValueError(f"Dispatcher '{clean}' with empty args is not supported for Hyprlang")
        return "exec", decoded.strip()

    if key in ("window.close", "killactive"):
        if clean_args and table != {}:
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        return "killactive", None

    if key in ("window.pin", "pin"):
        if clean_args and table != {}:
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        return "pin", None

    if key in ("window.float", "togglefloating"):
        if not clean_args or table == {}:
            return "togglefloating", None
        if table is not None:
            if set(table.keys()) == {"action"} and isinstance(table["action"], str) and table["action"].strip().lower() == "toggle":
                return "togglefloating", None
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang (only action='toggle' is lossless)")
        decoded = _maybe_decode_lua_string(clean_args)
        if decoded.strip().lower() == "toggle":
            return "togglefloating", None
        raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")

    if key in ("window.fullscreen", "fullscreen"):
        if not clean_args or table == {}:
            return "fullscreen", "0"
        if table is not None:
            if set(table.keys()) == {"mode"}:
                mode_val = table["mode"]
                if isinstance(mode_val, int) and not isinstance(mode_val, bool) and mode_val in (0, 1):
                    return "fullscreen", str(mode_val)
                if isinstance(mode_val, str):
                    mode = mode_val.strip().lower()
                    if mode in ("0", "fullscreen"):
                        return "fullscreen", "0"
                    if mode in ("1", "maximized"):
                        return "fullscreen", "1"
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        val = _maybe_decode_lua_string(clean_args).strip().lower()
        if val in ("0", "fullscreen"):
            return "fullscreen", "0"
        if val in ("1", "maximized"):
            return "fullscreen", "1"
        raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")

    if key in ("focus", "movefocus"):
        if table is not None:
            if set(table.keys()) == {"direction"} and isinstance(table["direction"], str):
                d = _DIRECTION_MAP.get(table["direction"].strip().lower())
                if d is not None:
                    return "movefocus", d
            if set(table.keys()) == {"workspace"}:
                ws = str(table["workspace"]).strip()
                if _is_valid_workspace_selector(ws):
                    return "workspace", ws
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        val = _maybe_decode_lua_string(clean_args).strip()
        d = _DIRECTION_MAP.get(val.lower())
        if d is not None:
            return "movefocus", d
        if _is_valid_workspace_selector(val):
            return "workspace", val
        raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")

    if key in ("window.move", "movewindow"):
        if not clean_args or table == {}:
            if is_mouse:
                return "movewindow", None
            raise ValueError(f"Dispatcher '{clean}' with empty args is only valid for mouse binds and is not supported for Hyprlang")
        if table is not None:
            if set(table.keys()) == {"direction"} and isinstance(table["direction"], str):
                d = _DIRECTION_MAP.get(table["direction"].strip().lower())
                if d is not None:
                    return "movewindow", d
            if set(table.keys()) <= {"workspace", "silent"} and "workspace" in table:
                silent = table.get("silent", False)
                ws = str(table["workspace"]).strip()
                if isinstance(silent, bool) and _is_valid_workspace_selector(ws):
                    return ("movetoworkspacesilent" if silent else "movetoworkspace"), ws
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        val = _maybe_decode_lua_string(clean_args).strip()
        d = _DIRECTION_MAP.get(val.lower())
        if d is not None:
            return "movewindow", d
        if _is_valid_workspace_selector(val):
            return "movetoworkspace", val
        raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")

    if key == "workspace":
        if table is not None:
            if set(table.keys()) == {"workspace"}:
                ws = str(table["workspace"]).strip()
                if _is_valid_workspace_selector(ws):
                    return "workspace", ws
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        val = _maybe_decode_lua_string(clean_args).strip()
        if _is_valid_workspace_selector(val):
            return "workspace", val
        raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")

    if key in ("movetoworkspace", "movetoworkspacesilent"):
        if table is not None:
            if set(table.keys()) <= {"workspace", "silent"} and "workspace" in table:
                silent = table.get("silent", key == "movetoworkspacesilent")
                ws = str(table["workspace"]).strip()
                if isinstance(silent, bool) and _is_valid_workspace_selector(ws):
                    return ("movetoworkspacesilent" if silent else "movetoworkspace"), ws
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        val = _maybe_decode_lua_string(clean_args).strip()
        if _is_valid_workspace_selector(val):
            return key, val
        raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")

    if key in ("window.resize", "resizeactive"):
        if table is not None:
            if (
                set(table.keys()) == {"x", "y", "relative"}
                and table["relative"] is True
                and isinstance(table["x"], int)
                and not isinstance(table["x"], bool)
                and isinstance(table["y"], int)
                and not isinstance(table["y"], bool)
            ):
                return "resizeactive", f"{table['x']} {table['y']}"
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        decoded = _maybe_decode_lua_string(clean_args).strip()
        parts = decoded.split()
        if len(parts) == 2 and all(_INT_RE.fullmatch(p) for p in parts):
            return "resizeactive", f"{int(parts[0])} {int(parts[1])}"
        raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")

    if key in ("layout", "togglesplit", "layoutmsg"):
        if key == "togglesplit" and (not clean_args or table == {}):
            return "layoutmsg", "togglesplit"
        if table is not None:
            if key == "layout" and set(table.keys()) == {"action"} and isinstance(table["action"], str) and table["action"].strip().lower() == "togglesplit":
                return "layoutmsg", "togglesplit"
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        val = _maybe_decode_lua_string(clean_args).strip().lower()
        if val == "togglesplit":
            return "layoutmsg", "togglesplit"
        raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")

    if key == "submap":
        if table is not None:
            if set(table.keys()) == {"submap"} and isinstance(table["submap"], str):
                sm = table["submap"].strip()
                if _SUBMAP_RE.fullmatch(sm):
                    return "submap", sm
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        val = _maybe_decode_lua_string(clean_args).strip()
        if _SUBMAP_RE.fullmatch(val):
            return "submap", val
        raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")

    raise ValueError(f"Dispatcher '{clean}' is not supported for Hyprlang")


def get_catalog() -> list[dict[str, Any]]:
    """Return the data-driven dispatcher catalog."""
    return list(DISPATCHER_CATALOG)


def get_dispatcher_by_id(dispatcher_id: str) -> dict[str, Any] | None:
    """Find a catalog entry by its identifier or alias."""
    clean = dispatcher_id.strip().lower()
    for item in DISPATCHER_CATALOG:
        if item["id"].lower() == clean:
            return item
        if item["hyprlang_name"].lower() == clean:
            return item
    # Check common aliases
    alias_map = {
        "killactive": "window.close",
        "close": "window.close",
        "exec": "exec_cmd",
        "float": "togglefloating",
        "movefocus": "movefocus",
        "focus": "movefocus",
    }
    target_id = alias_map.get(clean)
    if target_id:
        for item in DISPATCHER_CATALOG:
            if item["id"] == target_id:
                return item
    return None


def render_from_catalog(
    dispatcher_id: str,
    args: dict[str, Any] | str | None,
    language: str = "lua",
) -> tuple[str, str | None]:
    """Render dispatcher name and argument string from catalog item and argument dict.

    Returns:
      For Lua: (dispatcher_call_or_path, arg_summary)
      For Hyprlang: (dispatcher_name, arg_string)
    """
    entry = get_dispatcher_by_id(dispatcher_id)
    if entry is None:
        # Fall back as a raw dispatcher
        if isinstance(args, dict):
            args_str = json.dumps(args)
        else:
            args_str = str(args) if args is not None else None
        return dispatcher_id, args_str

    if isinstance(args, str):
        try:
            parsed_args = json.loads(args) if args.strip().startswith("{") else {"cmd": args, "expr": args, "workspace": args, "submap": args}
        except Exception:
            parsed_args = {"cmd": args, "expr": args, "workspace": args, "submap": args}
    elif isinstance(args, dict):
        parsed_args = dict(args)
    else:
        parsed_args = {}

    d_id = entry["id"]

    if d_id == "custom":
        raw = parsed_args.get("expr", "")
        if language == "lua":
            return raw, raw
        parts = raw.split(",", 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
        return raw.strip(), None

    if language == "lua":
        if d_id == "exec_cmd":
            cmd = str(parsed_args.get("cmd", ""))
            if not cmd.strip():
                raise ValueError("Dispatcher 'exec_cmd' requires non-empty arguments")
            from backend.editor.codegen import encode_lua_string
            return "exec_cmd", encode_lua_string(cmd)

        if d_id == "window.close":
            return "window.close", None

        if d_id == "togglefloating":
            return 'window.float({ action = "toggle" })', None

        if d_id == "fullscreen":
            mode = parsed_args.get("mode", "fullscreen")
            return f'window.fullscreen({{ mode = "{mode}" }})', None

        if d_id == "movefocus":
            direction = parsed_args.get("direction", "left")
            return f'focus({{ direction = "{direction}" }})', None

        if d_id == "movewindow":
            direction = parsed_args.get("direction", "left")
            return f'window.move({{ direction = "{direction}" }})', None

        if d_id == "workspace":
            ws = str(parsed_args.get("workspace", "1"))
            # If number
            if ws.isdigit():
                return f"focus({{ workspace = {ws} }})", None
            return f'focus({{ workspace = "{ws}" }})', None

        if d_id == "movetoworkspace":
            ws = str(parsed_args.get("workspace", "1"))
            silent = bool(parsed_args.get("silent", False))
            ws_val = ws if ws.isdigit() else f'"{ws}"'
            silent_opt = ", silent = true" if silent else ""
            return f"window.move({{ workspace = {ws_val}{silent_opt} }})", None

        if d_id == "resizeactive":
            dx = int(parsed_args.get("dx", 20))
            dy = int(parsed_args.get("dy", 0))
            return f"window.resize({{ x = {dx}, y = {dy}, relative = true }})", None

        if d_id == "pin":
            return "window.pin()", None

        if d_id == "togglesplit":
            return 'layout("togglesplit")', None

        if d_id == "submap":
            sub = parsed_args.get("submap", "reset")
            return f'submap("{sub}")', None

        return entry["id"], None

    # Hyprlang
    hl_name = entry["hyprlang_name"]
    if d_id == "exec_cmd":
        cmd = str(parsed_args.get("cmd", ""))
        if not cmd.strip():
            raise ValueError("Dispatcher 'exec_cmd' requires non-empty arguments")
        if "\x00" in cmd or "\n" in cmd or "\r" in cmd:
            raise ValueError("Newlines and NUL bytes are not allowed in exec_cmd arguments")
        return hl_name, cmd
    if d_id in ("window.close", "togglefloating", "pin", "togglesplit"):
        return hl_name, None
    if d_id == "fullscreen":
        mode = parsed_args.get("mode", "fullscreen")
        return hl_name, ("0" if mode == "fullscreen" else "1")
    if d_id in ("movefocus", "movewindow"):
        return hl_name, str(parsed_args.get("direction", "left"))
    if d_id == "workspace":
        return hl_name, str(parsed_args.get("workspace", "1"))
    if d_id == "movetoworkspace":
        silent = bool(parsed_args.get("silent", False))
        ws = str(parsed_args.get("workspace", "1"))
        return ("movetoworkspacesilent" if silent else "movetoworkspace"), ws
    if d_id == "resizeactive":
        dx = int(parsed_args.get("dx", 20))
        dy = int(parsed_args.get("dy", 0))
        return hl_name, f"{dx} {dy}"
    if d_id == "submap":
        return hl_name, str(parsed_args.get("submap", "reset"))

    return hl_name, None
