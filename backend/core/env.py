"""Environment variable resolution helpers (HYPRDECK_* > HKS_* > default)."""

from __future__ import annotations

import os
from typing import Mapping


def get_env(
    suffix: str,
    default: str = "",
    environ: Mapping[str, str] | None = None,
    *,
    strip: bool = True,
) -> str:
    """Return HYPRDECK_<suffix> if non-empty, else HKS_<suffix>, else default."""
    env_map = os.environ if environ is None else environ
    for prefix in ("HYPRDECK_", "HKS_"):
        raw = env_map.get(f"{prefix}{suffix}")
        if raw is None:
            continue
        val = str(raw).strip() if strip else str(raw)
        if val:
            return val
    return default


def get_env_flag(
    suffix: str,
    default: bool = False,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Return True if HYPRDECK_<suffix> (or HKS_<suffix>) is '1', False if '0'."""
    val = get_env(suffix, "", environ=environ)
    if val == "1":
        return True
    if val == "0":
        return False
    return default
