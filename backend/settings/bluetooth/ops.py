"""Bluetooth controller & device operations via busctl / rfkill / one-shot bluetoothctl."""

from __future__ import annotations

import time
from typing import Any, Callable

from backend.core.live_cmd import DEFAULT_LIVE_CMD_TIMEOUT_SECONDS, LiveRunner, run_live_cmd
from backend.settings.bluetooth.state import (
    get_bluetooth_state,
    mac_to_dbus_path,
    validate_mac,
)

MAX_DISCOVERABLE_TIMEOUT = 300
MIN_SCAN_SECONDS = 1.0
MAX_SCAN_SECONDS = 30.0
MIN_PAIR_TIMEOUT = 5
MAX_PAIR_TIMEOUT = 60

_MANUAL_PAIR_HINTS = (
    "passkey",
    "confirm",
    "pin",
    "authentication",
    "authorization",
    "agent",
    "rejected",
)


def _fail(error: str, before: Any = None, after: Any = None, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "before": before, "after": after, "error": error}
    out.update(extra)
    return out


def _find_device(state: dict[str, Any], mac: str) -> dict[str, Any] | None:
    for dev in state.get("devices", []):
        if isinstance(dev, dict) and dev.get("address") == mac:
            return dev
    return None


def _busctl_set_prop(
    path: str,
    iface: str,
    prop: str,
    sig: str,
    val: str,
    *,
    runner: LiveRunner | None,
    timeout: float,
):
    return run_live_cmd(
        ["busctl", "--system", "set-property", "org.bluez", path, iface, prop, sig, val],
        timeout=timeout,
        runner=runner,
    )


def _busctl_call(
    path: str,
    iface: str,
    method: str,
    *args: str,
    runner: LiveRunner | None,
    timeout: float,
):
    return run_live_cmd(
        ["busctl", "--system", "call", "org.bluez", path, iface, method, *args],
        timeout=timeout,
        runner=runner,
    )


