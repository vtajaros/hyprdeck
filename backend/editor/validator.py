"""Configuration candidate verification via Hyprland --verify-config and the HyprDeck recorder."""

from __future__ import annotations

import contextlib
import fnmatch
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from backend.editor.edit_plan import EditOp
from backend.models.types import BindRecord, Diagnostic
from backend.parser import parse_hyprlang_config, parse_lua_config

FILE_LINE_MSG_RE = re.compile(r"^(.+?):(\d+):\s*(.+)$")
HYPRCONF_ERR_RE = re.compile(
    r"^Config error in file\s+(.+?)\s+at line\s+(\d+):\s*(.+)$",
    re.IGNORECASE,
)

NOISE_SUBSTRINGS = (
    "Socket2::UnixImpl",
    "Couldn't bind the Hyprland Socket",
    "DEBUG ]:",
    "Disabling stdout logs",
    "User-specified config location:",
    "Config is either explicit or special",
)


class RecorderVerificationError(Exception):
    """Raised when the HyprDeck recorder/parser fails to cleanly parse a candidate config."""

    def __init__(
        self,
        message: str,
        *,
        diagnostics: list[Diagnostic] | None = None,
        binds: list[BindRecord] | None = None,
    ) -> None:
        super().__init__(message)
        self.diagnostics: list[Diagnostic] = diagnostics or []
        self.binds: list[BindRecord] = binds or []


@dataclass(slots=True)
class VerifyResult:
    ok: bool | None  # True = ok, False = error, None = hyprland_unavailable
    exit_code: int | None
    message: str
    line: int | None = None
    reason: str | None = None
    raw_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "line": self.line,
            "message": self.message,
            "ok": self.ok,
            "reason": self.reason,
        }


def _is_noise_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    for sub in NOISE_SUBSTRINGS:
        if sub in s:
            return True
    return False


def _parse_verify_error(lines: list[str], candidate_path: str) -> tuple[str, int | None]:
    """Extract a normalized 'file:line: message' and line number from Hyprland error lines."""
    clean_lines = [ln.strip() for ln in lines if not _is_noise_line(ln)]
    if not clean_lines:
        return f"{candidate_path}:1: unknown configuration verification failure", None

    c_detail: str | None = None
    for ln in clean_lines:
        if ln.startswith("=[C]:"):
            parts = ln.split(":", 2)
            if len(parts) == 3 and parts[2].strip():
                c_detail = parts[2].strip()
            continue

        m_conf = HYPRCONF_ERR_RE.match(ln)
        if m_conf:
            f_path, line_s, msg = m_conf.group(1), m_conf.group(2), m_conf.group(3)
            line_no = int(line_s)
            return f"{f_path}:{line_no}: {msg}", line_no

        m_fl = FILE_LINE_MSG_RE.match(ln)
        if m_fl:
            f_path, line_s, msg = m_fl.group(1), m_fl.group(2), m_fl.group(3)
            # Clean optional leading 'require("..."): ' prefix
            if ": /" in f_path:
                f_path = "/" + f_path.split(": /", 1)[1]
            line_no = int(line_s)
            if c_detail and c_detail not in msg:
                msg = f"{c_detail} ({msg})"
            return f"{f_path}:{line_no}: {msg}", line_no

    first = clean_lines[0]
    return f"{candidate_path}:1: {first}", None


