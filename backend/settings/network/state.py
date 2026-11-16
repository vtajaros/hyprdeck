"""NetworkManager state probing via `nmcli -t` (with LC_ALL=C and proper escaping)."""

from __future__ import annotations

import ipaddress
import os
import re
from typing import Any

from backend.core.live_cmd import DEFAULT_LIVE_CMD_TIMEOUT_SECONDS, LiveRunner, run_live_cmd

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_IFACE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_HIDDEN_DEVICE_TYPES = frozenset({"loopback", "wifi-p2p"})


def nmcli_env() -> dict[str, str]:
    """Return environment dict with LC_ALL=C for deterministic nmcli parsing."""
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    return env


def split_nmcli_terse_line(line: str) -> list[str]:
    """Split a single `nmcli -t` line on unescaped ':', unescaping '\\:' and '\\\\'."""
    fields: list[str] = []
    buf: list[str] = []
    escaped = False
    for ch in line:
        if escaped:
            buf.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == ":":
            fields.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if escaped:
        buf.append("\\")
    fields.append("".join(buf))
    return fields


def validate_uuid(uuid: Any) -> str:
    """Validate and normalize a NetworkManager connection UUID."""
    if not isinstance(uuid, str):
        raise ValueError(f"UUID must be a string, got {type(uuid).__name__}.")
    norm = uuid.strip().lower()
    if not _UUID_RE.match(norm):
        raise ValueError(f"Invalid connection UUID: {uuid!r}.")
    return norm


def validate_iface_name(name: Any) -> str:
    """Validate a network interface name (no slashes, spaces, or control chars)."""
    if not isinstance(name, str) or not _IFACE_RE.match(name.strip()):
        raise ValueError(f"Invalid network device name: {name!r}.")
    return name.strip()


def validate_ip_list(servers: Any) -> list[str]:
    """Validate DNS server IPs or 'auto' (returns [] for 'auto')."""
    if servers is None:
        return []
    if isinstance(servers, str):
        s = servers.strip()
        if not s or s.lower() == "auto":
            return []
        raw_items = [p.strip() for p in re.split(r"[\s,]+", s) if p.strip()]
    elif isinstance(servers, (list, tuple)):
        raw_items = [str(p).strip() for p in servers if str(p).strip()]
    else:
        raise ValueError(f"DNS servers must be 'auto', a string, or a list, got {type(servers).__name__}.")

    if len(raw_items) == 1 and raw_items[0].lower() == "auto":
        return []

    validated: list[str] = []
    for item in raw_items:
        try:
            validated.append(str(ipaddress.ip_address(item)))
        except ValueError as exc:
            raise ValueError(f"Invalid DNS IP address: {item!r}.") from exc
    return validated


def parse_general_status(raw: str) -> dict[str, Any]:
    """Parse `nmcli -t -f STATE,CONNECTIVITY,WIFI-HW,WIFI,WWAN-HW,WWAN,NETWORKING general status`."""
    lines = [ln for ln in (raw or "").splitlines() if ln.strip()]
    if not lines:
        raise ValueError("Empty output from nmcli general status.")
    parts = split_nmcli_terse_line(lines[0])
    if len(parts) < 7:
        raise ValueError(f"Malformed nmcli general status line (expected 7 fields, got {len(parts)}).")
    return {
        "state": parts[0],
        "connectivity": parts[1],
        "wifi_hw_enabled": parts[2] == "enabled",
        "wifi_enabled": parts[3] == "enabled",
        "wwan_present": parts[4] != "missing",
        "wwan_enabled": parts[5] == "enabled",
        "networking_enabled": parts[6] == "enabled",
    }


def parse_device_list(raw: str) -> list[dict[str, Any]]:
    """Parse `nmcli -t -f DEVICE,TYPE,STATE,CONNECTION,CON-UUID device`."""
    devices: list[dict[str, Any]] = []
    for line in (raw or "").splitlines():
        if not line.strip():
            continue
        parts = split_nmcli_terse_line(line)
        if len(parts) < 5:
            continue
        name, dev_type, state, conn_name, conn_uuid = parts[0], parts[1], parts[2], parts[3], parts[4]
        is_active = state.startswith("connected")
        devices.append(
            {
                "name": name,
                "type": dev_type,
                "state": state,
                "active_connection": conn_name,
                "active_uuid": conn_uuid.lower() if conn_uuid else "",
                "ip4_address": "",
                "ip4_gateway": "",
                "ip4_dns": [],
                "mac": "",
                "is_active": is_active,
            }
        )
    return devices


