"""Table-driven human description and category derivation for Hyprland keybindings."""

from __future__ import annotations

import os
import re
from typing import Any

from backend.models.types import BindRecord, DescriptionEffective

DIRECTION_MAP: dict[str, str] = {
    "l": "left",
    "left": "left",
    "r": "right",
    "right": "right",
    "u": "up",
    "up": "up",
    "d": "down",
    "down": "down",
}

SHELL_METACHARS = frozenset("|&;$()<>`\"'")

SYSTEM_EXEC_RE = re.compile(
    r"(?:^|[\s/;|&])(?:hyprlock|wlogout|loginctl|poweroff|reboot)(?:$|[\s;|&])"
    r"|(?:^|[\s/;|&])systemctl\s+(?:--\S+\s+)*(?:suspend|poweroff|reboot|hibernate)(?:$|[\s;|&])"
)

HYPRLANG_WINDOW_DISPATCHERS = frozenset(
    {
        "killactive",
        "closewindow",
        "fullscreen",
        "fakefullscreen",
        "togglefloating",
        "float",
        "pseudo",
        "togglesplit",
        "layoutmsg",
        "movewindow",
        "resizewindow",
        "movefocus",
        "cyclenext",
        "bringactivetotop",
        "swapwindow",
        "swapnext",
        "centerwindow",
        "pin",
        "splitratio",
        "alterzorder",
        "tagwindow",
        "lockactivegroup",
        "togglegroup",
        "changegroupactive",
        "moveoutofgroup",
        "moveintogroup",
        "movegroupwindow",
    }
)

HYPRLANG_WORKSPACE_DISPATCHERS = frozenset(
    {
        "workspace",
        "movetoworkspace",
        "movetoworkspacesilent",
        "togglespecialworkspace",
        "focusworkspaceoncurrentmonitor",
        "movecurrentworkspacetomonitor",
        "moveworkspacetomonitor",
        "swapactiveworkspaces",
    }
)


def _first_dict_arg(args: list[Any]) -> dict[str, Any] | None:
    if args and isinstance(args[0], dict):
        return args[0]
    return None


def _first_scalar_arg(args: list[Any], arg_summary: str) -> str:
    if args:
        first = args[0]
        if isinstance(first, bool):
            return "true" if first else "false"
        if isinstance(first, (int, float)):
            return str(int(first)) if float(first).is_integer() else str(first)
        if isinstance(first, str):
            return first.strip()
    return arg_summary.strip()


def _format_workspace_val(val: Any) -> str:
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, (int, float)):
        return str(int(val)) if float(val).is_integer() else str(val)
    return str(val).strip()


def _extract_direction(args: list[Any], arg_summary: str) -> str | None:
    d_arg = _first_dict_arg(args)
    if d_arg is not None:
        raw_dir = d_arg.get("direction") or d_arg.get("dir")
        if isinstance(raw_dir, str):
            return DIRECTION_MAP.get(raw_dir.strip().lower())
        return None
    scalar = _first_scalar_arg(args, arg_summary).lower()
    return DIRECTION_MAP.get(scalar)


def _extract_workspace_target(args: list[Any], arg_summary: str) -> str | None:
    d_arg = _first_dict_arg(args)
    if d_arg is not None:
        if "workspace" in d_arg and d_arg["workspace"] is not None:
            return _format_workspace_val(d_arg["workspace"])
        if "special" in d_arg and d_arg["special"] is not None:
            sp = _format_workspace_val(d_arg["special"])
            return sp if sp.startswith("special:") else f"special:{sp}"
        return None
    scalar = _first_scalar_arg(args, arg_summary)
    if not scalar or scalar.lower() in DIRECTION_MAP:
        return None
    return scalar


def _format_move_to_workspace(ws_str: str) -> str:
    if ws_str in ("e+1", "+1"):
        return "Move window to next workspace"
    if ws_str in ("e-1", "-1"):
        return "Move window to previous workspace"
    if ws_str.startswith("special:"):
        sp_name = ws_str[len("special:") :].strip()
        if sp_name == "minimized":
            return "Minimize window"
        return f"Send window to special workspace {sp_name}"
    return f"Move window to workspace {ws_str}"


def _format_switch_workspace(ws_str: str) -> str:
    if ws_str in ("e+1", "+1"):
        return "Switch to next workspace"
    if ws_str in ("e-1", "-1"):
        return "Switch to previous workspace"
    return f"Switch to workspace {ws_str}"


def _format_exec_description(cmd: str) -> str:
    clean = cmd.strip()
    if (
        clean
        and not any(ch.isspace() for ch in clean)
        and not any(ch in SHELL_METACHARS for ch in clean)
    ):
        base = os.path.basename(clean) or clean
        return f"Launch {base}"
    full = f"Run: {clean}"
    if len(full) > 60:
        return full[:57] + "..."
    return full


