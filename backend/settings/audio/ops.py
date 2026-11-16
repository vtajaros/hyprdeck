"""Audio mutation operations (volume, mute, default device) with readback verification."""

from __future__ import annotations

import math
from typing import Any

from backend.core.live_cmd import DEFAULT_LIVE_CMD_TIMEOUT_SECONDS, LiveRunner, run_live_cmd
from backend.settings.audio.state import get_audio_state

DEFAULT_MAX_VOLUME = 100
HARD_MAX_VOLUME = 150
VALID_MUTE_MODES = frozenset({"1", "0", "toggle"})


def validate_and_clamp_volume(
    value: Any,
    *,
    max_percent: int = DEFAULT_MAX_VOLUME,
) -> int:
    """Validate numeric volume and clamp to [0, min(max_percent, 150)]."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"Volume must be a finite number, got {value!r}.")
    try:
        num = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Volume must be a finite number, got {value!r}.") from exc
    if math.isnan(num) or math.isinf(num):
        raise ValueError(f"Volume must be a finite number, got {value!r}.")

    if isinstance(max_percent, bool):
        raise ValueError(f"max_percent must be an integer, got {max_percent!r}.")
    cap = max(0, min(HARD_MAX_VOLUME, int(max_percent)))
    rounded = int(round(num))
    return max(0, min(cap, rounded))


def normalize_mute_mode(mode: Any) -> str:
    """Normalize mute mode to '1', '0', or 'toggle'."""
    if isinstance(mode, bool):
        return "1" if mode else "0"
    s = str(mode).strip().lower()
    if s in VALID_MUTE_MODES:
        return s
    if s in ("true", "mute", "on"):
        return "1"
    if s in ("false", "unmute", "off"):
        return "0"
    raise ValueError(f"Mute mode must be '1', '0', or 'toggle', got {mode!r}.")


def _validate_node_name(name: Any) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Device node name must be a non-empty string.")
    cleaned = name.strip()
    if cleaned.isdigit():
        raise ValueError(
            f"Device must be addressed by node name, not numeric index ({cleaned!r})."
        )
    return cleaned


def _find_device(
    state: dict[str, Any],
    list_key: str,
    name: str,
) -> dict[str, Any] | None:
    for dev in state.get(list_key, []):
        if isinstance(dev, dict) and dev.get("name") == name:
            return dev
    return None


def _fail(error: str, before: Any = None, after: Any = None) -> dict[str, Any]:
    return {"ok": False, "before": before, "after": after, "error": error}


def _set_volume(
    *,
    kind: str,
    name: Any,
    percent: Any,
    max_percent: int = DEFAULT_MAX_VOLUME,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    try:
        node_name = _validate_node_name(name)
        target_pct = validate_and_clamp_volume(percent, max_percent=max_percent)
    except ValueError as exc:
        return _fail(str(exc))

    list_key = "outputs" if kind == "sink" else "inputs"
    pactl_cmd = "set-sink-volume" if kind == "sink" else "set-source-volume"

    before_state = get_audio_state(runner=runner, timeout=timeout)
    if not before_state.get("available"):
        return _fail(before_state.get("error") or "Audio daemon unavailable.")

    before_dev = _find_device(before_state, list_key, node_name)
    if before_dev is None:
        return _fail(f"Unknown {kind}: {node_name}")

    write_res = run_live_cmd(
        ["pactl", pactl_cmd, node_name, f"{target_pct}%"],
        timeout=timeout,
        runner=runner,
    )
    if not write_res.ok:
        return _fail(
            write_res.err.strip() or f"pactl {pactl_cmd} failed (rc={write_res.rc})",
            before=before_dev,
        )

    after_state = get_audio_state(runner=runner, timeout=timeout)
    if not after_state.get("available"):
        return _fail(
            after_state.get("error") or "Audio daemon unavailable during readback.",
            before=before_dev,
        )

    after_dev = _find_device(after_state, list_key, node_name)
    if after_dev is None:
        return _fail(
            f"{kind.capitalize()} {node_name!r} vanished during readback.",
            before=before_dev,
        )

    if after_dev.get("volume_percent") != target_pct:
        return _fail(
            f"Volume readback mismatch for {node_name}: expected {target_pct}%, got {after_dev.get('volume_percent')}%.",
            before=before_dev,
            after=after_dev,
        )

    return {"ok": True, "before": before_dev, "after": after_dev, "error": None}


def _set_mute(
    *,
    kind: str,
    name: Any,
    mode: Any,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    try:
        node_name = _validate_node_name(name)
        mute_arg = normalize_mute_mode(mode)
    except ValueError as exc:
        return _fail(str(exc))

    list_key = "outputs" if kind == "sink" else "inputs"
    pactl_cmd = "set-sink-mute" if kind == "sink" else "set-source-mute"

    before_state = get_audio_state(runner=runner, timeout=timeout)
    if not before_state.get("available"):
        return _fail(before_state.get("error") or "Audio daemon unavailable.")

    before_dev = _find_device(before_state, list_key, node_name)
    if before_dev is None:
        return _fail(f"Unknown {kind}: {node_name}")

    expected_mute = (
        not bool(before_dev.get("mute"))
        if mute_arg == "toggle"
        else (mute_arg == "1")
    )

    write_res = run_live_cmd(
        ["pactl", pactl_cmd, node_name, mute_arg],
        timeout=timeout,
        runner=runner,
    )
    if not write_res.ok:
        return _fail(
            write_res.err.strip() or f"pactl {pactl_cmd} failed (rc={write_res.rc})",
            before=before_dev,
        )

    after_state = get_audio_state(runner=runner, timeout=timeout)
    if not after_state.get("available"):
        return _fail(
            after_state.get("error") or "Audio daemon unavailable during readback.",
            before=before_dev,
        )

    after_dev = _find_device(after_state, list_key, node_name)
    if after_dev is None:
        return _fail(
            f"{kind.capitalize()} {node_name!r} vanished during readback.",
            before=before_dev,
        )

    if bool(after_dev.get("mute")) is not expected_mute:
        return _fail(
            f"Mute readback mismatch for {node_name}: expected {expected_mute}, got {after_dev.get('mute')}.",
            before=before_dev,
            after=after_dev,
        )

    return {"ok": True, "before": before_dev, "after": after_dev, "error": None}


def _set_default(
    *,
    kind: str,
    name: Any,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    try:
        node_name = _validate_node_name(name)
    except ValueError as exc:
        return _fail(str(exc))

    list_key = "outputs" if kind == "sink" else "inputs"
    default_key = "default_sink" if kind == "sink" else "default_source"
    pactl_cmd = "set-default-sink" if kind == "sink" else "set-default-source"

    before_state = get_audio_state(runner=runner, timeout=timeout)
    if not before_state.get("available"):
        return _fail(before_state.get("error") or "Audio daemon unavailable.")

    before_dev = _find_device(before_state, list_key, node_name)
    if before_dev is None:
        return _fail(f"Unknown {kind}: {node_name}")

    before_info = {default_key: before_state.get(default_key, ""), "device": before_dev}

    write_res = run_live_cmd(
        ["pactl", pactl_cmd, node_name],
        timeout=timeout,
        runner=runner,
    )
    if not write_res.ok:
        return _fail(
            write_res.err.strip() or f"pactl {pactl_cmd} failed (rc={write_res.rc})",
            before=before_info,
        )

    after_state = get_audio_state(runner=runner, timeout=timeout)
    if not after_state.get("available"):
        return _fail(
            after_state.get("error") or "Audio daemon unavailable during readback.",
            before=before_info,
        )

    after_dev = _find_device(after_state, list_key, node_name)
    if after_dev is None:
        return _fail(
            f"{kind.capitalize()} {node_name!r} vanished during readback.",
            before=before_info,
        )

    after_info = {default_key: after_state.get(default_key, ""), "device": after_dev}
    if after_state.get(default_key) != node_name or not after_dev.get("is_default"):
        return _fail(
            f"Default {kind} readback mismatch: expected {node_name!r}, got {after_state.get(default_key)!r}.",
            before=before_info,
            after=after_info,
        )

    return {"ok": True, "before": before_info, "after": after_info, "error": None}


def set_sink_volume(
    name: str,
    percent: Any,
    *,
    max_percent: int = DEFAULT_MAX_VOLUME,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    return _set_volume(
        kind="sink",
        name=name,
        percent=percent,
        max_percent=max_percent,
        runner=runner,
        timeout=timeout,
    )


def set_source_volume(
    name: str,
    percent: Any,
    *,
    max_percent: int = DEFAULT_MAX_VOLUME,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    return _set_volume(
        kind="source",
        name=name,
        percent=percent,
        max_percent=max_percent,
        runner=runner,
        timeout=timeout,
    )


def set_sink_mute(
    name: str,
    mode: Any,
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    return _set_mute(kind="sink", name=name, mode=mode, runner=runner, timeout=timeout)


def set_source_mute(
    name: str,
    mode: Any,
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    return _set_mute(kind="source", name=name, mode=mode, runner=runner, timeout=timeout)


def set_default_sink(
    name: str,
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    return _set_default(kind="sink", name=name, runner=runner, timeout=timeout)


def set_default_source(
    name: str,
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    return _set_default(kind="source", name=name, runner=runner, timeout=timeout)
