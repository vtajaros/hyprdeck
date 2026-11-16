"""Bluetooth state probing via BlueZ D-Bus GetManagedObjects, rfkill, and PipeWire default sink."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from backend.core.live_cmd import DEFAULT_LIVE_CMD_TIMEOUT_SECONDS, LiveRunner, run_live_cmd

_MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")
_BLUEZ_SINK_RE = re.compile(r"^bluez_output\.([0-9A-Fa-f]{2}(?:_[0-9A-Fa-f]{2}){5})\.")

_AUDIO_UUID_PREFIXES = (
    "00001108-",  # Headset
    "0000110a-",  # Audio Source
    "0000110b-",  # Audio Sink
    "0000110d-",  # Advanced Audio Distribution
    "0000111e-",  # Handsfree
)


def validate_mac(mac: Any) -> str:
    """Validate and normalize a Bluetooth MAC address to uppercase AA:BB:CC:DD:EE:FF."""
    if not isinstance(mac, str):
        raise ValueError(f"Bluetooth MAC must be a string, got {type(mac).__name__}.")
    norm = mac.strip().upper()
    if not _MAC_RE.match(norm):
        raise ValueError(f"Invalid Bluetooth MAC address: {mac!r}.")
    return norm


def mac_to_dbus_path(mac: str, adapter_path: str = "/org/bluez/hci0") -> str:
    """Convert a validated MAC address to a BlueZ D-Bus Device1 object path."""
    norm = validate_mac(mac)
    base = (adapter_path or "/org/bluez/hci0").rstrip("/")
    return f"{base}/dev_{norm.replace(':', '_')}"


def _unwrap_dbus_val(val: Any) -> Any:
    if isinstance(val, Mapping) and "type" in val and "data" in val:
        return val["data"]
    return val


def _is_audio_device(uuids: list[str], icon: str) -> bool:
    if (icon or "").lower().startswith("audio-"):
        return True
    for u in uuids:
        u_low = str(u).lower()
        if any(u_low.startswith(p) for p in _AUDIO_UUID_PREFIXES):
            return True
    return False


@dataclass(frozen=True, slots=True)
class BluetoothController:
    path: str
    address: str
    alias: str
    powered: bool
    power_state: str
    pairable: bool
    discoverable: bool
    discovering: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "address": self.address,
            "alias": self.alias,
            "powered": self.powered,
            "power_state": self.power_state,
            "pairable": self.pairable,
            "discoverable": self.discoverable,
            "discovering": self.discovering,
        }


@dataclass(frozen=True, slots=True)
class BluetoothDevice:
    path: str
    address: str
    name: str
    alias: str
    icon: str
    paired: bool
    bonded: bool
    trusted: bool
    blocked: bool
    connected: bool
    rssi: int | None
    is_audio: bool
    is_default_sink: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "address": self.address,
            "name": self.name,
            "alias": self.alias,
            "icon": self.icon,
            "paired": self.paired,
            "bonded": self.bonded,
            "trusted": self.trusted,
            "blocked": self.blocked,
            "connected": self.connected,
            "rssi": self.rssi,
            "is_audio": self.is_audio,
            "is_default_sink": self.is_default_sink,
        }


def parse_rfkill_json(raw: str) -> dict[str, Any]:
    """Parse `rfkill --json` output for bluetooth soft/hard block state."""
    if not raw or not raw.strip():
        return {"available": False, "soft_blocked": False, "hard_blocked": False}
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        return {"available": False, "soft_blocked": False, "hard_blocked": False}
    if not isinstance(doc, Mapping):
        return {"available": False, "soft_blocked": False, "hard_blocked": False}

    devs = doc.get("rfkilldevices")
    if not isinstance(devs, list):
        return {"available": False, "soft_blocked": False, "hard_blocked": False}

    bt_devs = [d for d in devs if isinstance(d, Mapping) and str(d.get("type", "")).lower() == "bluetooth"]
    if not bt_devs:
        return {"available": True, "soft_blocked": False, "hard_blocked": False}

    soft = any(str(d.get("soft", "")).lower() == "blocked" for d in bt_devs)
    hard = any(str(d.get("hard", "")).lower() == "blocked" for d in bt_devs)
    return {"available": True, "soft_blocked": soft, "hard_blocked": hard}


def _extract_mac_from_sink_name(sink_name: str) -> str:
    m = _BLUEZ_SINK_RE.match((sink_name or "").strip())
    if not m:
        return ""
    return m.group(1).replace("_", ":").upper()


def _get_default_bluez_sink_mac(
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> str:
    res = run_live_cmd(["pactl", "get-default-sink"], timeout=timeout, runner=runner)
    if not res.ok:
        return ""
    def_name = res.out.strip()
    mac = _extract_mac_from_sink_name(def_name)
    if mac:
        return mac

    # Fallback: check api.bluez5.address in `pactl --format=json list sinks`
    sinks_res = run_live_cmd(
        ["pactl", "--format=json", "list", "sinks"],
        timeout=timeout,
        runner=runner,
    )
    if sinks_res.ok and sinks_res.out.strip():
        try:
            sinks = json.loads(sinks_res.out)
            if isinstance(sinks, list):
                for s in sinks:
                    if isinstance(s, Mapping) and s.get("name") == def_name:
                        props = s.get("properties")
                        if isinstance(props, Mapping):
                            addr = str(props.get("api.bluez5.address") or "").strip().upper()
                            if _MAC_RE.match(addr):
                                return addr
        except json.JSONDecodeError:
            pass
    return ""


def parse_managed_objects_json(
    raw: str,
    *,
    default_sink_mac: str = "",
) -> tuple[BluetoothController | None, list[BluetoothDevice]]:
    """Parse `busctl --system --json=short call org.bluez / org.freedesktop.DBus.ObjectManager GetManagedObjects`."""
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON from busctl GetManagedObjects: {exc}") from exc

    if not isinstance(doc, Mapping) or not isinstance(doc.get("data"), list) or not doc["data"]:
        raise ValueError("Unexpected GetManagedObjects JSON shape: missing 'data' list.")

    objects = doc["data"][0]
    if not isinstance(objects, Mapping):
        raise ValueError("Unexpected GetManagedObjects JSON shape: data[0] must be a mapping.")

    controller: BluetoothController | None = None
    devices: list[BluetoothDevice] = []
    norm_def_mac = default_sink_mac.strip().upper() if default_sink_mac else ""

    for path in sorted(objects.keys()):
        ifaces = objects[path]
        if not isinstance(ifaces, Mapping):
            continue

        if "org.bluez.Adapter1" in ifaces and isinstance(ifaces["org.bluez.Adapter1"], Mapping):
            ad = ifaces["org.bluez.Adapter1"]
            ctrl = BluetoothController(
                path=str(path),
                address=str(_unwrap_dbus_val(ad.get("Address")) or "").upper(),
                alias=str(_unwrap_dbus_val(ad.get("Alias")) or _unwrap_dbus_val(ad.get("Name")) or ""),
                powered=bool(_unwrap_dbus_val(ad.get("Powered")) or False),
                power_state=str(_unwrap_dbus_val(ad.get("PowerState")) or "off"),
                pairable=bool(_unwrap_dbus_val(ad.get("Pairable")) or False),
                discoverable=bool(_unwrap_dbus_val(ad.get("Discoverable")) or False),
                discovering=bool(_unwrap_dbus_val(ad.get("Discovering")) or False),
            )
            if controller is None or path == "/org/bluez/hci0":
                controller = ctrl

        if "org.bluez.Device1" in ifaces and isinstance(ifaces["org.bluez.Device1"], Mapping):
            dv = ifaces["org.bluez.Device1"]
            addr = str(_unwrap_dbus_val(dv.get("Address")) or "").strip().upper()
            if not _MAC_RE.match(addr):
                continue
            name = str(_unwrap_dbus_val(dv.get("Name")) or "")
            alias = str(_unwrap_dbus_val(dv.get("Alias")) or name or addr)
            icon = str(_unwrap_dbus_val(dv.get("Icon")) or "")
            uuids_raw = _unwrap_dbus_val(dv.get("UUIDs"))
            uuids = [str(u) for u in uuids_raw] if isinstance(uuids_raw, list) else []
            rssi_raw = _unwrap_dbus_val(dv.get("RSSI"))
            rssi = int(rssi_raw) if isinstance(rssi_raw, int) and not isinstance(rssi_raw, bool) else None
            is_audio = _is_audio_device(uuids, icon)
            devices.append(
                BluetoothDevice(
                    path=str(path),
                    address=addr,
                    name=name or alias,
                    alias=alias,
                    icon=icon,
                    paired=bool(_unwrap_dbus_val(dv.get("Paired")) or False),
                    bonded=bool(_unwrap_dbus_val(dv.get("Bonded")) or False),
                    trusted=bool(_unwrap_dbus_val(dv.get("Trusted")) or False),
                    blocked=bool(_unwrap_dbus_val(dv.get("Blocked")) or False),
                    connected=bool(_unwrap_dbus_val(dv.get("Connected")) or False),
                    rssi=rssi,
                    is_audio=is_audio,
                    is_default_sink=bool(norm_def_mac and addr == norm_def_mac),
                )
            )

    return controller, devices


def compute_safety_flags(
    controller: BluetoothController | None,
    devices: list[BluetoothDevice],
) -> dict[str, Any]:
    """Compute disruptive-action safety flags for the Bluetooth state payload."""
    connected = [d for d in devices if d.connected]
    default_audio = next((d for d in connected if d.is_default_sink), None)
    return {
        "disconnecting_default_audio": default_audio is not None,
        "default_audio_mac": default_audio.address if default_audio else "",
        "default_audio_name": default_audio.alias if default_audio else "",
        "powering_off_disconnects": bool(controller and controller.powered and len(connected) > 0),
        "connected_count": len(connected),
        "connected_names": [d.alias for d in connected],
    }


def get_bluetooth_state(
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Probe live BlueZ state, rfkill status, and default PipeWire Bluetooth sink match."""
    rf_res = run_live_cmd(["rfkill", "--json"], timeout=timeout, runner=runner)
    rfkill = parse_rfkill_json(rf_res.out) if rf_res.ok else {
        "available": False,
        "soft_blocked": False,
        "hard_blocked": False,
    }

    dbus_res = run_live_cmd(
        [
            "busctl",
            "--system",
            "--json=short",
            "call",
            "org.bluez",
            "/",
            "org.freedesktop.DBus.ObjectManager",
            "GetManagedObjects",
        ],
        timeout=timeout,
        runner=runner,
    )
    if not dbus_res.ok:
        err = dbus_res.err.strip() or f"busctl GetManagedObjects failed (rc={dbus_res.rc})"
        return {
            "available": False,
            "no_controller": False,
            "controller": None,
            "rfkill": rfkill,
            "devices": [],
            "default_sink_mac": "",
            "safety": compute_safety_flags(None, []),
            "error": err,
        }

    default_sink_mac = _get_default_bluez_sink_mac(runner=runner, timeout=timeout)

    try:
        controller, devices = parse_managed_objects_json(
            dbus_res.out,
            default_sink_mac=default_sink_mac,
        )
    except ValueError as exc:
        return {
            "available": False,
            "no_controller": False,
            "controller": None,
            "rfkill": rfkill,
            "devices": [],
            "default_sink_mac": default_sink_mac,
            "safety": compute_safety_flags(None, []),
            "error": str(exc),
        }

    if controller is None:
        return {
            "available": False,
            "no_controller": True,
            "controller": None,
            "rfkill": rfkill,
            "devices": [d.to_dict() for d in devices],
            "default_sink_mac": default_sink_mac,
            "safety": compute_safety_flags(None, devices),
            "error": "No Bluetooth controller found.",
        }

    return {
        "available": True,
        "no_controller": False,
        "controller": controller.to_dict(),
        "rfkill": rfkill,
        "devices": [d.to_dict() for d in devices],
        "default_sink_mac": default_sink_mac,
        "safety": compute_safety_flags(controller, devices),
        "error": None,
    }