def derive_description(bind: BindRecord) -> tuple[str, bool]:
    """Derive a deterministic human-readable description and generic flag for a bind."""
    dsp_path = bind.dispatcher.path.strip()
    dsp_lower = dsp_path.lower()
    dsp_leaf = dsp_lower.rsplit(".", 1)[-1]
    args = bind.dispatcher.args
    arg_summary = bind.dispatcher.arg_summary.strip()
    is_mouse_bind = bool(bind.flags.get("mouse")) or bind.bind_type.startswith("bindm")

    # 1. Mouse drag / resize binds
    if dsp_leaf == "drag" or (dsp_lower == "movewindow" and is_mouse_bind):
        return "Drag window with mouse", False
    if dsp_leaf == "resizewindow" or (dsp_leaf == "resize" and (is_mouse_bind or dsp_lower == "window.resize")):
        return "Resize window with mouse", False

    # 2. Close window
    if dsp_leaf in ("close", "killactive", "closewindow"):
        return "Close window", False

    # 3. Fullscreen / maximize
    if dsp_leaf == "fullscreen":
        d_arg = _first_dict_arg(args)
        if d_arg is not None:
            mode = str(d_arg.get("mode", "fullscreen")).strip().lower()
            if mode in ("maximized", "1"):
                return "Maximize window", False
            return "Toggle fullscreen", False
        scalar = _first_scalar_arg(args, arg_summary).lower()
        if scalar in ("1", "maximized", "mode=maximized"):
            return "Maximize window", False
        return "Toggle fullscreen", False

    # 4. Float & pseudo-tiling
    if dsp_leaf in ("float", "togglefloating"):
        return "Toggle floating", False
    if dsp_leaf == "pseudo":
        return "Toggle pseudo-tiling", False

    # 5. Layout & togglesplit
    if dsp_leaf == "togglesplit":
        return "Toggle split direction", False
    if dsp_leaf in ("layout", "layoutmsg"):
        scalar = _first_scalar_arg(args, arg_summary)
        if scalar == "togglesplit":
            return "Toggle split direction", False
        if scalar:
            return f"Layout: {scalar}", False

    # 6. Window move (direction or workspace) & movetoworkspace(silent)
    if dsp_lower in ("window.move", "move", "movewindow"):
        direction = _extract_direction(args, arg_summary)
        if direction is not None:
            return f"Move window {direction}", False
        ws_target = _extract_workspace_target(args, arg_summary)
        if ws_target is not None:
            return _format_move_to_workspace(ws_target), False
        if dsp_lower == "movewindow":
            return "Drag window with mouse", False

    if dsp_leaf in ("movetoworkspace", "movetoworkspacesilent"):
        ws_target = _extract_workspace_target(args, arg_summary)
        if ws_target is not None:
            return _format_move_to_workspace(ws_target), False

    # 7. Focus (window direction vs workspace target) & movefocus / workspace
    if dsp_leaf == "movefocus":
        direction = _extract_direction(args, arg_summary)
        if direction is not None:
            return f"Focus window {direction}", False

    if dsp_leaf == "workspace" or dsp_lower == "workspace.focus":
        ws_target = _extract_workspace_target(args, arg_summary)
        if ws_target is not None:
            return _format_switch_workspace(ws_target), False

    if dsp_leaf == "focus":
        direction = _extract_direction(args, arg_summary)
        if direction is not None:
            return f"Focus window {direction}", False
        ws_target = _extract_workspace_target(args, arg_summary)
        if ws_target is not None:
            return _format_switch_workspace(ws_target), False

    # 8. Cycle next / previous
    if dsp_leaf in ("cycle_next", "cyclenext"):
        d_arg = _first_dict_arg(args)
        if d_arg is not None and bool(d_arg.get("prev")):
            return "Cycle to previous window", False
        scalar = _first_scalar_arg(args, arg_summary).lower()
        if scalar in ("prev", "previous", "prev=true", "true", "1"):
            return "Cycle to previous window", False
        return "Cycle to next window", False

    # 9. Bring to top
    if dsp_leaf in ("bring_to_top", "bringactivetotop"):
        return "Bring window to top", False

    # 10. Toggle special workspace
    if dsp_leaf in ("toggle_special", "togglespecialworkspace") or dsp_lower == "workspace.toggle_special":
        d_arg = _first_dict_arg(args)
        sp_name = ""
        if d_arg is not None:
            raw_sp = d_arg.get("name") or d_arg.get("workspace") or d_arg.get("special") or ""
            sp_name = _format_workspace_val(raw_sp)
        else:
            sp_name = _first_scalar_arg(args, arg_summary)
        if sp_name.startswith("special:"):
            sp_name = sp_name[len("special:") :].strip()
        if sp_name:
            return f"Toggle special workspace {sp_name}", False
        return "Toggle special workspace", False

    # 11. Exec commands
    if dsp_leaf in ("exec_cmd", "exec", "execr"):
        cmd = _first_scalar_arg(args, arg_summary)
        return _format_exec_description(cmd), False

    # 12. Generic fallback
    return f"{dsp_path}: {arg_summary}", True