def parse_device_show(raw: str) -> dict[str, dict[str, Any]]:
    """Parse `nmcli -t -f ... device show` stanzas keyed by device name."""
    details: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] = {}

    def _flush() -> None:
        dev_name = str(current.get("GENERAL.DEVICE") or "").strip()
        if not dev_name:
            return
        entry: dict[str, Any] = {
            "ip4_address": str(current.get("IP4.ADDRESS[1]") or current.get("IP4.ADDRESS") or ""),
            "ip4_gateway": str(current.get("IP4.GATEWAY") or ""),
            "ip4_dns": list(current.get("_dns", [])),
            "mac": str(current.get("GENERAL.HWADDR") or ""),
        }
        mtu_raw = str(current.get("GENERAL.MTU") or "").strip()
        if mtu_raw.isdigit():
            entry["mtu"] = int(mtu_raw)
        details[dev_name] = entry

    for line in (raw or "").splitlines():
        if not line.strip():
            _flush()
            current = {}
            continue
        parts = split_nmcli_terse_line(line)
        if len(parts) < 2:
            continue
        key = parts[0].strip()
        val = ":".join(parts[1:]).strip() if len(parts) > 2 else parts[1].strip()
        if key.startswith("IP4.DNS"):
            if val:
                current.setdefault("_dns", []).append(val)
        else:
            current[key] = val
    _flush()
    return details


def parse_connections(raw: str) -> list[dict[str, Any]]:
    """Parse `nmcli -t -f UUID,NAME,TYPE,AUTOCONNECT,DEVICE,ACTIVE connection show`."""
    conns: list[dict[str, Any]] = []
    for line in (raw or "").splitlines():
        if not line.strip():
            continue
        parts = split_nmcli_terse_line(line)
        if len(parts) < 6:
            continue
        uuid, name, ctype, autoconn, device, active = parts[:6]
        conns.append(
            {
                "uuid": uuid.strip().lower(),
                "name": name,
                "type": ctype,
                "autoconnect": autoconn.strip().lower() == "yes",
                "metered": "unknown",
                "device": device,
                "active": active.strip().lower() == "yes",
            }
        )
    return conns


def parse_wifi_list(raw: str, known_wifi_names: set[str]) -> list[dict[str, Any]]:
    """Parse `nmcli -t -f SSID,SIGNAL,SECURITY,IN-USE device wifi list`, deduping by SSID."""
    by_ssid: dict[str, dict[str, Any]] = {}
    hidden_count = 0

    for line in (raw or "").splitlines():
        if not line.strip():
            continue
        parts = split_nmcli_terse_line(line)
        if len(parts) < 4:
            continue
        ssid_raw, sig_raw, sec, in_use_raw = parts[0], parts[1], parts[2], parts[3]
        try:
            signal = max(0, min(100, int(sig_raw.strip())))
        except ValueError:
            signal = 0
        in_use = in_use_raw.strip() == "*"
        is_hidden = (ssid_raw == "" or ssid_raw == "--")
        if is_hidden:
            hidden_count += 1
            key = f"__hidden_{hidden_count}"
            ssid = ""
        else:
            key = ssid_raw
            ssid = ssid_raw

        entry = {
            "ssid": ssid,
            "hidden": is_hidden,
            "signal": signal,
            "security": sec.strip(),
            "in_use": in_use,
            "known": (not is_hidden) and (ssid in known_wifi_names),
        }
        existing = by_ssid.get(key)
        if existing is None:
            by_ssid[key] = entry
        else:
            if signal > existing["signal"]:
                existing["signal"] = signal
                existing["security"] = entry["security"]
            if in_use:
                existing["in_use"] = True

    return sorted(by_ssid.values(), key=lambda x: (not x["in_use"], -x["signal"], x["ssid"]))


def compute_network_safety(
    devices: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    general: dict[str, Any],
) -> dict[str, Any]:
    """Compute `would_cut_current_session` and `is_active` flags for connections and devices."""
    hidden_names = {d["name"] for d in devices if d.get("type") in _HIDDEN_DEVICE_TYPES}
    active_non_lo_conns = [
        c for c in connections
        if c.get("active") and c.get("type") != "loopback" and c.get("device") not in hidden_names
    ]
    active_count = len(active_non_lo_conns)
    has_conn = general.get("connectivity") in ("full", "limited", "portal") or active_count > 0

    for c in connections:
        is_act = bool(c.get("active"))
        c["is_active"] = is_act
        c["would_cut_current_session"] = bool(is_act and has_conn and active_count <= 1)

    for d in devices:
        is_act = bool(d.get("is_active"))
        d["would_cut_current_session"] = bool(
            is_act and d.get("type") not in _HIDDEN_DEVICE_TYPES and has_conn and active_count <= 1
        )

    non_wifi_active = [c for c in active_non_lo_conns if c.get("type") != "802-11-wireless"]
    wifi_off_cuts = bool(
        general.get("wifi_enabled")
        and len(active_non_lo_conns) > 0
        and len(non_wifi_active) == 0
    )

    return {
        "active_connection_count": active_count,
        "wifi_off_would_cut_session": wifi_off_cuts,
    }


