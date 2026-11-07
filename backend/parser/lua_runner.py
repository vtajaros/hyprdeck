"""Subprocess runner for the sandboxed Lua 5.4 bind recorder."""

from __future__ import annotations

import json
import os
import resource
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any

from backend.models.types import Diagnostic, SandboxStats

RECORDER_SCRIPT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "lua", "recorder.lua")
)

ALLOWED_ENV_KEYS = ("HOME", "XDG_CONFIG_HOME", "XDG_SESSION_TYPE", "USER", "LANG")
INSTRUCTION_LIMIT_DEFAULT = 50_000_000
CPU_LIMIT_SECONDS = 10
WALL_TIMEOUT_SECONDS = 15.0
AS_LIMIT_BYTES = 512 * 1024 * 1024
FSIZE_LIMIT_BYTES = 0
NOFILE_LIMIT = 64
NPROC_LIMIT = 0
DEFAULT_TIMEOUT_SECONDS = WALL_TIMEOUT_SECONDS


@dataclass(slots=True)
class RawRecorderOutput:
    recorder_version: int = 1
    binds: list[dict[str, Any]] = field(default_factory=list)
    files_loaded: list[str] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    ignored_calls: dict[str, int] = field(default_factory=dict)
    unexecuted_callbacks: list[dict[str, Any]] = field(default_factory=list)
    sandbox: SandboxStats | None = None
    complete: bool = False


def _build_sandbox_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    src = base_env if base_env is not None else os.environ
    clean: dict[str, str] = {}
    for k in ALLOWED_ENV_VARS_FOR_SUBPROCESS:
        val = src.get(k)
        if val is not None:
            clean[k] = val
    return clean


ALLOWED_ENV_VARS_FOR_SUBPROCESS = ALLOWED_ENV_KEYS


def _apply_rlimits() -> None:
    """Apply resource limits in the child process before exec."""
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT_SECONDS, CPU_LIMIT_SECONDS))
    except (ValueError, OSError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_AS, (AS_LIMIT_BYTES, AS_LIMIT_BYTES))
    except (ValueError, OSError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (FSIZE_LIMIT_BYTES, FSIZE_LIMIT_BYTES))
    except (ValueError, OSError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (NOFILE_LIMIT, NOFILE_LIMIT))
    except (ValueError, OSError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (NPROC_LIMIT, NPROC_LIMIT))
    except (ValueError, OSError, AttributeError):
        pass


