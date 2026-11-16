"""Audio state and live control operations via pactl."""

from backend.settings.audio.ops import (
    DEFAULT_MAX_VOLUME,
    HARD_MAX_VOLUME,
    normalize_mute_mode,
    set_default_sink,
    set_default_source,
    set_sink_mute,
    set_sink_volume,
    set_source_mute,
    set_source_volume,
    validate_and_clamp_volume,
)
from backend.settings.audio.state import (
    AudioDevice,
    AudioStateError,
    AudioStream,
    classify_device_kind,
    get_audio_state,
    parse_channel_volumes,
    parse_sink_inputs_json,
    parse_sinks_json,
    parse_sources_json,
)

__all__ = [
    "AudioDevice",
    "AudioStateError",
    "AudioStream",
    "DEFAULT_MAX_VOLUME",
    "HARD_MAX_VOLUME",
    "classify_device_kind",
    "get_audio_state",
    "normalize_mute_mode",
    "parse_channel_volumes",
    "parse_sink_inputs_json",
    "parse_sinks_json",
    "parse_sources_json",
    "set_default_sink",
    "set_default_source",
    "set_sink_mute",
    "set_sink_volume",
    "set_source_mute",
    "set_source_volume",
    "validate_and_clamp_volume",
]
