"""Modifier bitmask table and key classification for Hyprland Keybind Studio."""

from __future__ import annotations

from dataclasses import dataclass, field

# Canonical modifier bits (verified against live `hyprctl binds -j` data)
MODIFIER_BITS: dict[str, int] = {
    "SHIFT": 1,
    "CAPS": 2,
    "CTRL": 4,
    "ALT": 8,
    "MOD2": 16,
    "MOD3": 32,
    "SUPER": 64,
    "MOD5": 128,
}

MODIFIER_ALIASES: dict[str, str] = {
    "SHIFT": "SHIFT",
    "CAPS": "CAPS",
    "CAPSLOCK": "CAPS",
    "LOCK": "CAPS",
    "CTRL": "CTRL",
    "CONTROL": "CTRL",
    "ALT": "ALT",
    "MOD1": "ALT",
    "MOD2": "MOD2",
    "MOD3": "MOD3",
    "SUPER": "SUPER",
    "META": "SUPER",
    "WIN": "SUPER",
    "LOGO": "SUPER",
    "MOD4": "SUPER",
    "MOD5": "MOD5",
}

MOUSE_WHEEL_KEYS = frozenset(
    {
        "mouse_up",
        "mouse_down",
        "mouse_left",
        "mouse_right",
    }
)

# Hyprlang flag letters corresponding to normalized boolean flag names
FLAG_TO_LETTER: dict[str, str] = {
    "repeating": "e",
    "ignore_mods": "i",
    "locked": "l",
    "mouse": "m",
    "non_consuming": "n",
    "long_press": "o",
    "release": "r",
    "transparent": "t",
}

LETTER_TO_FLAG: dict[str, str] = {
    "l": "locked",
    "r": "release",
    "e": "repeating",
    "n": "non_consuming",
    "m": "mouse",
    "t": "transparent",
    "i": "ignore_mods",
    "o": "long_press",
    "s": "separate",
    "d": "has_description",
    "g": "group",
    "p": "bypass",
}


@dataclass(slots=True)
class ParsedModifiers:
    modifiers: list[str] = field(default_factory=list)
    modmask: int = 0
    unknown_tokens: list[str] = field(default_factory=list)
    has_empty_token: bool = False


def resolve_modifier_tokens(tokens: list[str]) -> ParsedModifiers:
    """Resolve a list of raw modifier tokens into canonical names and bitmask."""
    res = ParsedModifiers()
    seen: set[str] = set()
    for raw_tok in tokens:
        tok = raw_tok.strip()
        if not tok:
            res.has_empty_token = True
            continue
        upper = tok.upper()
        canonical = MODIFIER_ALIASES.get(upper)
        if canonical is None:
            res.unknown_tokens.append(tok)
            continue
        bit = MODIFIER_BITS[canonical]
        res.modmask |= bit
        if canonical not in seen:
            seen.add(canonical)
            res.modifiers.append(canonical)
    return res


def classify_key_kind(key: str) -> str:
    """Classify a Hyprland key string into keysym | mouse_button | keycode | mouse_wheel."""
    lower = key.lower()
    if lower.startswith("mouse:"):
        return "mouse_button"
    if lower in MOUSE_WHEEL_KEYS:
        return "mouse_wheel"
    if lower.startswith("code:"):
        return "keycode"
    return "keysym"


def derive_bind_type_from_flags(
    flags: dict[str, bool], has_description: bool = False
) -> str:
    """Derive canonical bind_type ('bind' + sorted flag letters) from boolean flags."""
    letters: list[str] = []
    for flag_name, letter in FLAG_TO_LETTER.items():
        if flags.get(flag_name, False):
            letters.append(letter)
    if has_description:
        letters.append("d")
    letters.sort()
    return "bind" + "".join(letters)
