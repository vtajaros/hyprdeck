"""NetworkManager live operations via `nmcli` with UUID addressing, readback, and password safety."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from typing import Any, Callable

from backend.core.live_cmd import DEFAULT_LIVE_CMD_TIMEOUT_SECONDS, LiveRunner, run_live_cmd
from backend.settings.network.state import (
    get_network_state,
    nmcli_env,
    split_nmcli_terse_line,
    validate_iface_name,
    validate_ip_list,
    validate_uuid,
)

VALID_METERED_VALUES = frozenset({"yes", "no", "unknown"})
DEFAULT_CONNECT_WAIT_SECONDS = 15.0


def _fail(error: str, before: Any = None, after: Any = None, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "before": before, "after": after, "error": error}
    out.update(extra)
    return out


def _find_connection(state: dict[str, Any], uuid: str) -> dict[str, Any] | None:
    for c in state.get("connections", []):
        if isinstance(c, dict) and c.get("uuid") == uuid:
            return c
    return None


def _find_device(state: dict[str, Any], name: str) -> dict[str, Any] | None:
    for d in state.get("devices", []):
        if isinstance(d, dict) and d.get("name") == name:
            return d
    return None


def _read_connection_fields(
    uuid: str,
    fields: list[str],
    *,
    runner: LiveRunner | None,
    timeout: float,
) -> dict[str, str] | None:
    res = run_live_cmd(
        ["nmcli", "-t", "-f", ",".join(fields), "connection", "show", "uuid", uuid],
        timeout=timeout,
        runner=runner,
        env=nmcli_env(),
    )
    if not res.ok:
        return None
    out: dict[str, str] = {}
    for line in res.out.splitlines():
        if not line.strip():
            continue
        parts = split_nmcli_terse_line(line)
        if len(parts) >= 2:
            out[parts[0].strip()] = ":".join(parts[1:]).strip() if len(parts) > 2 else parts[1].strip()
    return out


def _sanitize_error(msg: str, secret: str | None) -> str:
    if not secret:
        return msg
    return msg.replace(secret, "***")


def set_wifi_enabled(
    enabled: bool,
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not isinstance(enabled, bool):
        return _fail(f"enabled must be bool, got {enabled!r}.")

    before_state = get_network_state(runner=runner, timeout=timeout)
    if not before_state.get("available"):
        return _fail(before_state.get("error") or "NetworkManager unavailable.")

    before_gen = before_state["general"]
    if not before_gen.get("wifi_hw_enabled"):
        return _fail("Wi-Fi hardware is disabled.", before=before_gen)

    res = run_live_cmd(
        ["nmcli", "radio", "wifi", "on" if enabled else "off"],
        timeout=timeout,
        runner=runner,
        env=nmcli_env(),
    )
    if not res.ok:
        return _fail(res.err.strip() or f"nmcli radio wifi failed (rc={res.rc})", before=before_gen)

    after_state = get_network_state(runner=runner, timeout=timeout)
    if not after_state.get("available"):
        return _fail(after_state.get("error") or "NetworkManager unavailable during readback.", before=before_gen)

    after_gen = after_state["general"]
    if bool(after_gen.get("wifi_enabled")) is not enabled:
        return _fail(
            f"Wi-Fi readback mismatch: expected {enabled}, got {after_gen.get('wifi_enabled')}.",
            before=before_gen,
            after=after_gen,
        )
    return {"ok": True, "before": before_gen, "after": after_gen, "error": None}


def rescan(
    *,
    runner: LiveRunner | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    before_state = get_network_state(runner=runner, timeout=timeout)
    if not before_state.get("available"):
        return _fail(before_state.get("error") or "NetworkManager unavailable.")
    if not before_state.get("has_wifi_device"):
        return _fail("No Wi-Fi device present.", before=before_state)
    if not before_state["general"].get("wifi_enabled"):
        return _fail("Wi-Fi is disabled.", before=before_state)

    res = run_live_cmd(
        ["nmcli", "device", "wifi", "rescan"],
        timeout=timeout,
        runner=runner,
        env=nmcli_env(),
    )
    if not res.ok:
        return _fail(res.err.strip() or f"nmcli device wifi rescan failed (rc={res.rc})", before=before_state)

    after_state = get_network_state(runner=runner, timeout=timeout)
    if not after_state.get("available"):
        return _fail(after_state.get("error") or "NetworkManager unavailable after rescan.", before=before_state)
    return {
        "ok": True,
        "before": {"wifi_count": len(before_state.get("wifi_networks", []))},
        "after": {"wifi_count": len(after_state.get("wifi_networks", [])), "wifi_networks": after_state.get("wifi_networks", [])},
        "error": None,
    }


def connect_saved(
    uuid: str,
    *,
    wait_timeout: float = DEFAULT_CONNECT_WAIT_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
    runner: LiveRunner | None = None,
) -> dict[str, Any]:
    try:
        norm_uuid = validate_uuid(uuid)
    except ValueError as exc:
        return _fail(str(exc))

    before_state = get_network_state(runner=runner)
    if not before_state.get("available"):
        return _fail(before_state.get("error") or "NetworkManager unavailable.")

    before_conn = _find_connection(before_state, norm_uuid)
    if before_conn is None:
        return _fail(f"Unknown connection UUID: {norm_uuid}")

    res = run_live_cmd(
        ["nmcli", "connection", "up", "uuid", norm_uuid],
        timeout=max(5.0, float(wait_timeout)),
        runner=runner,
        env=nmcli_env(),
    )
    if not res.ok:
        return _fail(
            res.err.strip() or f"nmcli connection up failed (rc={res.rc})",
            before=before_conn,
            timed_out=res.timed_out,
        )

    deadline = time.monotonic() + max(0.5, float(wait_timeout))
    after_conn = None
    while True:
        after_state = get_network_state(runner=runner)
        if after_state.get("available"):
            after_conn = _find_connection(after_state, norm_uuid)
            if after_conn and after_conn.get("active"):
                return {"ok": True, "before": before_conn, "after": after_conn, "error": None}
        if time.monotonic() >= deadline:
            break
        sleep_fn(0.5)

    return _fail(
        f"Timed out waiting for connection {norm_uuid} to become active.",
        before=before_conn,
        after=after_conn,
        timed_out=True,
    )


def disconnect(
    device: str,
    *,
    confirm: bool = False,
    runner: LiveRunner | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    try:
        dev_name = validate_iface_name(device)
    except ValueError as exc:
        return _fail(str(exc))

    before_state = get_network_state(runner=runner, timeout=timeout)
    if not before_state.get("available"):
        return _fail(before_state.get("error") or "NetworkManager unavailable.")

    before_dev = _find_device(before_state, dev_name)
    if before_dev is None:
        return _fail(f"Unknown network device: {dev_name}")

    if before_dev.get("would_cut_current_session") and not confirm:
        return _fail(
            f"Disconnecting {dev_name} would cut your current active session; confirmation required.",
            before=before_dev,
            requires_confirm=True,
        )

    res = run_live_cmd(
        ["nmcli", "device", "disconnect", dev_name],
        timeout=timeout,
        runner=runner,
        env=nmcli_env(),
    )
    if not res.ok:
        return _fail(res.err.strip() or f"nmcli device disconnect failed (rc={res.rc})", before=before_dev)

    after_state = get_network_state(runner=runner, timeout=timeout)
    if not after_state.get("available"):
        return _fail(after_state.get("error") or "NetworkManager unavailable during readback.", before=before_dev)

    after_dev = _find_device(after_state, dev_name)
    if after_dev and after_dev.get("is_active"):
        return _fail(
            f"Disconnect readback mismatch for {dev_name}: still connected.",
            before=before_dev,
            after=after_dev,
        )
    return {"ok": True, "before": before_dev, "after": after_dev, "error": None}


def connect_new_wifi(
    ssid: str,
    *,
    security: str = "",
    password: str | None = None,
    wait_timeout: float = DEFAULT_CONNECT_WAIT_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
    runner: LiveRunner | None = None,
) -> dict[str, Any]:
    if not isinstance(ssid, str) or not ssid:
        return _fail("SSID must be a non-empty string.")

    before_state = get_network_state(runner=runner)
    if not before_state.get("available"):
        return _fail(before_state.get("error") or "NetworkManager unavailable.")
    if not before_state.get("has_wifi_device"):
        return _fail("No Wi-Fi device present.")
    if not before_state["general"].get("wifi_enabled"):
        return _fail("Wi-Fi is disabled.")

    known = {w.get("ssid"): w for w in before_state.get("wifi_networks", []) if w.get("ssid")}
    if known and ssid not in known:
        return _fail(f"Unknown SSID: {ssid}")

    before_wifi = known.get(ssid)
    tmp_dir: str | None = None
    try:
        argv = ["nmcli", "device", "wifi", "connect", ssid]
        if password is not None and len(password) > 0:
            tmp_dir = tempfile.mkdtemp(prefix="hks_nm_")
            os.chmod(tmp_dir, 0o700)
            pw_path = os.path.join(tmp_dir, "passwd")
            fd = os.open(pw_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                key_name = "802-11-wireless-security.wep-key0" if "wep" in (security or "").lower() else "802-11-wireless-security.psk"
                os.write(fd, f"{key_name}:{password}\n".encode("utf-8"))
            finally:
                os.close(fd)
            argv.extend(["passwd-file", pw_path])

        res = run_live_cmd(
            argv,
            timeout=max(5.0, float(wait_timeout)),
            runner=runner,
            env=nmcli_env(),
        )
    finally:
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    if not res.ok:
        err = _sanitize_error(res.err.strip() or f"Wi-Fi connect failed (rc={res.rc})", password)
        return _fail(err, before=before_wifi, timed_out=res.timed_out)

    deadline = time.monotonic() + max(0.5, float(wait_timeout))
    after_wifi = None
    while True:
        after_state = get_network_state(runner=runner)
        if after_state.get("available"):
            after_wifi = next((w for w in after_state.get("wifi_networks", []) if w.get("ssid") == ssid), None)
            if after_wifi and after_wifi.get("in_use"):
                return {"ok": True, "before": before_wifi, "after": after_wifi, "error": None}
            if any(c.get("name") == ssid and c.get("active") for c in after_state.get("connections", [])):
                return {"ok": True, "before": before_wifi, "after": after_wifi, "error": None}
        if time.monotonic() >= deadline:
            break
        sleep_fn(0.5)

    return _fail(
        f"Timed out waiting for Wi-Fi connection to {ssid}.",
        before=before_wifi,
        after=after_wifi,
        timed_out=True,
    )


def forget(
    uuid: str,
    *,
    confirm: bool = False,
    runner: LiveRunner | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    try:
        norm_uuid = validate_uuid(uuid)
    except ValueError as exc:
        return _fail(str(exc))

    before_state = get_network_state(runner=runner, timeout=timeout)
    if not before_state.get("available"):
        return _fail(before_state.get("error") or "NetworkManager unavailable.")

    before_conn = _find_connection(before_state, norm_uuid)
    if before_conn is None:
        return _fail(f"Unknown connection UUID: {norm_uuid}")

    if before_conn.get("would_cut_current_session") and not confirm:
        return _fail(
            f"Forgetting {before_conn.get('name', norm_uuid)} would cut your current active session; confirmation required.",
            before=before_conn,
            requires_confirm=True,
        )

    res = run_live_cmd(
        ["nmcli", "connection", "delete", "uuid", norm_uuid],
        timeout=timeout,
        runner=runner,
        env=nmcli_env(),
    )
    if not res.ok:
        return _fail(res.err.strip() or f"nmcli connection delete failed (rc={res.rc})", before=before_conn)

    after_state = get_network_state(runner=runner, timeout=timeout)
    if not after_state.get("available"):
        return _fail(after_state.get("error") or "NetworkManager unavailable during readback.", before=before_conn)

    after_conn = _find_connection(after_state, norm_uuid)
    if after_conn is not None:
        return _fail(f"Delete readback mismatch: {norm_uuid} still present.", before=before_conn, after=after_conn)
    return {"ok": True, "before": before_conn, "after": None, "error": None}


def set_autoconnect(
    uuid: str,
    enabled: bool,
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not isinstance(enabled, bool):
        return _fail(f"enabled must be bool, got {enabled!r}.")
    try:
        norm_uuid = validate_uuid(uuid)
    except ValueError as exc:
        return _fail(str(exc))

    before_fields = _read_connection_fields(norm_uuid, ["connection.uuid", "connection.autoconnect"], runner=runner, timeout=timeout)
    if before_fields is None:
        return _fail(f"Unknown connection UUID: {norm_uuid}")

    target_str = "yes" if enabled else "no"
    res = run_live_cmd(
        ["nmcli", "connection", "modify", "uuid", norm_uuid, "connection.autoconnect", target_str],
        timeout=timeout,
        runner=runner,
        env=nmcli_env(),
    )
    if not res.ok:
        return _fail(res.err.strip() or f"nmcli connection modify failed (rc={res.rc})", before=before_fields)

    after_fields = _read_connection_fields(norm_uuid, ["connection.uuid", "connection.autoconnect"], runner=runner, timeout=timeout)
    if after_fields is None:
        return _fail(f"Connection {norm_uuid} vanished during readback.", before=before_fields)
    if after_fields.get("connection.autoconnect", "").lower() != target_str:
        return _fail(
            f"Autoconnect readback mismatch: expected {target_str!r}, got {after_fields.get('connection.autoconnect')!r}.",
            before=before_fields,
            after=after_fields,
        )
    return {"ok": True, "before": before_fields, "after": after_fields, "error": None}


def set_metered(
    uuid: str,
    value: str,
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    try:
        norm_uuid = validate_uuid(uuid)
    except ValueError as exc:
        return _fail(str(exc))
    val = str(value).strip().lower()
    if val not in VALID_METERED_VALUES:
        return _fail(f"Metered value must be yes, no, or unknown, got {value!r}.")

    before_fields = _read_connection_fields(norm_uuid, ["connection.uuid", "connection.metered"], runner=runner, timeout=timeout)
    if before_fields is None:
        return _fail(f"Unknown connection UUID: {norm_uuid}")

    res = run_live_cmd(
        ["nmcli", "connection", "modify", "uuid", norm_uuid, "connection.metered", val],
        timeout=timeout,
        runner=runner,
        env=nmcli_env(),
    )
    if not res.ok:
        return _fail(res.err.strip() or f"nmcli connection modify failed (rc={res.rc})", before=before_fields)

    after_fields = _read_connection_fields(norm_uuid, ["connection.uuid", "connection.metered"], runner=runner, timeout=timeout)
    if after_fields is None:
        return _fail(f"Connection {norm_uuid} vanished during readback.", before=before_fields)
    if after_fields.get("connection.metered", "").lower() != val:
        return _fail(
            f"Metered readback mismatch: expected {val!r}, got {after_fields.get('connection.metered')!r}.",
            before=before_fields,
            after=after_fields,
        )
    return {"ok": True, "before": before_fields, "after": after_fields, "error": None}


def set_ipv4_dns(
    uuid: str,
    servers: Any,
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    try:
        norm_uuid = validate_uuid(uuid)
        ips = validate_ip_list(servers)
    except ValueError as exc:
        return _fail(str(exc))

    before_fields = _read_connection_fields(norm_uuid, ["connection.uuid", "ipv4.dns", "ipv4.ignore-auto-dns"], runner=runner, timeout=timeout)
    if before_fields is None:
        return _fail(f"Unknown connection UUID: {norm_uuid}")

    dns_arg = ",".join(ips) if ips else ""
    ignore_auto = "yes" if ips else "no"
    res = run_live_cmd(
        ["nmcli", "connection", "modify", "uuid", norm_uuid, "ipv4.dns", dns_arg, "ipv4.ignore-auto-dns", ignore_auto],
        timeout=timeout,
        runner=runner,
        env=nmcli_env(),
    )
    if not res.ok:
        return _fail(res.err.strip() or f"nmcli connection modify failed (rc={res.rc})", before=before_fields)

    after_fields = _read_connection_fields(norm_uuid, ["connection.uuid", "ipv4.dns", "ipv4.ignore-auto-dns"], runner=runner, timeout=timeout)
    if after_fields is None:
        return _fail(f"Connection {norm_uuid} vanished during readback.", before=before_fields)

    actual_dns = [p.strip() for p in after_fields.get("ipv4.dns", "").split(",") if p.strip()]
    if actual_dns != ips:
        return _fail(
            f"DNS readback mismatch: expected {ips!r}, got {actual_dns!r}.",
            before=before_fields,
            after=after_fields,
        )
    return {"ok": True, "before": before_fields, "after": after_fields, "error": None}
