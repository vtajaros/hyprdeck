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