def verify_with_hyprland(
    candidate_path: str,
    *,
    timeout: float = 20.0,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> VerifyResult:
    """Run `Hyprland --verify-config --config <candidate_path>` and parse the result."""
    abs_candidate = os.path.abspath(os.path.expanduser(candidate_path))
    run_fn = runner if runner is not None else subprocess.run

    try:
        proc = run_fn(
            ["Hyprland", "--verify-config", "--config", abs_candidate],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return VerifyResult(
            ok=None,
            exit_code=None,
            message="hyprland_unavailable",
            line=None,
            reason="hyprland_unavailable",
            raw_output="",
        )
    except subprocess.TimeoutExpired:
        return VerifyResult(
            ok=False,
            exit_code=None,
            message=f"{abs_candidate}:1: Hyprland --verify-config timed out after {timeout}s",
            line=None,
            reason="timeout",
            raw_output="",
        )
    except OSError as exc:
        return VerifyResult(
            ok=None,
            exit_code=None,
            message=f"hyprland_unavailable: {exc}",
            line=None,
            reason="hyprland_unavailable",
            raw_output="",
        )

    combined = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    marker = "Config parsing result:"
    if marker in combined:
        after_marker = combined.split(marker, 1)[1]
    else:
        after_marker = combined

    after_stripped = after_marker.strip()
    if after_stripped.lower() == "config ok" and proc.returncode == 0:
        return VerifyResult(
            ok=True,
            exit_code=proc.returncode,
            message="config ok",
            line=None,
            reason="ok",
            raw_output=after_stripped,
        )

    err_lines = after_marker.splitlines()
    msg, line_no = _parse_verify_error(err_lines, abs_candidate)
    return VerifyResult(
        ok=False,
        exit_code=proc.returncode,
        message=msg,
        line=line_no,
        reason="config_error",
        raw_output=after_stripped,
    )


_LUA_ONLY_DISPATCHERS = frozenset({
    "exec_cmd",
    "window.close",
    "window.float",
    "window.fullscreen",
    "window.move",
    "window.resize",
    "window.pin",
})


def validate_hyprlang_structure(text: str, entrypoint: str = "hyprland.conf") -> VerifyResult:
    """Strict stdlib structural validator for Hyprlang .conf files.

    Used as a UNIT-ONLY fallback when `Hyprland --verify-config` runs in Lua-only mode.
    Checks brace balance, quote termination, bind* field arity, Lua-only dispatcher leaks,
    and submap = reset pairing.
    """
    brace_depth = 0
    active_submap: str | None = None
    lines = text.splitlines()

    for line_no, raw_line in enumerate(lines, start=1):
        in_str: str | None = None
        in_esc = False
        code_chars: list[str] = []
        for ch in raw_line:
            if in_esc:
                in_esc = False
                code_chars.append(ch)
                continue
            if ch == "\\" and in_str is not None:
                in_esc = True
                code_chars.append(ch)
                continue
            if in_str is not None:
                if ch == in_str:
                    in_str = None
                code_chars.append(ch)
                continue
            if ch in ('"', "'"):
                in_str = ch
                code_chars.append(ch)
                continue
            if ch == "#":
                break
            if ch == "{":
                brace_depth += 1
            elif ch == "}":
                brace_depth -= 1
                if brace_depth < 0:
                    return VerifyResult(
                        ok=False,
                        exit_code=1,
                        message=f"{entrypoint}:{line_no}: unexpected closing brace '}}'",
                        line=line_no,
                        reason="config_error",
                        raw_output="",
                    )
            code_chars.append(ch)

        if in_str is not None:
            return VerifyResult(
                ok=False,
                exit_code=1,
                message=f"{entrypoint}:{line_no}: unterminated string literal ({in_str})",
                line=line_no,
                reason="config_error",
                raw_output="",
            )

        code = "".join(code_chars).strip()
        if not code:
            continue

        m_sub = re.match(r"^submap\s*=\s*(.+)$", code)
        if m_sub:
            sub_val = m_sub.group(1).strip()
            if sub_val == "reset":
                active_submap = None
            else:
                active_submap = sub_val
            continue

        m_bind = re.match(r"^(bind[a-zA-Z]*)\s*=\s*(.*)$", code)
        if m_bind:
            rhs = m_bind.group(2)
            fields = [f.strip() for f in rhs.split(",")]
            if len(fields) < 3:
                return VerifyResult(
                    ok=False,
                    exit_code=1,
                    message=f"{entrypoint}:{line_no}: {m_bind.group(1)} requires at least 3 comma-separated fields",
                    line=line_no,
                    reason="config_error",
                    raw_output="",
                )
            key_field = fields[1]
            dsp_field = fields[2]
            if not key_field or not dsp_field:
                return VerifyResult(
                    ok=False,
                    exit_code=1,
                    message=f"{entrypoint}:{line_no}: empty key or dispatcher in {m_bind.group(1)}",
                    line=line_no,
                    reason="config_error",
                    raw_output="",
                )
            if dsp_field.lower() in _LUA_ONLY_DISPATCHERS or dsp_field.lower().startswith("hl.dsp."):
                return VerifyResult(
                    ok=False,
                    exit_code=1,
                    message=f"{entrypoint}:{line_no}: Lua-only dispatcher '{dsp_field}' in Hyprlang config",
                    line=line_no,
                    reason="config_error",
                    raw_output="",
                )

    if brace_depth != 0:
        return VerifyResult(
            ok=False,
            exit_code=1,
            message=f"{entrypoint}:{len(lines)}: unclosed '{{' brace(s) (depth={brace_depth})",
            line=len(lines),
            reason="config_error",
            raw_output="",
        )
    if active_submap is not None:
        return VerifyResult(
            ok=False,
            exit_code=1,
            message=f"{entrypoint}:{len(lines)}: unclosed submap '{active_submap}' (missing 'submap = reset')",
            line=len(lines),
            reason="config_error",
            raw_output="",
        )

    return VerifyResult(
        ok=True,
        exit_code=0,
        message="hyprlang structure ok (UNIT-ONLY)",
        line=None,
        reason="ok",
        raw_output="",
    )


def verify_with_recorder(
    candidate_path: str,
    config_dir: str,
    *,
    env: dict[str, str] | None = None,
) -> list[BindRecord]:
    """Run the HyprDeck recorder/parser on `candidate_path` and return the parsed BindRecords.

    Raises RecorderVerificationError if parsing is incomplete or produces error diagnostics.
    """
    abs_candidate = os.path.abspath(os.path.expanduser(candidate_path))
    abs_config_dir = os.path.abspath(os.path.expanduser(config_dir))

    if abs_candidate.endswith(".lua"):
        binds, _, diags, _, complete = parse_lua_config(
            entrypoint=abs_candidate,
            config_dir=abs_config_dir,
            env=env,
        )
    else:
        binds, _, _, diags, _, complete = parse_hyprlang_config(
            entrypoint=abs_candidate,
        )

    error_diags = [d for d in diags if d.level == "error"]
    if not complete or error_diags:
        if error_diags:
            first = error_diags[0]
            loc = f"{first.file or abs_candidate}:{first.line or 1}"
            msg = f"{loc}: [{first.code}] {first.message}"
        else:
            msg = f"{abs_candidate}:1: recorder failed to complete parsing"
        raise RecorderVerificationError(msg, diagnostics=diags, binds=binds)

    return binds


def _should_skip_copy(name: str) -> bool:
    if name in (".git", "backups", "__pycache__"):
        return True
    if fnmatch.fnmatch(name, "*.bak*") or fnmatch.fnmatch(name, ".*.hks-tmp-*"):
        return True
    return False


def _copy_config_tree(src_dir: str, dst_dir: str) -> None:
    """Copy configuration files from src_dir to dst_dir, skipping backups and *.bak* files."""
    for root, dirs, files in os.walk(src_dir, followlinks=False):
        dirs[:] = [d for d in dirs if not _should_skip_copy(d)]
        rel_root = os.path.relpath(root, src_dir)
        target_root = dst_dir if rel_root == "." else os.path.join(dst_dir, rel_root)
        os.makedirs(target_root, exist_ok=True)
        for fname in files:
            if _should_skip_copy(fname):
                continue
            src_file = os.path.join(root, fname)
            dst_file = os.path.join(target_root, fname)
            if os.path.islink(src_file):
                link_target = os.readlink(src_file)
                os.symlink(link_target, dst_file)
            elif os.path.isfile(src_file):
                shutil.copy2(src_file, dst_file)


@contextlib.contextmanager
def stage_candidate_config(
    config_dir: str,
    entrypoint: str,
    target_file: str,
    new_bytes: bytes,
) -> Iterator[tuple[str, str, str]]:
    """Stage a copy of config_dir in a temporary directory with `target_file` updated to `new_bytes`.

    Yields (staged_config_dir, staged_entrypoint, staged_target_file).
    """
    abs_config_dir = os.path.abspath(os.path.expanduser(config_dir))
    abs_entrypoint = os.path.abspath(os.path.expanduser(entrypoint))
    abs_target = os.path.abspath(os.path.expanduser(target_file))

    with tempfile.TemporaryDirectory(prefix="hyprdeck-stage-") as tmp_dir:
        if os.path.isdir(abs_config_dir):
            _copy_config_tree(abs_config_dir, tmp_dir)

        try:
            rel_entry = os.path.relpath(abs_entrypoint, abs_config_dir)
        except ValueError:
            rel_entry = os.path.basename(abs_entrypoint)
        if rel_entry.startswith(".."):
            rel_entry = os.path.basename(abs_entrypoint)

        try:
            rel_target = os.path.relpath(abs_target, abs_config_dir)
        except ValueError:
            rel_target = os.path.basename(abs_target)
        if rel_target.startswith(".."):
            rel_target = os.path.basename(abs_target)

        staged_entrypoint = os.path.join(tmp_dir, rel_entry)
        staged_target = os.path.join(tmp_dir, rel_target)
        os.makedirs(os.path.dirname(staged_target), exist_ok=True)
        with open(staged_target, "wb") as f:
            f.write(new_bytes)

        yield tmp_dir, staged_entrypoint, staged_target


BindSignature = tuple[str, str, int, str, tuple[tuple[str, bool], ...], str, str]


def bind_semantic_signature(bind: BindRecord, base_dir: str) -> BindSignature:
    """Build a directory-independent semantic signature for a BindRecord."""
    abs_base = os.path.abspath(base_dir)
    abs_src = os.path.abspath(bind.source_file)
    try:
        rel_file = os.path.relpath(abs_src, abs_base)
    except ValueError:
        rel_file = os.path.basename(abs_src)
    if rel_file.startswith(".."):
        rel_file = os.path.basename(abs_src)

    return (
        rel_file,
        bind.submap,
        int(bind.modmask),
        bind.key.lower(),
        tuple(sorted((k, bool(v)) for k, v in bind.flags.items())),
        bind.dispatcher.path,
        bind.dispatcher.arg_summary,
    )


@dataclass(slots=True)
class BindSetComparison:
    ok: bool
    before_count: int
    after_count: int
    removed_count: int
    added_count: int
    message: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "added_count": self.added_count,
            "after_count": self.after_count,
            "before_count": self.before_count,
            "message": self.message,
            "ok": self.ok,
            "removed_count": self.removed_count,
        }


def _bind_matches_expected(actual: BindRecord, expected: BindRecord) -> bool:
    """Check if an actual parsed bind matches the expected new bind properties."""
    if actual.modmask != expected.modmask:
        return False
    if actual.key.lower() != expected.key.lower():
        return False
    if (actual.submap or "") != (expected.submap or ""):
        return False

    # Check dispatcher path (allow 'exec_cmd' vs 'hl.dsp.exec_cmd')
    act_dsp = actual.dispatcher.path.split(".")[-1]
    exp_dsp = expected.dispatcher.path.split(".")[-1]
    if act_dsp != exp_dsp:
        return False

    # Check args if expected provides non-empty args
    exp_arg = (expected.dispatcher.arg_summary or expected.args_raw or "").strip().strip("\"'")
    act_arg = (actual.dispatcher.arg_summary or actual.args_raw or "").strip().strip("\"'")
    if exp_arg and act_arg != exp_arg:
        return False

    if expected.flags:
        for k, v in expected.flags.items():
            if v and not actual.flags.get(k, False):
                return False

    return True


def compare_bind_sets(
    before_binds: list[BindRecord],
    after_binds: list[BindRecord],
    ops: list[EditOp],
    before_dir: str,
    after_dir: str,
    *,
    op_kind: str | None = None,
    expected_new_bind: BindRecord | None = None,
) -> BindSetComparison:
    """Verify that the difference between before_binds and after_binds matches `ops`.

    Asserts per-operation invariants:
    - DISABLE/DELETE: exactly -1 bind (the targeted one), nothing else changed.
    - ENABLE/RESTORE: exactly +1 bind restored, nothing else changed.
    - REPLACE: exactly 1 removed and 1 added (the added matching expected_new_bind if provided).
    - INSERT: exactly +1 bind added (matching expected_new_bind if provided).
    """
    # Ensure no newly produced bind has a broken parse_status
    before_bad = sum(1 for b in before_binds if b.parse_status != "ok")
    after_bad = sum(1 for b in after_binds if b.parse_status != "ok")
    if after_bad > before_bad:
        return BindSetComparison(
            ok=False,
            before_count=len(before_binds),
            after_count=len(after_binds),
            removed_count=0,
            added_count=0,
            message=f"Candidate config introduced {after_bad - before_bad} unparsable/partial bind(s).",
        )

    before_counter = Counter(bind_semantic_signature(b, before_dir) for b in before_binds)
    after_counter = Counter(bind_semantic_signature(b, after_dir) for b in after_binds)

    removed_counter = before_counter - after_counter
    added_counter = after_counter - before_counter
    removed_total = sum(removed_counter.values())
    added_total = sum(added_counter.values())

    # Identify binds in before_binds located on lines targeted by removal/replacement ops
    removal_lines: set[tuple[str, int]] = set()
    replace_lines: set[tuple[str, int]] = set()
    uncomment_count = 0
    insert_count = 0

    for op in ops:
        abs_op_file = os.path.abspath(os.path.expanduser(op.file))
        if op.kind in ("comment_out", "delete_line"):
            removal_lines.add((abs_op_file, op.line_number))
        elif op.kind == "replace_line":
            replace_lines.add((abs_op_file, op.line_number))
        elif op.kind == "uncomment":
            uncomment_count += 1
        elif op.kind == "insert_after":
            insert_count += 1

    expected_removed_binds = [
        b
        for b in before_binds
        if (os.path.abspath(b.source_file), b.source_line) in removal_lines
    ]
    expected_replaced_binds = [
        b
        for b in before_binds
        if (os.path.abspath(b.source_file), b.source_line) in replace_lines
    ]

    expected_removed_counter = Counter(
        bind_semantic_signature(b, before_dir) for b in expected_removed_binds
    )
    expected_replaced_counter = Counter(
        bind_semantic_signature(b, before_dir) for b in expected_replaced_binds
    )

    # Determine primary operation kind if not explicitly passed
    effective_kind = op_kind
    if effective_kind is None:
        if replace_lines and not removal_lines and uncomment_count == 0 and insert_count == 0:
            effective_kind = "replace"
        elif insert_count > 0 and not replace_lines and not removal_lines and uncomment_count == 0:
            effective_kind = "insert"
        elif uncomment_count > 0 and not replace_lines and not removal_lines and insert_count == 0:
            effective_kind = "uncomment"
        elif removal_lines and not replace_lines and uncomment_count == 0 and insert_count == 0:
            effective_kind = "disable_or_delete"

    # --- 1. Pure DISABLE / DELETE ---
    if effective_kind == "disable_or_delete" or (
        not replace_lines and uncomment_count == 0 and insert_count == 0
    ):
        expected_count = len(removal_lines) if removal_lines else sum(expected_removed_counter.values())
        if added_total != 0:
            return BindSetComparison(
                ok=False,
                before_count=len(before_binds),
                after_count=len(after_binds),
                removed_count=removed_total,
                added_count=added_total,
                message=f"Validation failed: DISABLE/DELETE added {added_total} unexpected bind(s) (expected 0).",
            )
        if removed_total != expected_count or removed_counter != expected_removed_counter:
            return BindSetComparison(
                ok=False,
                before_count=len(before_binds),
                after_count=len(after_binds),
                removed_count=removed_total,
                added_count=added_total,
                message=(
                    f"Validation failed: DISABLE/DELETE removed {removed_total} bind(s) "
                    f"(expected exactly {expected_count} targeted bind(s))."
                ),
            )
        return BindSetComparison(
            ok=True,
            before_count=len(before_binds),
            after_count=len(after_binds),
            removed_count=removed_total,
            added_count=added_total,
            message=f"Bind set verified: exactly -{removed_total} bind(s) removed, nothing else changed.",
        )

    # --- 2. Pure REPLACE ---
    if effective_kind == "replace" or (
        replace_lines and not removal_lines and uncomment_count == 0 and insert_count == 0
    ):
        target_count = len(replace_lines)
        if removed_total != target_count or added_total != target_count:
            return BindSetComparison(
                ok=False,
                before_count=len(before_binds),
                after_count=len(after_binds),
                removed_count=removed_total,
                added_count=added_total,
                message=(
                    f"Validation failed: REPLACE expected exactly {target_count} removed and "
                    f"{target_count} added (got -{removed_total}, +{added_total})."
                ),
            )
        if removed_counter != expected_replaced_counter:
            return BindSetComparison(
                ok=False,
                before_count=len(before_binds),
                after_count=len(after_binds),
                removed_count=removed_total,
                added_count=added_total,
                message="Validation failed: REPLACE removed bind did not match targeted line.",
            )
        # Check added bind matches expected_new_bind if provided
        if expected_new_bind is not None:
            # Find the actual newly added bind object from after_binds
            added_sigs = set(added_counter.keys())
            matched_added = False
            for b in after_binds:
                if bind_semantic_signature(b, after_dir) in added_sigs:
                    if _bind_matches_expected(b, expected_new_bind):
                        matched_added = True
                        break
            if not matched_added:
                return BindSetComparison(
                    ok=False,
                    before_count=len(before_binds),
                    after_count=len(after_binds),
                    removed_count=removed_total,
                    added_count=added_total,
                    message=f"Validation failed: REPLACE added bind did not match expected new bind ({expected_new_bind.keys_raw}).",
                )

        return BindSetComparison(
            ok=True,
            before_count=len(before_binds),
            after_count=len(after_binds),
            removed_count=removed_total,
            added_count=added_total,
            message="Bind set verified: exactly 1 bind replaced (1 removed, 1 added matching expected new bind).",
        )

    # --- 3. Pure INSERT ---
    if effective_kind == "insert" or (
        insert_count > 0 and not replace_lines and not removal_lines and uncomment_count == 0
    ):
        if removed_total != 0:
            return BindSetComparison(
                ok=False,
                before_count=len(before_binds),
                after_count=len(after_binds),
                removed_count=removed_total,
                added_count=added_total,
                message=f"Validation failed: INSERT unexpectedly removed {removed_total} bind(s) (expected 0).",
            )
        if added_total != insert_count:
            return BindSetComparison(
                ok=False,
                before_count=len(before_binds),
                after_count=len(after_binds),
                removed_count=removed_total,
                added_count=added_total,
                message=f"Validation failed: INSERT added {added_total} bind(s) (expected exactly {insert_count}).",
            )
        if expected_new_bind is not None:
            added_sigs = set(added_counter.keys())
            matched_added = False
            for b in after_binds:
                if bind_semantic_signature(b, after_dir) in added_sigs:
                    if _bind_matches_expected(b, expected_new_bind):
                        matched_added = True
                        break
            if not matched_added:
                return BindSetComparison(
                    ok=False,
                    before_count=len(before_binds),
                    after_count=len(after_binds),
                    removed_count=removed_total,
                    added_count=added_total,
                    message=f"Validation failed: INSERT added bind did not match expected bind ({expected_new_bind.keys_raw}).",
                )

        return BindSetComparison(
            ok=True,
            before_count=len(before_binds),
            after_count=len(after_binds),
            removed_count=0,
            added_count=added_total,
            message=f"Bind set verified: exactly +{added_total} bind(s) inserted, nothing else changed.",
        )

    # --- 4. Pure UNCOMMENT / RESTORE ---
    if effective_kind == "uncomment" or (
        uncomment_count > 0 and not replace_lines and not removal_lines and insert_count == 0
    ):
        if removed_total != 0:
            return BindSetComparison(
                ok=False,
                before_count=len(before_binds),
                after_count=len(after_binds),
                removed_count=removed_total,
                added_count=added_total,
                message=f"Validation failed: UNCOMMENT unexpectedly removed {removed_total} bind(s) (expected 0).",
            )
        if added_total != uncomment_count:
            return BindSetComparison(
                ok=False,
                before_count=len(before_binds),
                after_count=len(after_binds),
                removed_count=removed_total,
                added_count=added_total,
                message=f"Validation failed: UNCOMMENT added {added_total} bind(s) (expected exactly {uncomment_count}).",
            )
        return BindSetComparison(
            ok=True,
            before_count=len(before_binds),
            after_count=len(after_binds),
            removed_count=0,
            added_count=added_total,
            message=f"Bind set verified: exactly +{added_total} bind(s) restored, nothing else changed.",
        )

    # Mixed / fallback case (e.g. multi-op restore from backup)
    max_allowed_removed = expected_removed_counter + expected_replaced_counter
    unexpected_removals = removed_counter - max_allowed_removed
    if sum(unexpected_removals.values()) > 0:
        return BindSetComparison(
            ok=False,
            before_count=len(before_binds),
            after_count=len(after_binds),
            removed_count=removed_total,
            added_count=added_total,
            message=f"Edit unexpectedly removed {sum(unexpected_removals.values())} untargeted bind(s).",
        )

    return BindSetComparison(
        ok=True,
        before_count=len(before_binds),
        after_count=len(after_binds),
        removed_count=removed_total,
        added_count=added_total,
        message=f"Bind set verified: -{removed_total} bind(s), +{added_total} bind(s).",
    )
