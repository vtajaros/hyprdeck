"""Parser package for HyprDeck."""

from backend.parser.hyprlang_parser import (
    expand_variables,
    parse_hyprlang_config,
    strip_hyprlang_comment,
)
from backend.parser.lua_normalizer import (
    compute_bind_id,
    compute_stats,
    normalize_lua_output,
    parse_lua_config,
    summarize_dispatcher_args,
)
from backend.parser.lua_runner import RawRecorderOutput, run_lua_recorder
from backend.parser.modifiers import (
    MODIFIER_ALIASES,
    MODIFIER_BITS,
    classify_key_kind,
    derive_bind_type_from_flags,
    resolve_modifier_tokens,
)

__all__ = [
    "MODIFIER_ALIASES",
    "MODIFIER_BITS",
    "RawRecorderOutput",
    "classify_key_kind",
    "compute_bind_id",
    "compute_stats",
    "derive_bind_type_from_flags",
    "expand_variables",
    "normalize_lua_output",
    "parse_hyprlang_config",
    "parse_lua_config",
    "resolve_modifier_tokens",
    "run_lua_recorder",
    "strip_hyprlang_comment",
    "summarize_dispatcher_args",
]
