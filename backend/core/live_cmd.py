"""Shared live-command runner for external system tools (pactl, wpctl, etc.).

Enforces argument-list invocation (never shell=True), per-call timeouts,
structured results, and clean runner injection for unit tests.
"""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

DEFAULT_LIVE_CMD_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class LiveCmdResult:
    """Structured result from executing a live system command."""

    ok: bool
    rc: int
    out: str
    err: str
    timed_out: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "rc": self.rc,
            "out": self.out,
            "err": self.err,
            "timed_out": self.timed_out,
        }


LiveRunner = Callable[..., LiveCmdResult]


def _decode_stream(data: str | bytes | None) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


def _validate_argv(argv: Sequence[str]) -> list[str]:
    if isinstance(argv, (str, bytes)):
        raise ValueError("argv must be a sequence of strings, not a single string/bytes (shell=True is forbidden).")
    items = list(argv)
    if not items:
        raise ValueError("argv must be non-empty.")
    for i, item in enumerate(items):
        if not isinstance(item, str):
            raise ValueError(f"argv[{i}] must be str, got {type(item).__name__}.")
    if items[0] == "":
        raise ValueError("argv[0] (executable) must be non-empty.")
    return items


def _validate_timeout(timeout: float) -> float:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ValueError(f"timeout must be a positive number, got {timeout!r}.")
    t = float(timeout)
    if math.isnan(t) or math.isinf(t) or t <= 0.0:
        raise ValueError(f"timeout must be finite and > 0, got {timeout!r}.")
    return t


def run_live_cmd(
    argv: Sequence[str],
    *,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
    runner: LiveRunner | None = None,
    env: Mapping[str, str] | None = None,
) -> LiveCmdResult:
    """Execute an external command using an argument list (never shell=True).

    Args:
        argv: Non-empty sequence of string arguments.
        timeout: Per-call timeout in seconds (must be > 0).
        runner: Optional injectable callable `(argv_list, timeout=timeout) -> LiveCmdResult`.
        env: Optional environment mapping passed to `subprocess.run`.

    Returns:
        LiveCmdResult with `ok`, `rc`, `out`, `err`, `timed_out`.
    """
    cmd = _validate_argv(argv)
    t = _validate_timeout(timeout)

    if runner is not None:
        return runner(cmd, timeout=t)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=t,
            shell=False,
            check=False,
            env=dict(env) if env is not None else None,
        )
        return LiveCmdResult(
            ok=(proc.returncode == 0),
            rc=proc.returncode,
            out=proc.stdout or "",
            err=proc.stderr or "",
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        out = _decode_stream(exc.stdout)
        err = _decode_stream(exc.stderr) or f"Command {cmd[0]!r} timed out after {t}s."
        return LiveCmdResult(ok=False, rc=-1, out=out, err=err, timed_out=True)
    except FileNotFoundError as exc:
        return LiveCmdResult(ok=False, rc=127, out="", err=str(exc), timed_out=False)
    except OSError as exc:
        return LiveCmdResult(ok=False, rc=-1, out="", err=str(exc), timed_out=False)
