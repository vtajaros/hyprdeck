#!/usr/bin/env bash
# Shared environment variable helpers for HyprDeck shell scripts.
# Resolution order: HYPRDECK_<SUFFIX> > HKS_<SUFFIX> > default.

hyprdeck_env_get() {
    local suffix="$1"
    local def="${2:-}"
    local new_name="HYPRDECK_${suffix}"
    local old_name="HKS_${suffix}"
    if [ -n "${!new_name:-}" ]; then
        printf '%s' "${!new_name}"
    elif [ -n "${!old_name:-}" ]; then
        printf '%s' "${!old_name}"
    else
        printf '%s' "$def"
    fi
}

hyprdeck_env_export_pair() {
    local suffix="$1"
    local val="$2"
    export "HYPRDECK_${suffix}=$val"
    export "HKS_${suffix}=$val"
}

hyprdeck_env_unset_pair() {
    local suffix="$1"
    unset "HYPRDECK_${suffix}" "HKS_${suffix}"
}
