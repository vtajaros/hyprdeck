"""XKB evdev.lst parser and keyboard layout/variant/options validation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping

from backend.core.constants import ENV_SETTINGS_XKB_PATH

DEFAULT_EVDEV_LST_PATH = "/usr/share/X11/xkb/rules/evdev.lst"

NON_LATIN_LAYOUTS: frozenset[str] = frozenset(
    {
        "af",
        "am",
        "ara",
        "bd",
        "bg",
        "bt",
        "by",
        "cn",
        "eg",
        "et",
        "ge",
        "gr",
        "il",
        "iq",
        "ir",
        "jp",
        "kg",
        "kh",
        "kr",
        "kz",
        "la",
        "lk",
        "mk",
        "mm",
        "mn",
        "np",
        "pk",
        "rs",
        "ru",
        "sy",
        "th",
        "ti",
        "tj",
        "tw",
        "ua",
    }
)


@dataclass(slots=True)
class XkbRules:
    """Parsed XKB layouts, per-layout variants, and option groups."""

    layouts: list[dict[str, str]] = field(default_factory=list)
    variants: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    option_groups: list[dict[str, Any]] = field(default_factory=list)
    layout_codes: set[str] = field(default_factory=set)
    option_codes: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "layouts": list(self.layouts),
            "variants": {k: list(v) for k, v in self.variants.items()},
            "option_groups": list(self.option_groups),
        }


def parse_evdev_lst(text: str) -> XkbRules:
    """Parse XKB rules text in `evdev.lst` format."""
    rules = XkbRules()
    section = ""
    groups_by_name: dict[str, dict[str, Any]] = {}

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("!"):
            section = stripped[1:].strip().lower()
            continue

        if section == "layout":
            parts = stripped.split(None, 1)
            if len(parts) == 2:
                code, desc = parts[0].strip(), parts[1].strip()
                if code and code not in rules.layout_codes:
                    rules.layout_codes.add(code)
                    rules.layouts.append({"code": code, "description": desc})
        elif section == "variant":
            parts = stripped.split(None, 1)
            if len(parts) == 2 and ":" in parts[1]:
                var_code = parts[0].strip()
                lay_part, desc_part = parts[1].split(":", 1)
                lay_code = lay_part.strip()
                desc = desc_part.strip()
                if var_code and lay_code:
                    rules.variants.setdefault(lay_code, []).append(
                        {"code": var_code, "description": desc}
                    )
        elif section == "option":
            parts = stripped.split(None, 1)
            if len(parts) == 2:
                code, desc = parts[0].strip(), parts[1].strip()
                if ":" in code:
                    grp = code.split(":", 1)[0]
                    rules.option_codes.add(code)
                    if grp not in groups_by_name:
                        groups_by_name[grp] = {
                            "group": grp,
                            "description": grp,
                            "options": [],
                        }
                        rules.option_groups.append(groups_by_name[grp])
                    groups_by_name[grp]["options"].append(
                        {"code": code, "description": desc}
                    )
                else:
                    if code not in groups_by_name:
                        groups_by_name[code] = {
                            "group": code,
                            "description": desc,
                            "options": [],
                        }
                        rules.option_groups.append(groups_by_name[code])
                    else:
                        groups_by_name[code]["description"] = desc

    return rules


def load_xkb_rules(
    *,
    path: str | None = None,
    env: Mapping[str, str] | None = None,
) -> XkbRules:
    """Load and parse system `evdev.lst` (or `HKS_SETTINGS_XKB_PATH` override)."""
    environ = env if env is not None else os.environ
    eff_path = (
        path
        or environ.get(ENV_SETTINGS_XKB_PATH, "").strip()
        or DEFAULT_EVDEV_LST_PATH
    )
    with open(os.path.expanduser(eff_path), "r", encoding="utf-8", errors="replace") as f:
        return parse_evdev_lst(f.read())


def validate_keyboard_layout(
    kb_layout: str,
    kb_variant: str = "",
    kb_options: str = "",
    *,
    xkb_rules: XkbRules | None = None,
) -> tuple[list[str], list[str]]:
    """Validate comma-separated kb_layout/kb_variant/kb_options against XKB rules.

    Returns `(errors, warnings)`. Non-Latin first layout produces a non-blocking warning.
    """
    rules = xkb_rules if xkb_rules is not None else load_xkb_rules()
    errors: list[str] = []
    warnings: list[str] = []

    raw_layout = str(kb_layout or "").strip()
    if not raw_layout:
        return ["Keyboard layout ('kb_layout') cannot be empty."], []

    layouts = [part.strip() for part in raw_layout.split(",")]
    if any(not code for code in layouts):
        return ["Keyboard layout list contains an empty entry."], []

    for code in layouts:
        if rules.layout_codes and code not in rules.layout_codes:
            errors.append(f"Unknown XKB keyboard layout: {code!r}.")

    raw_variant = str(kb_variant or "").strip()
    if raw_variant:
        variants = [part.strip() for part in raw_variant.split(",")]
        if len(variants) != len(layouts):
            errors.append(
                f"Variant count ({len(variants)}) must match layout count ({len(layouts)}) or be empty."
            )
        else:
            for idx, var_code in enumerate(variants):
                if not var_code:
                    continue
                lay_code = layouts[idx]
                valid_for_lay = {v["code"] for v in rules.variants.get(lay_code, ())}
                if var_code not in valid_for_lay:
                    errors.append(
                        f"Unknown variant {var_code!r} for layout {lay_code!r}."
                    )

    raw_options = str(kb_options or "").strip()
    if raw_options:
        opts = [part.strip() for part in raw_options.split(",") if part.strip()]
        for opt_code in opts:
            if rules.option_codes and opt_code not in rules.option_codes:
                errors.append(f"Unknown XKB keyboard option: {opt_code!r}.")

    if not errors and layouts and layouts[0] in NON_LATIN_LAYOUTS:
        warnings.append(
            f"First layout {layouts[0]!r} is non-Latin; keysym-based keybinds may stop matching when active."
        )

    return errors, warnings
