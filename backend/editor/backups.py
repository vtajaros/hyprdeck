"""Backup creation, listing, and atomic restoration for Hyprland Keybind Studio."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Any


class BackupError(Exception):
    """Base error for backup operations."""


class BackupConflictError(BackupError):
    """Raised when restoring a backup fails due to unexpected current file hash."""


@dataclass(slots=True)
class BackupRecord:
    id: str
    original_path: str
    backup_path: str
    sha256: str
    created_at: str
    sidecar_backup_path: str | None = None
    sidecar_original_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "backup_path": self.backup_path,
            "created_at": self.created_at,
            "id": self.id,
            "original_path": self.original_path,
            "sha256": self.sha256,
        }
        if self.sidecar_backup_path is not None:
            d["sidecar_backup_path"] = self.sidecar_backup_path
        if self.sidecar_original_path is not None:
            d["sidecar_original_path"] = self.sidecar_original_path
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackupRecord:
        return cls(
            id=str(data["id"]),
            original_path=str(data["original_path"]),
            backup_path=str(data["backup_path"]),
            sha256=str(data["sha256"]),
            created_at=str(data["created_at"]),
            sidecar_backup_path=data.get("sidecar_backup_path"),
            sidecar_original_path=data.get("sidecar_original_path"),
        )


def resolve_backup_dir(
    backup_dir: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Resolve the backup directory (~/.local/share/hks/backups or $HKS_BACKUP_DIR)."""
    if backup_dir:
        return os.path.abspath(os.path.expanduser(backup_dir))
    environ = env if env is not None else os.environ
    override = environ.get("HKS_BACKUP_DIR", "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    home = environ.get("HOME", "").strip() or os.path.expanduser("~")
    return os.path.abspath(os.path.join(home, ".local", "share", "hks", "backups"))


def _ensure_not_inside_config_dir(backup_dir: str, target_dir: str) -> None:
    """Refuse backup directories located inside the Hyprland configuration directory."""
    real_backup = os.path.realpath(os.path.abspath(backup_dir))
    real_target = os.path.realpath(os.path.abspath(target_dir))
    try:
        common = os.path.commonpath([real_backup, real_target])
    except ValueError:
        return
    if common == real_target:
        raise BackupError(
            f"Backup directory ({backup_dir}) must never be inside the config directory ({target_dir})."
        )


def compute_file_sha256(path: str) -> str:
    """Compute hex SHA-256 of a file on disk."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def atomic_write_bytes(
    target_path: str,
    data: bytes,
    mode_source: str | None = None,
) -> None:
    """Atomically write bytes to target_path using a temp file in the same directory, fsync, and os.replace."""
    abs_target = os.path.abspath(os.path.expanduser(target_path))
    target_dir = os.path.dirname(abs_target)
    basename = os.path.basename(abs_target)
    os.makedirs(target_dir, exist_ok=True)

    existing_mode: int | None = None
    if mode_source and os.path.exists(mode_source):
        existing_mode = os.stat(mode_source).st_mode
    elif os.path.exists(abs_target):
        existing_mode = os.stat(abs_target).st_mode

    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{basename}.hks-tmp-",
        dir=target_dir,
    )
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(data)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        if existing_mode is not None:
            os.chmod(tmp_path, existing_mode & 0o7777)
        os.replace(tmp_path, abs_target)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


def _read_index(index_path: str) -> list[BackupRecord]:
    if not os.path.isfile(index_path):
        return []
    with open(index_path, "rb") as f:
        raw = f.read().decode("utf-8", errors="replace").strip()
    if not raw:
        return []
    data = json.loads(raw)
    if not isinstance(data, list):
        raise BackupError(f"Corrupt backups index (expected JSON list): {index_path}")
    return [BackupRecord.from_dict(item) for item in data if isinstance(item, dict)]


def _write_index(index_path: str, records: list[BackupRecord]) -> None:
    payload = json.dumps(
        [r.to_dict() for r in records],
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8") + b"\n"
    atomic_write_bytes(index_path, payload)


def create_backup(
    path: str,
    *,
    backup_dir: str | None = None,
    config_dir: str | None = None,
    env: dict[str, str] | None = None,
    sidecar_path: str | None = None,
) -> BackupRecord:
    """Create a timestamped, hash-tagged backup of `path` and append to backups.json."""
    abs_path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(abs_path):
        raise BackupError(f"Cannot back up non-existent file: {abs_path}")

    resolved_bdir = resolve_backup_dir(backup_dir=backup_dir, env=env)
    cfg_to_check = config_dir if config_dir else os.path.dirname(abs_path)
    _ensure_not_inside_config_dir(resolved_bdir, cfg_to_check)

    os.makedirs(resolved_bdir, exist_ok=True)

    sha256 = compute_file_sha256(abs_path)
    shorthash = sha256[:8]
    now = datetime.datetime.now(datetime.timezone.utc)
    ts_str = now.strftime("%Y%m%d-%H%M%S")
    created_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    basename = os.path.basename(abs_path)

    candidate_id = f"{basename}.{ts_str}-{shorthash}"
    candidate_path = os.path.join(resolved_bdir, candidate_id)
    counter = 2
    while os.path.exists(candidate_path):
        candidate_id = f"{basename}.{ts_str}-{shorthash}-{counter}"
        candidate_path = os.path.join(resolved_bdir, candidate_id)
        counter += 1

    shutil.copy2(abs_path, candidate_path)

    s_backup_path: str | None = None
    s_orig_path: str | None = None
    if sidecar_path is not None:
        abs_sidecar = os.path.abspath(os.path.expanduser(sidecar_path))
        s_orig_path = abs_sidecar
        if os.path.isfile(abs_sidecar):
            from backend.describe.sidecar_store import backup_sidecar_file
            s_backup_path = backup_sidecar_file(abs_sidecar, backup_dir=resolved_bdir, env=env)
        else:
            s_backup_path = "none"

    record = BackupRecord(
        id=candidate_id,
        original_path=abs_path,
        backup_path=candidate_path,
        sha256=sha256,
        created_at=created_at,
        sidecar_backup_path=s_backup_path,
        sidecar_original_path=s_orig_path,
    )

    index_path = os.path.join(resolved_bdir, "backups.json")
    records = _read_index(index_path)
    records.append(record)
    _write_index(index_path, records)

    return record


def list_backups(
    path: str | None = None,
    *,
    backup_dir: str | None = None,
    env: dict[str, str] | None = None,
) -> list[BackupRecord]:
    """List recorded backups, optionally filtered by original file path."""
    resolved_bdir = resolve_backup_dir(backup_dir=backup_dir, env=env)
    index_path = os.path.join(resolved_bdir, "backups.json")
    records = _read_index(index_path)
    if path is None:
        return records
    abs_filter = os.path.abspath(os.path.expanduser(path))
    return [r for r in records if os.path.abspath(r.original_path) == abs_filter]


def restore_backup(
    record: BackupRecord | str,
    expected_current_sha256: str | None = None,
    *,
    force: bool = False,
    backup_dir: str | None = None,
    env: dict[str, str] | None = None,
) -> BackupRecord:
    """Atomically restore a backup to its original_path.

    Refuses if `expected_current_sha256` is given (or if `force` is False and current file
    differs from expected) unless `force=True`.
    """
    resolved_bdir = resolve_backup_dir(backup_dir=backup_dir, env=env)
    if isinstance(record, str):
        all_records = list_backups(backup_dir=resolved_bdir, env=env)
        matched: BackupRecord | None = None
        for r in all_records:
            if r.id == record or r.backup_path == record:
                matched = r
                break
        if matched is None:
            raise BackupError(f"Backup record not found: {record}")
        target_record = matched
    else:
        target_record = record

    if not os.path.isfile(target_record.backup_path):
        raise BackupError(f"Backup file is missing on disk: {target_record.backup_path}")

    with open(target_record.backup_path, "rb") as f:
        backup_bytes = f.read()

    actual_backup_sha = hashlib.sha256(backup_bytes).hexdigest()
    if actual_backup_sha != target_record.sha256:
        raise BackupError(
            f"Backup file integrity check failed for {target_record.id}: "
            f"expected {target_record.sha256}, got {actual_backup_sha}"
        )

    if not force and expected_current_sha256 is not None:
        if os.path.isfile(target_record.original_path):
            current_sha = compute_file_sha256(target_record.original_path)
            if current_sha != expected_current_sha256:
                raise BackupConflictError(
                    f"Refusing to restore {target_record.id}: current file {target_record.original_path} "
                    f"has sha256 {current_sha}, expected {expected_current_sha256} (concurrent modification)."
                )
        else:
            raise BackupConflictError(
                f"Refusing to restore {target_record.id}: target file {target_record.original_path} "
                f"does not exist (expected sha256 {expected_current_sha256})."
            )

    atomic_write_bytes(
        target_record.original_path,
        backup_bytes,
        mode_source=target_record.backup_path,
    )

    if target_record.sidecar_backup_path and target_record.sidecar_original_path:
        if target_record.sidecar_backup_path == "none":
            if os.path.isfile(target_record.sidecar_original_path):
                try:
                    os.unlink(target_record.sidecar_original_path)
                except OSError:
                    pass
        elif os.path.isfile(target_record.sidecar_backup_path):
            with open(target_record.sidecar_backup_path, "rb") as sf:
                s_bytes = sf.read()
            atomic_write_bytes(
                target_record.sidecar_original_path,
                s_bytes,
                mode_source=target_record.sidecar_backup_path,
            )

    return target_record
