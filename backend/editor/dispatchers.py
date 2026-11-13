"""Dispatcher catalog and schema definitions for Hyprland Keybind Studio (Phase 3b)."""

from __future__ import annotations

import json
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
        "lua_template": "hl.dsp.window.resize({ dx = {dx}, dy = {dy} })",
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
    "layout": "togglesplit",
    "submap": "submap",
}

HYPRLANG_NATIVE_DISPATCHERS: frozenset[str] = frozenset({
    "exec",
    "killactive",
    "togglefloating",
    "fullscreen",
    "movefocus",
    "movewindow",
    "resizewindow",
    "resizeactive",
    "workspace",
    "movetoworkspace",
    "movetoworkspacesilent",
    "pin",
    "togglesplit",
    "submap",
})


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
            result[k] = v[1:-1]
        elif v == "true":
            result[k] = True
        elif v == "false":
            result[k] = False
        elif v.lstrip("+-").isdigit():
            result[k] = int(v)
        else:
            raise ValueError(f"Unsupported Lua table value {v!r} for Hyprlang")
    return result


def map_lua_dispatcher_to_hyprlang(
    dispatcher: str,
    args: str | None = None,
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

    # Native Hyprlang dispatchers (not Lua-prefixed)
    if clean.lower() in HYPRLANG_NATIVE_DISPATCHERS and not clean.lower().startswith("hl.dsp."):
        if table is not None:
            # Allow table translation via the same rules below if applicable
            pass
        else:
            return clean, (clean_args or None)

    if key == "exec_cmd" or key == "exec":
        if table is not None:
            if set(table.keys()) != {"cmd"} or not str(table["cmd"]).strip():
                raise ValueError(f"Dispatcher '{clean}' table args {clean_args!r} are not supported for Hyprlang")
            return "exec", str(table["cmd"]).strip()
        if not clean_args:
            raise ValueError(f"Dispatcher '{clean}' requires non-empty arguments")
        return "exec", clean_args

    if key in ("window.close", "killactive"):
        if clean_args and table != {}:
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        return "killactive", None

    if key in ("window.pin", "pin"):
        if clean_args and table != {}:
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        return "pin", None

    if key in ("window.float", "togglefloating"):
        if not clean_args:
            return "togglefloating", None
        if table is not None:
            if set(table.keys()) == {"action"} and str(table["action"]).lower() == "toggle":
                return "togglefloating", None
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang (only action='toggle' is lossless)")
        if clean_args.strip("\"'").lower() == "toggle":
            return "togglefloating", None
        raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")

    if key in ("window.fullscreen", "fullscreen"):
        if not clean_args:
            return "fullscreen", "0"
        if table is not None:
            if set(table.keys()) == {"mode"}:
                mode = str(table["mode"]).lower()
                if mode == "fullscreen":
                    return "fullscreen", "0"
                if mode == "maximized":
                    return "fullscreen", "1"
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        val = clean_args.strip("\"'").lower()
        if val in ("0", "fullscreen"):
            return "fullscreen", "0"
        if val in ("1", "maximized"):
            return "fullscreen", "1"
        raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")

    if key in ("focus", "movefocus"):
        if table is not None:
            if set(table.keys()) == {"direction"}:
                d = str(table["direction"]).lower()
                if d in ("left", "right", "up", "down", "l", "r", "u", "d"):
                    return "movefocus", d
            if set(table.keys()) == {"workspace"} and str(table["workspace"]).strip():
                return "workspace", str(table["workspace"]).strip()
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        val = clean_args.strip("\"'")
        if val.lower() in ("left", "right", "up", "down", "l", "r", "u", "d"):
            return "movefocus", val.lower()
        if val and val.lstrip("+-e").isdigit():
            return "workspace", val
        raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")

    if key in ("window.move", "movewindow"):
        if table is not None:
            if set(table.keys()) == {"direction"}:
                d = str(table["direction"]).lower()
                if d in ("left", "right", "up", "down", "l", "r", "u", "d"):
                    return "movewindow", d
            if set(table.keys()) <= {"workspace", "silent"} and "workspace" in table:
                ws = str(table["workspace"]).strip()
                if ws:
                    silent = bool(table.get("silent", False))
                    return ("movetoworkspacesilent" if silent else "movetoworkspace"), ws
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        val = clean_args.strip("\"'")
        if val.lower() in ("left", "right", "up", "down", "l", "r", "u", "d"):
            return "movewindow", val.lower()
        if val and val.lstrip("+-e").isdigit():
            return "movetoworkspace", val
        raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")

    if key == "workspace":
        if table is not None:
            if set(table.keys()) == {"workspace"} and str(table["workspace"]).strip():
                return "workspace", str(table["workspace"]).strip()
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        if not clean_args:
            raise ValueError(f"Dispatcher '{clean}' requires non-empty arguments")
        return "workspace", clean_args

    if key in ("movetoworkspace", "movetoworkspacesilent"):
        if table is not None:
            if set(table.keys()) <= {"workspace", "silent"} and "workspace" in table:
                ws = str(table["workspace"]).strip()
                if ws:
                    silent = bool(table.get("silent", key == "movetoworkspacesilent"))
                    return ("movetoworkspacesilent" if silent else "movetoworkspace"), ws
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        if not clean_args:
            raise ValueError(f"Dispatcher '{clean}' requires non-empty arguments")
        return key, clean_args

    if key in ("window.resize", "resizeactive"):
        if table is not None:
            if set(table.keys()) <= {"dx", "dy"} and table:
                dx = table.get("dx", 0)
                dy = table.get("dy", 0)
                if isinstance(dx, int) and not isinstance(dx, bool) and isinstance(dy, int) and not isinstance(dy, bool):
                    return "resizeactive", f"{dx} {dy}"
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        parts = clean_args.split()
        if len(parts) == 2 and all(p.lstrip("+-").isdigit() for p in parts):
            return "resizeactive", f"{parts[0]} {parts[1]}"
        raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")

    if key in ("layout", "togglesplit"):
        if key == "togglesplit" and (not clean_args or table == {}):
            return "togglesplit", None
        if table is not None:
            if set(table.keys()) == {"action"} and str(table["action"]).lower() == "togglesplit":
                return "togglesplit", None
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        if clean_args.strip("\"'").lower() == "togglesplit":
            return "togglesplit", None
        raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")

    if key == "submap":
        if table is not None:
            if set(table.keys()) == {"submap"} and str(table["submap"]).strip():
                return "submap", str(table["submap"]).strip()
            raise ValueError(f"Dispatcher '{clean}' with args {clean_args!r} is not supported for Hyprlang")
        if not clean_args:
            raise ValueError(f"Dispatcher '{clean}' requires non-empty arguments")
        return "submap", clean_args

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
            cmd = str(parsed_args.get("cmd", "")).strip()
            # If bare variable or expression
            if cmd.startswith('"') or cmd.startswith("'"):
                return "exec_cmd", cmd
            return "exec_cmd", f'"{cmd}"'

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
            return f"window.resize({{ dx = {dx}, dy = {dy} }})", None

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
        return hl_name, str(parsed_args.get("cmd", ""))
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
