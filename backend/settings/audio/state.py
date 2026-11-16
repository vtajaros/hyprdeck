"""Audio device and playback stream state probing via pactl JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from backend.core.live_cmd import DEFAULT_LIVE_CMD_TIMEOUT_SECONDS, LiveRunner, run_live_cmd


class AudioStateError(RuntimeError):
    """Raised when pactl JSON output cannot be parsed."""


@dataclass(frozen=True, slots=True)
class AudioDevice:
    """Normalized audio sink (output) or source (input)."""

    name: str
    description: str
    kind: str  # "bluez" | "alsa" | "hdmi" | "other"
    is_default: bool
    mute: bool
    volume_percent: int
    balance_diff: int
    running_state: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "kind": self.kind,
            "is_default": self.is_default,
            "mute": self.mute,
            "volume_percent": self.volume_percent,
            "balance_diff": self.balance_diff,
            "running_state": self.running_state,
        }


@dataclass(frozen=True, slots=True)
class AudioStream:
    """Read-only playback stream (pactl sink-input)."""

    index: int
    name: str
    app: str
    sink: str
    volume: int
    mute: bool
    balance_diff: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "app": self.app,
            "sink": self.sink,
            "volume": self.volume,
            "mute": self.mute,
            "balance_diff": self.balance_diff,
        }


def classify_device_kind(
    name: str,
    description: str = "",
    properties: Mapping[str, Any] | None = None,
) -> str:
    """Classify an audio node into 'bluez', 'hdmi', 'alsa', or 'other'."""
    props = properties if isinstance(properties, Mapping) else {}
    n_low = (name or "").lower()
    d_low = (description or "").lower()
    api = str(props.get("device.api") or "").lower()
    alsa_name = str(props.get("alsa.name") or "").lower()
    profile_name = str(props.get("device.profile.name") or "").lower()

    if api == "bluez5" or n_low.startswith("bluez_"):
        return "bluez"
    if (
        "hdmi" in n_low
        or "hdmi" in d_low
        or "hdmi" in alsa_name
        or "hdmi" in profile_name
    ):
        return "hdmi"
    if api == "alsa" or n_low.startswith("alsa_"):
        return "alsa"
    return "other"


def parse_channel_volumes(volume_obj: Any) -> tuple[int, int]:
    """Return (average_volume_percent, balance_diff) from pactl channel volume map."""
    if not isinstance(volume_obj, Mapping):
        return 0, 0

    percents: list[int] = []
    for ch_val in volume_obj.values():
        if not isinstance(ch_val, Mapping):
            continue
        pct_raw = ch_val.get("value_percent")
        if pct_raw is not None:
            s = str(pct_raw).strip().rstrip("%").strip()
            try:
                percents.append(int(round(float(s))))
                continue
            except ValueError:
                pass
        raw_val = ch_val.get("value")
        if raw_val is not None and not isinstance(raw_val, bool):
            try:
                percents.append(int(round((float(raw_val) / 65536.0) * 100.0)))
            except (TypeError, ValueError):
                pass

    if not percents:
        return 0, 0
    avg = int(round(sum(percents) / len(percents)))
    diff = max(percents) - min(percents)
    return avg, diff


def _parse_json_list(raw: str, label: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AudioStateError(f"Malformed JSON from pactl {label}: {exc}") from exc
    if not isinstance(data, list):
        raise AudioStateError(f"Expected JSON list from pactl {label}, got {type(data).__name__}.")
    return [item for item in data if isinstance(item, Mapping)]


def _build_device(item: Mapping[str, Any], default_name: str) -> AudioDevice | None:
    name = str(item.get("name") or "").strip()
    if not name:
        return None
    props = item.get("properties")
    props_map = props if isinstance(props, Mapping) else {}
    description = str(item.get("description") or props_map.get("node.description") or name)
    kind = classify_device_kind(name, description, props_map)
    vol_pct, bal_diff = parse_channel_volumes(item.get("volume"))
    running_state = str(item.get("state") or "UNKNOWN").upper()
    return AudioDevice(
        name=name,
        description=description,
        kind=kind,
        is_default=(name == default_name),
        mute=bool(item.get("mute", False)),
        volume_percent=vol_pct,
        balance_diff=bal_diff,
        running_state=running_state,
    )


def parse_sinks_json(
    raw: str,
    default_sink: str = "",
) -> tuple[list[AudioDevice], dict[int, str]]:
    """Parse `pactl --format=json list sinks` into AudioDevices and an index->name map."""
    items = _parse_json_list(raw, "list sinks")
    devices: list[AudioDevice] = []
    index_map: dict[int, str] = {}
    for item in items:
        dev = _build_device(item, default_sink)
        if dev is None:
            continue
        devices.append(dev)
        idx = item.get("index")
        if isinstance(idx, int) and not isinstance(idx, bool):
            index_map[idx] = dev.name
    return devices, index_map


def parse_sources_json(raw: str, default_source: str = "") -> list[AudioDevice]:
    """Parse `pactl --format=json list sources`, excluding `.monitor` sources."""
    items = _parse_json_list(raw, "list sources")
    devices: list[AudioDevice] = []
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name or name.endswith(".monitor"):
            continue
        dev = _build_device(item, default_source)
        if dev is not None:
            devices.append(dev)
    return devices


def parse_sink_inputs_json(
    raw: str,
    sink_index_map: Mapping[int, str] | None = None,
) -> list[AudioStream]:
    """Parse `pactl --format=json list sink-inputs` into read-only AudioStreams."""
    items = _parse_json_list(raw, "list sink-inputs")
    idx_map = sink_index_map or {}
    streams: list[AudioStream] = []
    for item in items:
        idx_raw = item.get("index", -1)
        idx = idx_raw if isinstance(idx_raw, int) and not isinstance(idx_raw, bool) else -1
        props = item.get("properties")
        props_map = props if isinstance(props, Mapping) else {}
        media_name = str(props_map.get("media.name") or item.get("name") or "")
        app_name = str(props_map.get("application.name") or props_map.get("node.name") or "")
        sink_raw = item.get("sink")
        if isinstance(sink_raw, int) and not isinstance(sink_raw, bool):
            sink_name = idx_map.get(sink_raw, str(sink_raw))
        elif sink_raw is not None:
            sink_name = str(sink_raw)
        else:
            sink_name = ""
        vol_pct, bal_diff = parse_channel_volumes(item.get("volume"))
        streams.append(
            AudioStream(
                index=idx,
                name=media_name,
                app=app_name,
                sink=sink_name,
                volume=vol_pct,
                mute=bool(item.get("mute", False)),
                balance_diff=bal_diff,
            )
        )
    return streams


def _empty_unavailable(error: str) -> dict[str, Any]:
    return {
        "available": False,
        "default_sink": "",
        "default_source": "",
        "outputs": [],
        "inputs": [],
        "streams": [],
        "error": error,
    }


def get_audio_state(
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Probe live PipeWire/PulseAudio state via pactl JSON commands."""
    sinks_res = run_live_cmd(
        ["pactl", "--format=json", "list", "sinks"],
        timeout=timeout,
        runner=runner,
    )
    if not sinks_res.ok:
        msg = sinks_res.err.strip() or f"pactl list sinks failed (rc={sinks_res.rc})"
        return _empty_unavailable(msg)

    sources_res = run_live_cmd(
        ["pactl", "--format=json", "list", "sources"],
        timeout=timeout,
        runner=runner,
    )
    if not sources_res.ok:
        msg = sources_res.err.strip() or f"pactl list sources failed (rc={sources_res.rc})"
        return _empty_unavailable(msg)

    def_sink_res = run_live_cmd(
        ["pactl", "get-default-sink"],
        timeout=timeout,
        runner=runner,
    )
    default_sink = def_sink_res.out.strip() if def_sink_res.ok else ""

    def_src_res = run_live_cmd(
        ["pactl", "get-default-source"],
        timeout=timeout,
        runner=runner,
    )
    default_source = def_src_res.out.strip() if def_src_res.ok else ""

    try:
        outputs, sink_index_map = parse_sinks_json(sinks_res.out, default_sink=default_sink)
        inputs = parse_sources_json(sources_res.out, default_source=default_source)
    except AudioStateError as exc:
        return _empty_unavailable(str(exc))

    streams: list[AudioStream] = []
    inputs_res = run_live_cmd(
        ["pactl", "--format=json", "list", "sink-inputs"],
        timeout=timeout,
        runner=runner,
    )
    if inputs_res.ok and inputs_res.out.strip():
        try:
            streams = parse_sink_inputs_json(inputs_res.out, sink_index_map=sink_index_map)
        except AudioStateError:
            streams = []

    return {
        "available": True,
        "default_sink": default_sink,
        "default_source": default_source,
        "outputs": [d.to_dict() for d in outputs],
        "inputs": [d.to_dict() for d in inputs],
        "streams": [s.to_dict() for s in streams],
        "error": None,
    }