def set_powered(
    enabled: bool,
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not isinstance(enabled, bool):
        return _fail(f"enabled must be bool, got {enabled!r}.")

    before_state = get_bluetooth_state(runner=runner, timeout=timeout)
    if not before_state.get("available") or not before_state.get("controller"):
        return _fail(before_state.get("error") or "Bluetooth controller unavailable.")

    before_ctrl = before_state["controller"]
    adapter_path = str(before_ctrl.get("path") or "/org/bluez/hci0")
    rf = before_state.get("rfkill") or {}

    if enabled:
        if rf.get("hard_blocked"):
            return _fail("Bluetooth is hardware-blocked (rfkill hard block).", before=before_ctrl)
        if rf.get("soft_blocked"):
            unblock_res = run_live_cmd(["rfkill", "unblock", "bluetooth"], timeout=timeout, runner=runner)
            if not unblock_res.ok:
                return _fail(
                    unblock_res.err.strip() or f"rfkill unblock failed (rc={unblock_res.rc})",
                    before=before_ctrl,
                )

    write_res = _busctl_set_prop(
        adapter_path,
        "org.bluez.Adapter1",
        "Powered",
        "b",
        "true" if enabled else "false",
        runner=runner,
        timeout=timeout,
    )
    if not write_res.ok:
        return _fail(
            write_res.err.strip() or f"Failed to set Powered (rc={write_res.rc})",
            before=before_ctrl,
        )

    after_state = get_bluetooth_state(runner=runner, timeout=timeout)
    if not after_state.get("available") or not after_state.get("controller"):
        return _fail(after_state.get("error") or "Controller unavailable during readback.", before=before_ctrl)

    after_ctrl = after_state["controller"]
    if bool(after_ctrl.get("powered")) is not enabled:
        return _fail(
            f"Powered readback mismatch: expected {enabled}, got {after_ctrl.get('powered')}.",
            before=before_ctrl,
            after=after_ctrl,
        )
    if enabled and (after_state.get("rfkill") or {}).get("soft_blocked"):
        return _fail(
            "Bluetooth remains rfkill soft-blocked after unblock.",
            before=before_ctrl,
            after=after_ctrl,
        )
    return {"ok": True, "before": before_ctrl, "after": after_ctrl, "error": None}


def set_pairable(
    enabled: bool,
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not isinstance(enabled, bool):
        return _fail(f"enabled must be bool, got {enabled!r}.")

    before_state = get_bluetooth_state(runner=runner, timeout=timeout)
    if not before_state.get("available") or not before_state.get("controller"):
        return _fail(before_state.get("error") or "Bluetooth controller unavailable.")

    before_ctrl = before_state["controller"]
    adapter_path = str(before_ctrl.get("path") or "/org/bluez/hci0")
    write_res = _busctl_set_prop(
        adapter_path,
        "org.bluez.Adapter1",
        "Pairable",
        "b",
        "true" if enabled else "false",
        runner=runner,
        timeout=timeout,
    )
    if not write_res.ok:
        return _fail(write_res.err.strip() or f"Failed to set Pairable (rc={write_res.rc})", before=before_ctrl)

    after_state = get_bluetooth_state(runner=runner, timeout=timeout)
    if not after_state.get("available") or not after_state.get("controller"):
        return _fail(after_state.get("error") or "Controller unavailable during readback.", before=before_ctrl)

    after_ctrl = after_state["controller"]
    if bool(after_ctrl.get("pairable")) is not enabled:
        return _fail(
            f"Pairable readback mismatch: expected {enabled}, got {after_ctrl.get('pairable')}.",
            before=before_ctrl,
            after=after_ctrl,
        )
    return {"ok": True, "before": before_ctrl, "after": after_ctrl, "error": None}


def set_discoverable(
    enabled: bool,
    *,
    discoverable_timeout: int = 180,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not isinstance(enabled, bool):
        return _fail(f"enabled must be bool, got {enabled!r}.")
    if isinstance(discoverable_timeout, bool) or not isinstance(discoverable_timeout, int):
        return _fail(f"discoverable_timeout must be an int, got {discoverable_timeout!r}.")
    capped_to = max(0, min(MAX_DISCOVERABLE_TIMEOUT, discoverable_timeout))

    before_state = get_bluetooth_state(runner=runner, timeout=timeout)
    if not before_state.get("available") or not before_state.get("controller"):
        return _fail(before_state.get("error") or "Bluetooth controller unavailable.")

    before_ctrl = before_state["controller"]
    adapter_path = str(before_ctrl.get("path") or "/org/bluez/hci0")

    if enabled:
        to_res = _busctl_set_prop(
            adapter_path,
            "org.bluez.Adapter1",
            "DiscoverableTimeout",
            "u",
            str(capped_to),
            runner=runner,
            timeout=timeout,
        )
        if not to_res.ok:
            return _fail(
                to_res.err.strip() or f"Failed to set DiscoverableTimeout (rc={to_res.rc})",
                before=before_ctrl,
            )

    write_res = _busctl_set_prop(
        adapter_path,
        "org.bluez.Adapter1",
        "Discoverable",
        "b",
        "true" if enabled else "false",
        runner=runner,
        timeout=timeout,
    )
    if not write_res.ok:
        return _fail(
            write_res.err.strip() or f"Failed to set Discoverable (rc={write_res.rc})",
            before=before_ctrl,
        )

    after_state = get_bluetooth_state(runner=runner, timeout=timeout)
    if not after_state.get("available") or not after_state.get("controller"):
        return _fail(after_state.get("error") or "Controller unavailable during readback.", before=before_ctrl)

    after_ctrl = after_state["controller"]
    if bool(after_ctrl.get("discoverable")) is not enabled:
        return _fail(
            f"Discoverable readback mismatch: expected {enabled}, got {after_ctrl.get('discoverable')}.",
            before=before_ctrl,
            after=after_ctrl,
        )
    return {"ok": True, "before": before_ctrl, "after": after_ctrl, "error": None}


def _device_prop_op(
    *,
    mac: str,
    prop: str,
    sig: str,
    val_str: str,
    field_key: str,
    expected_val: Any,
    runner: LiveRunner | None,
    timeout: float,
) -> dict[str, Any]:
    try:
        norm_mac = validate_mac(mac)
    except ValueError as exc:
        return _fail(str(exc))

    before_state = get_bluetooth_state(runner=runner, timeout=timeout)
    if not before_state.get("available") or not before_state.get("controller"):
        return _fail(before_state.get("error") or "Bluetooth controller unavailable.")

    before_dev = _find_device(before_state, norm_mac)
    if before_dev is None:
        return _fail(f"Unknown Bluetooth device: {norm_mac}")

    adapter_path = str(before_state["controller"].get("path") or "/org/bluez/hci0")
    dev_path = str(before_dev.get("path") or mac_to_dbus_path(norm_mac, adapter_path))

    write_res = _busctl_set_prop(
        dev_path,
        "org.bluez.Device1",
        prop,
        sig,
        val_str,
        runner=runner,
        timeout=timeout,
    )
    if not write_res.ok:
        return _fail(write_res.err.strip() or f"Failed to set {prop} (rc={write_res.rc})", before=before_dev)

    after_state = get_bluetooth_state(runner=runner, timeout=timeout)
    if not after_state.get("available"):
        return _fail(after_state.get("error") or "Bluetooth unavailable during readback.", before=before_dev)

    after_dev = _find_device(after_state, norm_mac)
    if after_dev is None:
        return _fail(f"Device {norm_mac} vanished during readback.", before=before_dev)

    if after_dev.get(field_key) != expected_val:
        return _fail(
            f"{prop} readback mismatch for {norm_mac}: expected {expected_val!r}, got {after_dev.get(field_key)!r}.",
            before=before_dev,
            after=after_dev,
        )
    return {"ok": True, "before": before_dev, "after": after_dev, "error": None}


def set_trusted(
    mac: str,
    trusted: bool,
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not isinstance(trusted, bool):
        return _fail(f"trusted must be bool, got {trusted!r}.")
    return _device_prop_op(
        mac=mac,
        prop="Trusted",
        sig="b",
        val_str="true" if trusted else "false",
        field_key="trusted",
        expected_val=trusted,
        runner=runner,
        timeout=timeout,
    )


def set_blocked(
    mac: str,
    blocked: bool,
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not isinstance(blocked, bool):
        return _fail(f"blocked must be bool, got {blocked!r}.")
    return _device_prop_op(
        mac=mac,
        prop="Blocked",
        sig="b",
        val_str="true" if blocked else "false",
        field_key="blocked",
        expected_val=blocked,
        runner=runner,
        timeout=timeout,
    )


def set_alias(
    mac: str,
    alias: str,
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not isinstance(alias, str) or not alias.strip():
        return _fail("Alias must be a non-empty string.")
    cleaned = alias.strip()
    if len(cleaned) > 248 or any(ord(c) < 32 for c in cleaned):
        return _fail("Alias contains invalid characters or exceeds 248 chars.")
    return _device_prop_op(
        mac=mac,
        prop="Alias",
        sig="s",
        val_str=cleaned,
        field_key="alias",
        expected_val=cleaned,
        runner=runner,
        timeout=timeout,
    )


def connect_device(
    mac: str,
    *,
    runner: LiveRunner | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    try:
        norm_mac = validate_mac(mac)
    except ValueError as exc:
        return _fail(str(exc))

    before_state = get_bluetooth_state(runner=runner, timeout=DEFAULT_LIVE_CMD_TIMEOUT_SECONDS)
    if not before_state.get("available") or not before_state.get("controller"):
        return _fail(before_state.get("error") or "Bluetooth controller unavailable.")

    before_dev = _find_device(before_state, norm_mac)
    if before_dev is None:
        return _fail(f"Unknown Bluetooth device: {norm_mac}")

    adapter_path = str(before_state["controller"].get("path") or "/org/bluez/hci0")
    dev_path = str(before_dev.get("path") or mac_to_dbus_path(norm_mac, adapter_path))

    call_res = _busctl_call(dev_path, "org.bluez.Device1", "Connect", runner=runner, timeout=timeout)
    if not call_res.ok:
        return _fail(call_res.err.strip() or f"Connect failed (rc={call_res.rc})", before=before_dev)

    after_state = get_bluetooth_state(runner=runner, timeout=DEFAULT_LIVE_CMD_TIMEOUT_SECONDS)
    if not after_state.get("available"):
        return _fail(after_state.get("error") or "Bluetooth unavailable during readback.", before=before_dev)

    after_dev = _find_device(after_state, norm_mac)
    if after_dev is None:
        return _fail(f"Device {norm_mac} vanished during readback.", before=before_dev)

    if not after_dev.get("connected"):
        return _fail(f"Connect readback mismatch for {norm_mac}: still disconnected.", before=before_dev, after=after_dev)
    return {"ok": True, "before": before_dev, "after": after_dev, "error": None}


def disconnect_device(
    mac: str,
    *,
    runner: LiveRunner | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    try:
        norm_mac = validate_mac(mac)
    except ValueError as exc:
        return _fail(str(exc))

    before_state = get_bluetooth_state(runner=runner, timeout=DEFAULT_LIVE_CMD_TIMEOUT_SECONDS)
    if not before_state.get("available") or not before_state.get("controller"):
        return _fail(before_state.get("error") or "Bluetooth controller unavailable.")

    before_dev = _find_device(before_state, norm_mac)
    if before_dev is None:
        return _fail(f"Unknown Bluetooth device: {norm_mac}")

    adapter_path = str(before_state["controller"].get("path") or "/org/bluez/hci0")
    dev_path = str(before_dev.get("path") or mac_to_dbus_path(norm_mac, adapter_path))

    call_res = _busctl_call(dev_path, "org.bluez.Device1", "Disconnect", runner=runner, timeout=timeout)
    if not call_res.ok:
        return _fail(call_res.err.strip() or f"Disconnect failed (rc={call_res.rc})", before=before_dev)

    after_state = get_bluetooth_state(runner=runner, timeout=DEFAULT_LIVE_CMD_TIMEOUT_SECONDS)
    if not after_state.get("available"):
        return _fail(after_state.get("error") or "Bluetooth unavailable during readback.", before=before_dev)

    after_dev = _find_device(after_state, norm_mac)
    if after_dev is None:
        return _fail(f"Device {norm_mac} vanished during readback.", before=before_dev)

    if after_dev.get("connected"):
        return _fail(f"Disconnect readback mismatch for {norm_mac}: still connected.", before=before_dev, after=after_dev)
    return {"ok": True, "before": before_dev, "after": after_dev, "error": None}


def remove_device(
    mac: str,
    *,
    runner: LiveRunner | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    try:
        norm_mac = validate_mac(mac)
    except ValueError as exc:
        return _fail(str(exc))

    before_state = get_bluetooth_state(runner=runner, timeout=DEFAULT_LIVE_CMD_TIMEOUT_SECONDS)
    if not before_state.get("available") or not before_state.get("controller"):
        return _fail(before_state.get("error") or "Bluetooth controller unavailable.")

    before_dev = _find_device(before_state, norm_mac)
    if before_dev is None:
        return _fail(f"Unknown Bluetooth device: {norm_mac}")

    adapter_path = str(before_state["controller"].get("path") or "/org/bluez/hci0")
    dev_path = str(before_dev.get("path") or mac_to_dbus_path(norm_mac, adapter_path))

    call_res = _busctl_call(
        adapter_path,
        "org.bluez.Adapter1",
        "RemoveDevice",
        "o",
        dev_path,
        runner=runner,
        timeout=timeout,
    )
    if not call_res.ok:
        return _fail(call_res.err.strip() or f"RemoveDevice failed (rc={call_res.rc})", before=before_dev)

    after_state = get_bluetooth_state(runner=runner, timeout=DEFAULT_LIVE_CMD_TIMEOUT_SECONDS)
    if not after_state.get("available"):
        return _fail(after_state.get("error") or "Bluetooth unavailable during readback.", before=before_dev)

    after_dev = _find_device(after_state, norm_mac)
    if after_dev is not None:
        return _fail(f"RemoveDevice readback mismatch: {norm_mac} still present.", before=before_dev, after=after_dev)
    return {"ok": True, "before": before_dev, "after": None, "error": None}


def scan_start(
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    before_state = get_bluetooth_state(runner=runner, timeout=timeout)
    if not before_state.get("available") or not before_state.get("controller"):
        return _fail(before_state.get("error") or "Bluetooth controller unavailable.")

    before_ctrl = before_state["controller"]
    if not before_ctrl.get("powered"):
        return _fail("Cannot start scan while Bluetooth is powered off.", before=before_ctrl)

    adapter_path = str(before_ctrl.get("path") or "/org/bluez/hci0")
    res = _busctl_call(adapter_path, "org.bluez.Adapter1", "StartDiscovery", runner=runner, timeout=timeout)
    if not res.ok:
        return _fail(res.err.strip() or f"StartDiscovery failed (rc={res.rc})", before=before_ctrl)

    after_state = get_bluetooth_state(runner=runner, timeout=timeout)
    if not after_state.get("available") or not after_state.get("controller"):
        return _fail(after_state.get("error") or "Controller unavailable during readback.", before=before_ctrl)

    after_ctrl = after_state["controller"]
    return {"ok": True, "before": before_ctrl, "after": after_ctrl, "error": None}


def scan_stop(
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    before_state = get_bluetooth_state(runner=runner, timeout=timeout)
    if not before_state.get("available") or not before_state.get("controller"):
        return _fail(before_state.get("error") or "Bluetooth controller unavailable.")

    before_ctrl = before_state["controller"]
    adapter_path = str(before_ctrl.get("path") or "/org/bluez/hci0")
    res = _busctl_call(adapter_path, "org.bluez.Adapter1", "StopDiscovery", runner=runner, timeout=timeout)
    if not res.ok:
        return _fail(res.err.strip() or f"StopDiscovery failed (rc={res.rc})", before=before_ctrl)

    after_state = get_bluetooth_state(runner=runner, timeout=timeout)
    if not after_state.get("available") or not after_state.get("controller"):
        return _fail(after_state.get("error") or "Controller unavailable during readback.", before=before_ctrl)

    after_ctrl = after_state["controller"]
    if after_ctrl.get("discovering"):
        return _fail("StopDiscovery readback mismatch: still discovering.", before=before_ctrl, after=after_ctrl)
    return {"ok": True, "before": before_ctrl, "after": after_ctrl, "error": None}


def scan_bounded(
    *,
    duration: float = 8.0,
    runner: LiveRunner | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run a bounded discovery scan and ALWAYS stop discovery even on error."""
    capped = max(MIN_SCAN_SECONDS, min(MAX_SCAN_SECONDS, float(duration)))
    start_res = scan_start(runner=runner, timeout=timeout)
    if not start_res.get("ok"):
        return start_res

    adapter_path = str((start_res.get("before") or {}).get("path") or "/org/bluez/hci0")
    try:
        sleep_fn(capped)
    finally:
        _busctl_call(adapter_path, "org.bluez.Adapter1", "StopDiscovery", runner=runner, timeout=timeout)

    after_state = get_bluetooth_state(runner=runner, timeout=timeout)
    if not after_state.get("available"):
        return _fail(after_state.get("error") or "Bluetooth unavailable after scan.", before=start_res.get("before"))
    discovered = [d for d in after_state.get("devices", []) if not d.get("paired")]
    return {
        "ok": True,
        "before": start_res.get("before"),
        "after": after_state.get("controller"),
        "discovered": discovered,
        "devices": after_state.get("devices", []),
        "error": None,
    }


def scan_results(
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    state = get_bluetooth_state(runner=runner, timeout=timeout)
    if not state.get("available"):
        return _fail(state.get("error") or "Bluetooth unavailable.")
    discovered = [d for d in state.get("devices", []) if not d.get("paired")]
    return {
        "ok": True,
        "discovering": bool((state.get("controller") or {}).get("discovering")),
        "discovered": discovered,
        "devices": state.get("devices", []),
        "error": None,
    }


def pair_device(
    mac: str,
    *,
    pair_timeout: int = 20,
    runner: LiveRunner | None = None,
) -> dict[str, Any]:
    """Attempt just-works pairing via one-shot `bluetoothctl --timeout N --agent NoInputNoOutput pair MAC`."""
    try:
        norm_mac = validate_mac(mac)
    except ValueError as exc:
        return _fail(str(exc), needs_manual=False)

    capped_to = max(MIN_PAIR_TIMEOUT, min(MAX_PAIR_TIMEOUT, int(pair_timeout)))

    before_state = get_bluetooth_state(runner=runner)
    if not before_state.get("available") or not before_state.get("controller"):
        return _fail(before_state.get("error") or "Bluetooth controller unavailable.", needs_manual=False)

    before_dev = _find_device(before_state, norm_mac)
    if before_dev is None:
        return _fail(f"Unknown Bluetooth device: {norm_mac}", needs_manual=False)

    pair_res = run_live_cmd(
        ["bluetoothctl", "--timeout", str(capped_to), "--agent", "NoInputNoOutput", "pair", norm_mac],
        timeout=float(capped_to + 5),
        runner=runner,
    )
    combined = f"{pair_res.out}\n{pair_res.err}".lower()

    after_state = get_bluetooth_state(runner=runner)
    after_dev = _find_device(after_state, norm_mac) if after_state.get("available") else None

    if not pair_res.ok:
        needs_manual = any(hint in combined for hint in _MANUAL_PAIR_HINTS)
        err_msg = (
            "Device requires passkey/PIN confirmation; open blueman-manager to pair."
            if needs_manual
            else (pair_res.err.strip() or pair_res.out.strip() or f"Pairing failed (rc={pair_res.rc})")
        )
        return _fail(err_msg, before=before_dev, after=after_dev, needs_manual=needs_manual)

    if after_dev is None or not after_dev.get("paired"):
        return _fail(
            f"Pairing readback mismatch for {norm_mac}: device not marked paired.",
            before=before_dev,
            after=after_dev,
            needs_manual=False,
        )
    return {"ok": True, "before": before_dev, "after": after_dev, "needs_manual": False, "error": None}