def run_lua_recorder(
    entrypoint: str,
    config_dir: str,
    instruction_limit: int | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    env: dict[str, str] | None = None,
    lua_binary: str = "lua5.4",
) -> RawRecorderOutput:
    """Execute recorder.lua in a restricted subprocess and parse its JSON output."""
    abs_entry = os.path.abspath(entrypoint)
    abs_config_dir = os.path.abspath(config_dir)
    clean_env = _build_sandbox_env(env)

    limit_env = os.environ.get("HKS_INSTRUCTION_LIMIT")
    effective_instruction_limit = (
        int(instruction_limit)
        if instruction_limit is not None
        else (int(limit_env) if limit_env and limit_env.isdigit() else INSTRUCTION_LIMIT_DEFAULT)
    )

    t0 = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="hks_sandbox_cwd_") as empty_cwd:
        try:
            proc = subprocess.run(
                [
                    lua_binary,
                    RECORDER_SCRIPT,
                    abs_entry,
                    abs_config_dir,
                    str(effective_instruction_limit),
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                cwd=empty_cwd,
                env=clean_env,
                timeout=timeout,
                preexec_fn=_apply_rlimits,
                check=False,
            )
            elapsed_ms = (time.monotonic() - t0) * 1000.0
        except subprocess.TimeoutExpired:
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            return RawRecorderOutput(
                binds=[],
                files_loaded=[abs_entry] if os.path.isfile(abs_entry) else [],
                diagnostics=[
                    Diagnostic(
                        level="error",
                        code="recorder_failed",
                        message=f"Lua recorder timed out after {timeout}s",
                        file=abs_entry,
                        line=None,
                    )
                ],
                ignored_calls={},
                unexecuted_callbacks=[],
                sandbox=SandboxStats(
                    instructions_used=0,
                    instruction_limit=effective_instruction_limit,
                    elapsed_ms=round(elapsed_ms, 2),
                    cpu_limit_s=float(CPU_LIMIT_SECONDS),
                    wall_timeout_s=float(timeout),
                ),
                complete=False,
            )
        except OSError as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            return RawRecorderOutput(
                binds=[],
                files_loaded=[abs_entry] if os.path.isfile(abs_entry) else [],
                diagnostics=[
                    Diagnostic(
                        level="error",
                        code="recorder_failed",
                        message=f"Failed to execute {lua_binary}: {exc}",
                        file=abs_entry,
                        line=None,
                    )
                ],
                ignored_calls={},
                unexecuted_callbacks=[],
                sandbox=SandboxStats(
                    instructions_used=0,
                    instruction_limit=effective_instruction_limit,
                    elapsed_ms=round(elapsed_ms, 2),
                    cpu_limit_s=float(CPU_LIMIT_SECONDS),
                    wall_timeout_s=float(timeout),
                ),
                complete=False,
            )

    if proc.returncode != 0:
        stderr_snippet = (proc.stderr or "").strip()
        msg = f"Lua recorder exited with status {proc.returncode}"
        if stderr_snippet:
            msg = f"{msg}: {stderr_snippet[:300]}"
        return RawRecorderOutput(
            binds=[],
            files_loaded=[abs_entry] if os.path.isfile(abs_entry) else [],
            diagnostics=[
                Diagnostic(
                    level="error",
                    code="recorder_failed",
                    message=msg,
                    file=abs_entry,
                    line=None,
                )
            ],
            ignored_calls={},
            unexecuted_callbacks=[],
            sandbox=SandboxStats(
                instructions_used=0,
                instruction_limit=effective_instruction_limit,
                elapsed_ms=round(elapsed_ms, 2),
                cpu_limit_s=float(CPU_LIMIT_SECONDS),
                wall_timeout_s=float(timeout),
            ),
            complete=False,
        )

    raw_stdout = (proc.stdout or "").strip()
    if not raw_stdout:
        return RawRecorderOutput(
            binds=[],
            files_loaded=[abs_entry] if os.path.isfile(abs_entry) else [],
            diagnostics=[
                Diagnostic(
                    level="error",
                    code="recorder_failed",
                    message="Lua recorder produced empty output",
                    file=abs_entry,
                    line=None,
                )
            ],
            ignored_calls={},
            unexecuted_callbacks=[],
            sandbox=SandboxStats(
                instructions_used=0,
                instruction_limit=effective_instruction_limit,
                elapsed_ms=round(elapsed_ms, 2),
                cpu_limit_s=float(CPU_LIMIT_SECONDS),
                wall_timeout_s=float(timeout),
            ),
            complete=False,
        )

    try:
        parsed = json.loads(raw_stdout)
        if not isinstance(parsed, dict):
            raise ValueError("Recorder root JSON is not an object")
    except ValueError as exc:
        return RawRecorderOutput(
            binds=[],
            files_loaded=[abs_entry] if os.path.isfile(abs_entry) else [],
            diagnostics=[
                Diagnostic(
                    level="error",
                    code="recorder_failed",
                    message=f"Lua recorder emitted invalid JSON: {exc}",
                    file=abs_entry,
                    line=None,
                )
            ],
            ignored_calls={},
            unexecuted_callbacks=[],
            sandbox=SandboxStats(
                instructions_used=0,
                instruction_limit=effective_instruction_limit,
                elapsed_ms=round(elapsed_ms, 2),
                cpu_limit_s=float(CPU_LIMIT_SECONDS),
                wall_timeout_s=float(timeout),
            ),
            complete=False,
        )

    diags: list[Diagnostic] = []
    for d in parsed.get("diagnostics") or []:
        if isinstance(d, dict):
            diags.append(
                Diagnostic(
                    level=str(d.get("level", "warning")),
                    code=str(d.get("code", "unknown")),
                    message=str(d.get("message", "")),
                    file=d.get("file") if isinstance(d.get("file"), str) else None,
                    line=int(d["line"]) if isinstance(d.get("line"), int) else None,
                )
            )

    raw_binds = parsed.get("binds")
    binds_list = raw_binds if isinstance(raw_binds, list) else []

    raw_files = parsed.get("files_loaded")
    files_list = [str(f) for f in raw_files] if isinstance(raw_files, list) else []

    raw_ignored = parsed.get("ignored_calls")
    ignored_map = (
        {str(k): int(v) for k, v in raw_ignored.items() if isinstance(v, (int, float))}
        if isinstance(raw_ignored, dict)
        else {}
    )

    raw_unexec = parsed.get("unexecuted_callbacks")
    unexec_list = (
        [dict(item) for item in raw_unexec if isinstance(item, dict)]
        if isinstance(raw_unexec, list)
        else []
    )

    instructions_used = int(parsed.get("instructions_used", 0))
    instruction_limit_val = int(parsed.get("instruction_limit", effective_instruction_limit))
    sandbox_stats = SandboxStats(
        instructions_used=instructions_used,
        instruction_limit=instruction_limit_val,
        elapsed_ms=round(elapsed_ms, 2),
        cpu_limit_s=float(CPU_LIMIT_SECONDS),
        wall_timeout_s=float(timeout),
    )

    return RawRecorderOutput(
        recorder_version=int(parsed.get("recorder_version", 1)),
        binds=binds_list,
        files_loaded=files_list,
        diagnostics=diags,
        ignored_calls=ignored_map,
        unexecuted_callbacks=unexec_list,
        sandbox=sandbox_stats,
        complete=bool(parsed.get("complete", False)),
    )
