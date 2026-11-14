"""Backlight (`brightnessctl`) and optional DDC/CI (`ddcutil`) brightness helpers."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

MIN_BRIGHTNESS_PERCENT = 5
MAX_BRIGHTNESS_PERCENT = 100

_DDC_BRI_RE = re.compile(r"VCP\s+10\s+C\s+(\d+)\s+(\d+)")


def clamp_brightness_percent(percent: int | float) -> int:
    """Clamp requested brightness percentage to [5, 100] to prevent black-screen traps."""
    rounded = int(round(float(percent)))
    return max(MIN_BRIGHTNESS_PERCENT, min(MAX_BRIGHTNESS_PERCENT, rounded))


@dataclass(slots=True)
class BrightnessInfo:
    available: bool
    device: str = ""
    current: int = 0
    max_value: int = 0
    percent: int = 0
    min_percent: int = MIN_BRIGHTNESS_PERCENT
    ddc_available: bool = False
    ddc_percent: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "device": self.device,
            "current": self.current,
            "max_value": self.max_value,
            "percent": self.percent,
            "min_percent": self.min_percent,
            "ddc_available": self.ddc_available,
            "ddc_percent": self.ddc_percent,
            "error": self.error,
        }


def parse_brightnessctl_machine_output(stdout: str) -> BrightnessInfo:
    """Parse `brightnessctl -m` CSV output, preferring class 'backlight'."""
    lines = [ln.strip() for ln in (stdout or "").splitlines() if ln.strip()]
    if not lines:
        return BrightnessInfo(available=False, error="No brightnessctl devices reported.")

    chosen: list[str] | None = None
    fallback: list[str] | None = None
    for line in lines:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        if fallback is None:
            fallback = parts
        if parts[1] == "backlight":
            chosen = parts
            break

    parts = chosen or fallback
    if parts is None:
        return BrightnessInfo(available=False, error="Unrecognized brightnessctl -m output.")

    try:
        device = parts[0]
        current = int(parts[2])
        pct_str = parts[3].rstrip("%")
        pct = int(round(float(pct_str)))
        max_val = int(parts[4])
    except (ValueError, IndexError) as exc:
        return BrightnessInfo(available=False, error=f"Failed to parse brightnessctl output: {exc}")

    return BrightnessInfo(
        available=True,
        device=device,
        current=current,
        max_value=max_val,
        percent=max(0, min(100, pct)),
        min_percent=MIN_BRIGHTNESS_PERCENT,
    )


def read_brightness(
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    enable_ddc: bool = False,
    timeout: float = 3.0,
) -> BrightnessInfo:
    """Read current panel backlight brightness via `brightnessctl -m` (and optionally `ddcutil`)."""
    run_fn = runner if runner is not None else subprocess.run
    try:
        proc = run_fn(
            ["brightnessctl", "-m"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            info = BrightnessInfo(available=False, error=f"brightnessctl exited {proc.returncode}: {detail}")
        else:
            info = parse_brightnessctl_machine_output(proc.stdout)
    except (OSError, subprocess.SubprocessError) as exc:
        info = BrightnessInfo(available=False, error=f"brightnessctl unavailable: {exc}")

    if enable_ddc:
        try:
            ddc_proc = run_fn(
                ["ddcutil", "getvcp", "10", "--brief"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if ddc_proc.returncode == 0:
                m = _DDC_BRI_RE.search(ddc_proc.stdout or "")
                if m:
                    cur = int(m.group(1))
                    mx = max(1, int(m.group(2)))
                    info.ddc_available = True
                    info.ddc_percent = max(0, min(100, int(round((cur * 100.0) / mx))))
        except (OSError, subprocess.SubprocessError, ValueError):
            info.ddc_available = False

    return info


def set_brightness(
    percent: int | float,
    *,
    device: str | None = None,
    use_ddc: bool = False,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    timeout: float = 3.0,
) -> dict[str, Any]:
    """Set backlight or DDC brightness, enforcing the 5% minimum floor."""
    requested = int(round(float(percent)))
    clamped = clamp_brightness_percent(percent)
    was_clamped = clamped != requested
    run_fn = runner if runner is not None else subprocess.run

    if use_ddc:
        argv = ["ddcutil", "setvcp", "10", str(clamped)]
    else:
        argv = ["brightnessctl"]
        if device:
            argv.extend(["-d", str(device)])
        argv.extend(["set", f"{clamped}%"])

    try:
        proc = run_fn(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "ok": False,
            "percent": clamped,
            "requested_percent": requested,
            "clamped": was_clamped,
            "error": f"Failed to set brightness: {exc}",
        }

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return {
            "ok": False,
            "percent": clamped,
            "requested_percent": requested,
            "clamped": was_clamped,
            "error": f"{argv[0]} exited with {proc.returncode}: {detail}",
        }

    return {
        "ok": True,
        "percent": clamped,
        "requested_percent": requested,
        "clamped": was_clamped,
        "device": device or "",
        "error": None,
    }
