"""Live-verified declarative catalog of Hyprland appearance and desktop-behavior options."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class OptionSpec:
    id: str
    section: str  # "appearance" | "desktop"
    group: str
    label: str
    description: str
    type: str  # "bool" | "int" | "float" | "color" | "enum" | "string"
    hyprland_path: str
    getoption_name: str
    min: float | None = None
    max: float | None = None
    step: float | None = None
    enum_values: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "section": self.section,
            "group": self.group,
            "label": self.label,
            "description": self.description,
            "type": self.type,
            "hyprland_path": self.hyprland_path,
            "getoption_name": self.getoption_name,
        }
        if self.min is not None:
            d["min"] = self.min
        if self.max is not None:
            d["max"] = self.max
        if self.step is not None:
            d["step"] = self.step
        if self.enum_values:
            d["enum_values"] = list(self.enum_values)
        return d


# Dropped from candidate probing against Hyprland 0.57.1:
# - dwindle.pseudotile (dwindle:pseudotile -> "no such option")
# - misc.vfr (misc:vfr -> "no such option")
# - general.col.active_border ("col.active_border" has '.' which is not a Lua identifier)
CATALOG: tuple[OptionSpec, ...] = (
    # --- Appearance ---
    OptionSpec(
        id="general.gaps_in",
        section="appearance",
        group="Gaps & Borders",
        label="Inner Gaps",
        description="Gaps between windows in pixels.",
        type="int",
        hyprland_path="general.gaps_in",
        getoption_name="general:gaps_in",
        min=0,
        max=64,
        step=1,
    ),
    OptionSpec(
        id="general.gaps_out",
        section="appearance",
        group="Gaps & Borders",
        label="Outer Gaps",
        description="Gaps between windows and monitor edges in pixels.",
        type="int",
        hyprland_path="general.gaps_out",
        getoption_name="general:gaps_out",
        min=0,
        max=96,
        step=1,
    ),
    OptionSpec(
        id="general.border_size",
        section="appearance",
        group="Gaps & Borders",
        label="Border Size",
        description="Thickness of window borders in pixels.",
        type="int",
        hyprland_path="general.border_size",
        getoption_name="general:border_size",
        min=0,
        max=12,
        step=1,
    ),
    OptionSpec(
        id="decoration.rounding",
        section="appearance",
        group="Decoration",
        label="Corner Rounding",
        description="Rounded corner radius in pixels.",
        type="int",
        hyprland_path="decoration.rounding",
        getoption_name="decoration:rounding",
        min=0,
        max=32,
        step=1,
    ),
    OptionSpec(
        id="decoration.active_opacity",
        section="appearance",
        group="Decoration",
        label="Active Opacity",
        description="Opacity of the focused window (0.1 to 1.0).",
        type="float",
        hyprland_path="decoration.active_opacity",
        getoption_name="decoration:active_opacity",
        min=0.1,
        max=1.0,
        step=0.02,
    ),
    OptionSpec(
        id="decoration.inactive_opacity",
        section="appearance",
        group="Decoration",
        label="Inactive Opacity",
        description="Opacity of unfocused windows (0.1 to 1.0).",
        type="float",
        hyprland_path="decoration.inactive_opacity",
        getoption_name="decoration:inactive_opacity",
        min=0.1,
        max=1.0,
        step=0.02,
    ),
    OptionSpec(
        id="decoration.blur.enabled",
        section="appearance",
        group="Blur",
        label="Enable Blur",
        description="Enable background blur behind transparent windows.",
        type="bool",
        hyprland_path="decoration.blur.enabled",
        getoption_name="decoration:blur:enabled",
    ),
    OptionSpec(
        id="decoration.blur.size",
        section="appearance",
        group="Blur",
        label="Blur Size",
        description="Blur kernel radius in pixels.",
        type="int",
        hyprland_path="decoration.blur.size",
        getoption_name="decoration:blur:size",
        min=1,
        max=24,
        step=1,
    ),
    OptionSpec(
        id="decoration.blur.passes",
        section="appearance",
        group="Blur",
        label="Blur Passes",
        description="Number of blur passes (higher is smoother, costs GPU).",
        type="int",
        hyprland_path="decoration.blur.passes",
        getoption_name="decoration:blur:passes",
        min=1,
        max=6,
        step=1,
    ),
    OptionSpec(
        id="decoration.shadow.enabled",
        section="appearance",
        group="Shadows",
        label="Enable Shadows",
        description="Draw drop shadows behind windows.",
        type="bool",
        hyprland_path="decoration.shadow.enabled",
        getoption_name="decoration:shadow:enabled",
    ),
    OptionSpec(
        id="decoration.shadow.range",
        section="appearance",
        group="Shadows",
        label="Shadow Range",
        description="Shadow spread size in pixels.",
        type="int",
        hyprland_path="decoration.shadow.range",
        getoption_name="decoration:shadow:range",
        min=0,
        max=64,
        step=1,
    ),
    OptionSpec(
        id="decoration.shadow.color",
        section="appearance",
        group="Shadows",
        label="Shadow Color",
        description="Shadow color in 0xAARRGGBB or #RRGGBB format.",
        type="color",
        hyprland_path="decoration.shadow.color",
        getoption_name="decoration:shadow:color",
    ),
    OptionSpec(
        id="animations.enabled",
        section="appearance",
        group="Animations",
        label="Enable Animations",
        description="Enable compositor animations globally.",
        type="bool",
        hyprland_path="animations.enabled",
        getoption_name="animations:enabled",
    ),
    # --- Desktop behavior ---
    OptionSpec(
        id="general.layout",
        section="desktop",
        group="Window Layout",
        label="Active Layout",
        description="Default tiling layout algorithm.",
        type="enum",
        hyprland_path="general.layout",
        getoption_name="general:layout",
        enum_values=("dwindle", "master"),
    ),
    OptionSpec(
        id="general.resize_on_border",
        section="desktop",
        group="Window Layout",
        label="Resize on Border",
        description="Allow resizing windows by dragging their borders.",
        type="bool",
        hyprland_path="general.resize_on_border",
        getoption_name="general:resize_on_border",
    ),
    OptionSpec(
        id="general.allow_tearing",
        section="desktop",
        group="Window Layout",
        label="Allow Tearing",
        description="Permit screen tearing for supported fullscreen apps.",
        type="bool",
        hyprland_path="general.allow_tearing",
        getoption_name="general:allow_tearing",
    ),
    OptionSpec(
        id="dwindle.preserve_split",
        section="desktop",
        group="Dwindle Layout",
        label="Preserve Split",
        description="Keep split direction when windows are closed or moved.",
        type="bool",
        hyprland_path="dwindle.preserve_split",
        getoption_name="dwindle:preserve_split",
    ),
    OptionSpec(
        id="dwindle.force_split",
        section="desktop",
        group="Dwindle Layout",
        label="Force Split Direction",
        description="0 = follow mouse, 1 = always left/top, 2 = always right/bottom.",
        type="int",
        hyprland_path="dwindle.force_split",
        getoption_name="dwindle:force_split",
        min=0,
        max=2,
        step=1,
    ),
    OptionSpec(
        id="master.new_status",
        section="desktop",
        group="Master Layout",
        label="New Window Role",
        description="Where new windows open in master layout.",
        type="enum",
        hyprland_path="master.new_status",
        getoption_name="master:new_status",
        enum_values=("master", "slave", "inherit"),
    ),
    OptionSpec(
        id="master.mfact",
        section="desktop",
        group="Master Layout",
        label="Master Ratio",
        description="Fraction of screen width/height occupied by master window.",
        type="float",
        hyprland_path="master.mfact",
        getoption_name="master:mfact",
        min=0.1,
        max=0.9,
        step=0.05,
    ),
    OptionSpec(
        id="misc.disable_hyprland_logo",
        section="desktop",
        group="Miscellaneous",
        label="Disable Hyprland Logo",
        description="Hide the default Hyprland background logo.",
        type="bool",
        hyprland_path="misc.disable_hyprland_logo",
        getoption_name="misc:disable_hyprland_logo",
    ),
    OptionSpec(
        id="misc.focus_on_activate",
        section="desktop",
        group="Miscellaneous",
        label="Focus on Activate",
        description="Focus windows automatically when they request activation.",
        type="bool",
        hyprland_path="misc.focus_on_activate",
        getoption_name="misc:focus_on_activate",
    ),
    OptionSpec(
        id="misc.animate_manual_resizes",
        section="desktop",
        group="Miscellaneous",
        label="Animate Manual Resizes",
        description="Animate windows while resizing manually.",
        type="bool",
        hyprland_path="misc.animate_manual_resizes",
        getoption_name="misc:animate_manual_resizes",
    ),
    OptionSpec(
        id="misc.enable_swallow",
        section="desktop",
        group="Miscellaneous",
        label="Enable Window Swallowing",
        description="Hide parent terminal when launching GUI applications from it.",
        type="bool",
        hyprland_path="misc.enable_swallow",
        getoption_name="misc:enable_swallow",
    ),
    OptionSpec(
        id="misc.mouse_move_enables_dpms",
        section="desktop",
        group="Miscellaneous",
        label="Mouse Move Wakes Display",
        description="Turn displays back on when the mouse moves.",
        type="bool",
        hyprland_path="misc.mouse_move_enables_dpms",
        getoption_name="misc:mouse_move_enables_dpms",
    ),
    OptionSpec(
        id="misc.key_press_enables_dpms",
        section="desktop",
        group="Miscellaneous",
        label="Key Press Wakes Display",
        description="Turn displays back on when any key is pressed.",
        type="bool",
        hyprland_path="misc.key_press_enables_dpms",
        getoption_name="misc:key_press_enables_dpms",
    ),
    OptionSpec(
        id="cursor.hide_on_key_press",
        section="desktop",
        group="Cursor",
        label="Hide Cursor on Key Press",
        description="Hide the mouse cursor while typing.",
        type="bool",
        hyprland_path="cursor.hide_on_key_press",
        getoption_name="cursor:hide_on_key_press",
    ),
    OptionSpec(
        id="cursor.inactive_timeout",
        section="desktop",
        group="Cursor",
        label="Cursor Inactivity Timeout",
        description="Seconds of inactivity before hiding the cursor (0 = never).",
        type="float",
        hyprland_path="cursor.inactive_timeout",
        getoption_name="cursor:inactive_timeout",
        min=0.0,
        max=60.0,
        step=1.0,
    ),
)

CATALOG_BY_ID: dict[str, OptionSpec] = {opt.id: opt for opt in CATALOG}