def _is_special_window_move(dsp_lower: str, dsp_leaf: str, args: list[Any], arg_summary: str) -> bool:
    if dsp_lower in ("window.move", "move", "movewindow") or dsp_leaf in (
        "movetoworkspace",
        "movetoworkspacesilent",
    ):
        ws_target = _extract_workspace_target(args, arg_summary)
        if ws_target is not None and ws_target.startswith("special:"):
            return True
    return False


def _is_workspace_dispatcher(dsp_lower: str, dsp_leaf: str, args: list[Any], arg_summary: str) -> bool:
    if _is_special_window_move(dsp_lower, dsp_leaf, args, arg_summary):
        return False
    if dsp_lower.startswith("workspace.") or dsp_leaf in HYPRLANG_WORKSPACE_DISPATCHERS:
        return True
    if dsp_leaf == "focus" and _extract_workspace_target(args, arg_summary) is not None:
        return True
    if dsp_lower in ("window.move", "move") and _extract_workspace_target(args, arg_summary) is not None:
        return True
    return False


def _is_window_dispatcher(dsp_lower: str, dsp_leaf: str, args: list[Any], arg_summary: str) -> bool:
    if _is_special_window_move(dsp_lower, dsp_leaf, args, arg_summary):
        return True
    if dsp_lower.startswith("window.") or dsp_leaf in HYPRLANG_WINDOW_DISPATCHERS:
        return True
    if dsp_leaf in (
        "close",
        "fullscreen",
        "float",
        "pseudo",
        "layout",
        "cycle_next",
        "bring_to_top",
        "drag",
        "resize",
    ):
        return True
    if dsp_leaf == "focus" and _extract_direction(args, arg_summary) is not None:
        return True
    if dsp_lower == "move" and _extract_direction(args, arg_summary) is not None:
        return True
    return False


def derive_category(bind: BindRecord) -> str:
    """Evaluate category rules in strict precedence order (first match wins)."""
    # 2) bind has the mouse flag => "Mouse"
    if bool(bind.flags.get("mouse")) or bind.bind_type.startswith("bindm"):
        return "Mouse"

    dsp_path = bind.dispatcher.path.strip()
    dsp_lower = dsp_path.lower()
    dsp_leaf = dsp_lower.rsplit(".", 1)[-1]
    args = bind.dispatcher.args
    arg_summary = bind.dispatcher.arg_summary.strip()
    is_exec = dsp_leaf in ("exec_cmd", "exec", "execr")

    # 3) exec matching system lock/power commands => "System"
    if is_exec:
        cmd = _first_scalar_arg(args, arg_summary)
        if SYSTEM_EXEC_RE.search(cmd):
            return "System"

    # 4) key starts with "XF86" => "Media & Hardware"
    if bind.key.startswith("XF86"):
        return "Media & Hardware"

    # 5) workspace-related dispatcher (except move to special: workspace) => "Workspaces"
    if _is_workspace_dispatcher(dsp_lower, dsp_leaf, args, arg_summary):
        return "Workspaces"

    # 6) window-related dispatcher => "Windows"
    if _is_window_dispatcher(dsp_lower, dsp_leaf, args, arg_summary):
        return "Windows"

    # 7) exec => "Apps"
    if is_exec:
        return "Apps"

    # 8) else "Other"
    return "Other"


def populate_bind_description(bind: BindRecord) -> None:
    """Populate description_effective, category, and category_source on a single BindRecord."""
    derived_text, is_generic = derive_description(bind)
    if bind.description is not None and bind.description.strip() != "":
        bind.description_effective = DescriptionEffective(
            text=bind.description,
            source="config",
            generic=False,
        )
    else:
        bind.description_effective = DescriptionEffective(
            text=derived_text,
            source="derived",
            generic=is_generic,
        )
    bind.category = derive_category(bind)
    bind.category_source = "derived"


def populate_bind_descriptions(binds: list[BindRecord]) -> None:
    """Populate derived descriptions and categories for a list of BindRecords in-place."""
    for bind in binds:
        populate_bind_description(bind)