def _unavailable_state(error: str) -> dict[str, Any]:
    return {
        "available": False,
        "general": {
            "state": "unknown",
            "connectivity": "none",
            "wifi_hw_enabled": False,
            "wifi_enabled": False,
            "wwan_present": False,
            "wwan_enabled": False,
            "networking_enabled": False,
        },
        "has_wifi_device": False,
        "devices": [],
        "debug_devices": [],
        "connections": [],
        "wifi_networks": [],
        "safety": {
            "active_connection_count": 0,
            "wifi_off_would_cut_session": False,
        },
        "error": error,
    }


def get_network_state(
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Probe live NetworkManager state via `nmcli -t` commands."""
    env = nmcli_env()

    gen_res = run_live_cmd(
        ["nmcli", "-t", "-f", "STATE,CONNECTIVITY,WIFI-HW,WIFI,WWAN-HW,WWAN,NETWORKING", "general", "status"],
        timeout=timeout,
        runner=runner,
        env=env,
    )
    if not gen_res.ok:
        return _unavailable_state(gen_res.err.strip() or f"nmcli general status failed (rc={gen_res.rc})")

    try:
        general = parse_general_status(gen_res.out)
    except ValueError as exc:
        return _unavailable_state(str(exc))

    dev_res = run_live_cmd(
        ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION,CON-UUID", "device"],
        timeout=timeout,
        runner=runner,
        env=env,
    )
    if not dev_res.ok:
        return _unavailable_state(dev_res.err.strip() or f"nmcli device failed (rc={dev_res.rc})")

    all_devices = parse_device_list(dev_res.out)

    show_res = run_live_cmd(
        [
            "nmcli", "-t", "-f",
            "GENERAL.DEVICE,GENERAL.TYPE,GENERAL.STATE,GENERAL.HWADDR,GENERAL.MTU,GENERAL.CONNECTION,GENERAL.CON-UUID,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS",
            "device", "show",
        ],
        timeout=timeout,
        runner=runner,
        env=env,
    )
    if show_res.ok and show_res.out.strip():
        details = parse_device_show(show_res.out)
        for d in all_devices:
            if d["name"] in details:
                d.update(details[d["name"]])

    conn_res = run_live_cmd(
        ["nmcli", "-t", "-f", "UUID,NAME,TYPE,AUTOCONNECT,DEVICE,ACTIVE", "connection", "show"],
        timeout=timeout,
        runner=runner,
        env=env,
    )
    if not conn_res.ok:
        return _unavailable_state(conn_res.err.strip() or f"nmcli connection show failed (rc={conn_res.rc})")

    connections = parse_connections(conn_res.out)
    safety = compute_network_safety(all_devices, connections, general)

    main_devices = [
        d for d in all_devices
        if d.get("type") not in _HIDDEN_DEVICE_TYPES
        and d.get("name") != "lo"
        and not str(d.get("name", "")).startswith("p2p-dev-")
    ]
    debug_devices = [
        d for d in all_devices
        if d.get("type") in _HIDDEN_DEVICE_TYPES
        or d.get("name") == "lo"
        or str(d.get("name", "")).startswith("p2p-dev-")
    ]

    has_wifi_dev = any(d.get("type") == "wifi" for d in main_devices)
    wifi_networks: list[dict[str, Any]] = []
    if has_wifi_dev and general.get("wifi_enabled") and general.get("wifi_hw_enabled"):
        wifi_res = run_live_cmd(
            ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE", "device", "wifi", "list"],
            timeout=timeout,
            runner=runner,
            env=env,
        )
        if wifi_res.ok:
            known_names = {c["name"] for c in connections if c.get("type") == "802-11-wireless"}
            wifi_networks = parse_wifi_list(wifi_res.out, known_names)

    return {
        "available": True,
        "general": general,
        "has_wifi_device": has_wifi_dev,
        "devices": main_devices,
        "debug_devices": debug_devices,
        "connections": connections,
        "wifi_networks": wifi_networks,
        "safety": safety,
        "error": None,
    }
