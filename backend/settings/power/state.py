"""Power (battery, CPU EPP/turbo, hypridle, lid/sleep) and System Info probing."""

from __future__ import annotations

import os
import re
from typing import Any, Mapping

from backend.core.env import get_env
from backend.core.live_cmd import DEFAULT_LIVE_CMD_TIMEOUT_SECONDS, LiveRunner, run_live_cmd

_CPU_DIR_RE = re.compile(r"^cpu[0-9]+$")


def resolve_power_paths(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Resolve power/sysinfo paths honoring isolation env overrides."""
    environ = env if env is not None else os.environ
    sysfs_ovr = get_env("POWER_SYSFS_ROOT", environ=environ)
    sysfs_root = os.path.abspath(os.path.expanduser(sysfs_ovr)) if sysfs_ovr else "/sys"

    idle_ovr = get_env("HYPRIDLE_PATH", environ=environ)
    home = os.path.abspath(os.path.expanduser(environ.get("HOME", "").strip() or "~"))
    hypridle_conf = (
        os.path.abspath(os.path.expanduser(idle_ovr))
        if idle_ovr
        else os.path.join(home, ".config", "hypr", "hypridle.conf")
    )

    return {
        "sysfs_root": sysfs_root,
        "hypridle_conf": hypridle_conf,
        "os_release": get_env("OS_RELEASE_PATH", "/etc/os-release", environ=environ),
        "proc_uptime": get_env("PROC_UPTIME_PATH", "/proc/uptime", environ=environ),
        "etc_hostname": get_env("ETC_HOSTNAME_PATH", "/etc/hostname", environ=environ),
    }


def _read_text(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _parse_float(raw: str | None) -> float | None:
    if not raw:
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", raw)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _parse_kv_colon(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (raw or "").splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip().lower()] = v.strip()
    return out


def _read_ac_online(sysfs_root: str) -> bool | None:
    ps_dir = os.path.join(sysfs_root, "class", "power_supply")
    if not os.path.isdir(ps_dir):
        return None
    try:
        for entry in sorted(os.listdir(ps_dir)):
            if entry.startswith("AC") or entry.startswith("ADP"):
                online_txt = _read_text(os.path.join(ps_dir, entry, "online"))
                if online_txt is not None and online_txt.strip() in ("0", "1"):
                    return online_txt.strip() == "1"
    except OSError:
        pass
    return None


def _read_charge_end_threshold(sysfs_root: str) -> int | None:
    ps_dir = os.path.join(sysfs_root, "class", "power_supply")
    if not os.path.isdir(ps_dir):
        return None
    try:
        for entry in sorted(os.listdir(ps_dir)):
            if entry.startswith("BAT"):
                txt = _read_text(os.path.join(ps_dir, entry, "charge_control_end_threshold"))
                if txt is not None and txt.strip().isdigit():
                    return int(txt.strip())
    except OSError:
        pass
    return None


def _probe_battery_sysfs(sysfs_root: str) -> dict[str, Any]:
    ps_dir = os.path.join(sysfs_root, "class", "power_supply")
    ac_online = _read_ac_online(sysfs_root)
    if not os.path.isdir(ps_dir):
        return {"available": False, "ac_online": ac_online}

    bat_name = None
    try:
        for entry in sorted(os.listdir(ps_dir)):
            if entry.startswith("BAT"):
                bat_name = entry
                break
    except OSError:
        return {"available": False, "ac_online": ac_online}

    if not bat_name:
        return {"available": False, "ac_online": ac_online}

    uevent = _read_text(os.path.join(ps_dir, bat_name, "uevent"))
    if not uevent:
        return {"available": False, "ac_online": ac_online}

    vals: dict[str, str] = {}
    for line in uevent.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()

    pct = _parse_float(vals.get("POWER_SUPPLY_CAPACITY"))
    state = (vals.get("POWER_SUPPLY_STATUS") or "unknown").lower()

    e_now = _parse_float(vals.get("POWER_SUPPLY_ENERGY_NOW"))
    e_full = _parse_float(vals.get("POWER_SUPPLY_ENERGY_FULL"))
    e_design = _parse_float(vals.get("POWER_SUPPLY_ENERGY_FULL_DESIGN"))
    p_now = _parse_float(vals.get("POWER_SUPPLY_POWER_NOW"))

    energy_wh = round(e_now / 1e6, 4) if e_now is not None else None
    energy_full_wh = round(e_full / 1e6, 4) if e_full is not None else None
    energy_design_wh = round(e_design / 1e6, 4) if e_design is not None else None
    energy_rate_w = round(p_now / 1e6, 3) if p_now is not None else None

    health_pct: float | None = None
    if e_full is not None and e_design and e_design > 0:
        health_pct = round((e_full / e_design) * 100.0, 2)
    else:
        c_full = _parse_float(vals.get("POWER_SUPPLY_CHARGE_FULL"))
        c_design = _parse_float(vals.get("POWER_SUPPLY_CHARGE_FULL_DESIGN"))
        if c_full is not None and c_design and c_design > 0:
            health_pct = round((c_full / c_design) * 100.0, 2)

    cycles_raw = _parse_float(vals.get("POWER_SUPPLY_CYCLE_COUNT"))
    charge_cycles = int(cycles_raw) if (cycles_raw is not None and cycles_raw > 0) else None

    return {
        "available": True,
        "name": bat_name,
        "state": state,
        "percentage": pct,
        "energy_wh": energy_wh,
        "energy_full_wh": energy_full_wh,
        "energy_full_design_wh": energy_design_wh,
        "health_percent": health_pct,
        "energy_rate_w": energy_rate_w,
        "time_to_empty": None,
        "time_to_full": None,
        "charge_cycles": charge_cycles,
        "charge_end_threshold": _read_charge_end_threshold(sysfs_root),
        "ac_online": ac_online,
    }


def probe_battery(
    sysfs_root: str,
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Probe battery via `upower -i` with fallback to sysfs power_supply."""
    ac_online = _read_ac_online(sysfs_root)
    res = run_live_cmd(
        ["upower", "-i", "/org/freedesktop/UPower/devices/battery_BAT1"],
        timeout=timeout,
        runner=runner,
    )
    if not res.ok or not res.out.strip():
        return _probe_battery_sysfs(sysfs_root)

    kv = _parse_kv_colon(res.out)
    if kv.get("present") != "yes" and "percentage" not in kv:
        return _probe_battery_sysfs(sysfs_root)

    cycles_raw = kv.get("charge-cycles", "")
    cycles = int(cycles_raw) if cycles_raw.isdigit() and int(cycles_raw) > 0 else None
    health_raw = _parse_float(kv.get("capacity"))
    health_pct = round(health_raw, 2) if health_raw is not None else None

    return {
        "available": True,
        "name": kv.get("native-path") or "BAT1",
        "state": kv.get("state") or "unknown",
        "percentage": _parse_float(kv.get("percentage")),
        "energy_wh": _parse_float(kv.get("energy")),
        "energy_full_wh": _parse_float(kv.get("energy-full")),
        "energy_full_design_wh": _parse_float(kv.get("energy-full-design")),
        "health_percent": health_pct,
        "energy_rate_w": _parse_float(kv.get("energy-rate")),
        "time_to_empty": kv.get("time to empty") or None,
        "time_to_full": kv.get("time to full") or None,
        "charge_cycles": cycles,
        "charge_end_threshold": _read_charge_end_threshold(sysfs_root),
        "ac_online": ac_online,
    }


def _cpu_dirs(sysfs_root: str) -> list[str]:
    cpu_base = os.path.join(sysfs_root, "devices", "system", "cpu")
    if not os.path.isdir(cpu_base):
        return []
    dirs: list[str] = []
    try:
        for entry in sorted(os.listdir(cpu_base)):
            if _CPU_DIR_RE.match(entry):
                full = os.path.join(cpu_base, entry)
                if os.path.isdir(full):
                    dirs.append(full)
    except OSError:
        return []
    return dirs


def read_per_cpu_epp(sysfs_root: str) -> dict[str, str]:
    """Return mapping of cpuN -> current energy_performance_preference."""
    out: dict[str, str] = {}
    for cdir in _cpu_dirs(sysfs_root):
        val = _read_text(os.path.join(cdir, "cpufreq", "energy_performance_preference"))
        if val is not None:
            out[os.path.basename(cdir)] = val.strip()
    return out


def read_turbo_enabled(sysfs_root: str) -> bool | None:
    """Return True if intel_pstate/no_turbo == '0', False if '1', None if absent."""
    txt = _read_text(os.path.join(sysfs_root, "devices", "system", "cpu", "intel_pstate", "no_turbo"))
    if txt is None:
        return None
    val = txt.strip()
    if val == "0":
        return True
    if val == "1":
        return False
    return None


def probe_cpu(sysfs_root: str) -> dict[str, Any]:
    """Read CPU scaling driver, governor, EPP preferences, and Intel turbo status from sysfs."""
    cdirs = _cpu_dirs(sysfs_root)
    if not cdirs:
        return {
            "available": False,
            "driver": None,
            "governor": None,
            "available_governors": [],
            "epp_current": None,
            "epp_available": [],
            "turbo_enabled": None,
            "cpu_count": 0,
        }

    first_cpufreq = os.path.join(cdirs[0], "cpufreq")
    driver = (_read_text(os.path.join(first_cpufreq, "scaling_driver")) or "").strip() or None
    governor = (_read_text(os.path.join(first_cpufreq, "scaling_governor")) or "").strip() or None
    avail_gov_raw = _read_text(os.path.join(first_cpufreq, "scaling_available_governors")) or ""
    avail_gov = [t for t in avail_gov_raw.split() if t]

    per_cpu_epp = read_per_cpu_epp(sysfs_root)
    epp_current = per_cpu_epp.get(os.path.basename(cdirs[0]))
    epp_avail_raw = _read_text(os.path.join(first_cpufreq, "energy_performance_available_preferences")) or ""
    epp_avail = [t for t in epp_avail_raw.split() if t]
    turbo_enabled = read_turbo_enabled(sysfs_root)

    available = bool(driver or epp_current or turbo_enabled is not None)
    return {
        "available": available,
        "driver": driver,
        "governor": governor,
        "available_governors": avail_gov,
        "epp_current": epp_current,
        "epp_available": epp_avail,
        "turbo_enabled": turbo_enabled,
        "cpu_count": len(cdirs),
    }


def classify_listener_role(on_timeout: str) -> str:
    """Classify a hypridle listener block into dim | lock | dpms | suspend | other."""
    cmd = (on_timeout or "").lower()
    if "dpms off" in cmd:
        return "dpms"
    if "lock-session" in cmd or "hyprlock" in cmd:
        return "lock"
    if "brightnessctl" in cmd:
        return "dim"
    if "suspend" in cmd:
        return "suspend"
    return "other"


def parse_hypridle_conf(raw: str) -> list[dict[str, Any]]:
    """Parse `listener { ... }` blocks from hypridle.conf preserving file order and line indices."""
    listeners: list[dict[str, Any]] = []
    lines = (raw or "").splitlines()
    in_listener = False
    depth = 0
    cur: dict[str, Any] = {}

    for idx, line in enumerate(lines):
        stripped = line.split("#", 1)[0].strip()
        if not in_listener:
            if re.match(r"^listener\s*\{$", stripped):
                in_listener = True
                depth = 1
                cur = {
                    "index": len(listeners),
                    "timeout": None,
                    "on_timeout": "",
                    "on_resume": "",
                    "timeout_line_index": None,
                }
            continue

        depth += stripped.count("{") - stripped.count("}")
        if "=" in stripped:
            k, v = stripped.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k == "timeout":
                try:
                    cur["timeout"] = int(v)
                    cur["timeout_line_index"] = idx
                except ValueError:
                    pass
            elif k == "on-timeout":
                cur["on_timeout"] = v
            elif k == "on-resume":
                cur["on_resume"] = v

        if depth <= 0:
            in_listener = False
            if cur["timeout"] is not None:
                cur["role"] = classify_listener_role(cur["on_timeout"])
                listeners.append(cur)

    return listeners


def probe_hypridle(
    hypridle_path: str,
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Probe hypridle daemon status via pgrep and parse listeners from hypridle.conf."""
    pg_res = run_live_cmd(["pgrep", "-x", "hypridle"], timeout=timeout, runner=runner)
    running = pg_res.ok

    raw = _read_text(hypridle_path)
    if raw is None:
        return {
            "available": False,
            "running": running,
            "config_path": hypridle_path,
            "listeners": [],
        }

    listeners = parse_hypridle_conf(raw)
    return {
        "available": True,
        "running": running,
        "config_path": hypridle_path,
        "listeners": [
            {
                "index": l["index"],
                "role": l["role"],
                "timeout": l["timeout"],
                "on_timeout": l["on_timeout"],
                "on_resume": l["on_resume"],
            }
            for l in listeners
        ],
    }


def probe_lid_sleep(
    sysfs_root: str,
    *,
    runner: LiveRunner | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Read /sys/power/mem_sleep and effective systemd-logind lid switch settings (read-only)."""
    mem_sleep_raw = (_read_text(os.path.join(sysfs_root, "power", "mem_sleep")) or "").strip() or None
    active_sleep = None
    if mem_sleep_raw:
        m = re.search(r"\[([^\]]+)\]", mem_sleep_raw)
        if m:
            active_sleep = m.group(1)

    lid_vals: dict[str, str] = {
        "handle_lid_switch": "suspend",
        "handle_lid_switch_external_power": "suspend",
        "handle_lid_switch_docked": "ignore",
    }
    res = run_live_cmd(
        ["systemd-analyze", "cat-config", "systemd/logind.conf"],
        timeout=timeout,
        runner=runner,
    )
    if res.ok and res.out:
        key_map = {
            "HandleLidSwitch": "handle_lid_switch",
            "HandleLidSwitchExternalPower": "handle_lid_switch_external_power",
            "HandleLidSwitchDocked": "handle_lid_switch_docked",
        }
        for line in res.out.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            if k in key_map and v.strip():
                lid_vals[key_map[k]] = v.strip()

    return {
        "available": mem_sleep_raw is not None or res.ok,
        "mem_sleep": mem_sleep_raw,
        "mem_sleep_active": active_sleep,
        **lid_vals,
    }


def get_power_state(
    *,
    runner: LiveRunner | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Assemble full S7 Power state (battery, cpu, hypridle, lid_sleep, capabilities)."""
    paths = resolve_power_paths(env)
    sysfs_root = paths["sysfs_root"]

    battery = probe_battery(sysfs_root, runner=runner, timeout=timeout)
    cpu = probe_cpu(sysfs_root)
    hypridle = probe_hypridle(paths["hypridle_conf"], runner=runner, timeout=timeout)
    lid_sleep = probe_lid_sleep(sysfs_root, runner=runner, timeout=timeout)

    capabilities = {
        "has_battery": bool(battery.get("available")),
        "can_write_epp": bool(cpu.get("available") and cpu.get("epp_available")),
        "can_write_turbo": bool(cpu.get("available") and cpu.get("turbo_enabled") is not None),
        "hypridle_present": bool(hypridle.get("available")),
    }
    any_avail = any([battery.get("available"), cpu.get("available"), hypridle.get("available"), lid_sleep.get("available")])
    return {
        "available": any_avail,
        "battery": battery,
        "cpu": cpu,
        "hypridle": hypridle,
        "lid_sleep": lid_sleep,
        "capabilities": capabilities,
        "error": None if any_avail else "No power backends available.",
    }


def _fmt_bytes(n: int) -> str:
    gib = n / (1024 ** 3)
    if gib >= 1.0:
        return f"{gib:.1f} GiB"
    mib = n / (1024 ** 2)
    return f"{mib:.0f} MiB"


def get_system_info(
    *,
    runner: LiveRunner | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_LIVE_CMD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Assemble privacy-safe System Info (never includes machine_id, boot_id, serials, MAC, or IP)."""
    paths = resolve_power_paths(env)
    sysfs_root = paths["sysfs_root"]

    hostname: str | None = None
    kernel: str | None = None
    os_name: str | None = None
    vendor_model: str | None = None

    # os-release
    os_raw = _read_text(paths["os_release"])
    if os_raw:
        for line in os_raw.splitlines():
            if line.startswith("PRETTY_NAME="):
                os_name = line.split("=", 1)[1].strip().strip('"')
                break

    # hostnamectl (strictly extract only hostname / OS / vendor / model; never Machine ID / Boot ID)
    hctl = run_live_cmd(["hostnamectl"], timeout=timeout, runner=runner)
    if hctl.ok and hctl.out:
        kv = _parse_kv_colon(hctl.out)
        hostname = kv.get("static hostname") or None
        if not os_name:
            os_name = kv.get("operating system") or None
        hv = kv.get("hardware vendor")
        hm = kv.get("hardware model")
        if hv or hm:
            vendor_model = " ".join(p for p in (hv, hm) if p)

    if not hostname:
        hn_raw = _read_text(paths["etc_hostname"])
        if hn_raw and hn_raw.strip():
            hostname = hn_raw.strip()

    if not vendor_model:
        sv = (_read_text(os.path.join(sysfs_root, "class", "dmi", "id", "sys_vendor")) or "").strip()
        pn = (_read_text(os.path.join(sysfs_root, "class", "dmi", "id", "product_name")) or "").strip()
        if sv or pn:
            vendor_model = " ".join(p for p in (sv, pn) if p)

    un_res = run_live_cmd(["uname", "-r"], timeout=timeout, runner=runner)
    if un_res.ok and un_res.out.strip():
        kernel = un_res.out.strip()

    cpu_model: str | None = None
    cpu_cores: int | None = None
    lscpu_res = run_live_cmd(["lscpu"], timeout=timeout, runner=runner)
    if lscpu_res.ok and lscpu_res.out:
        kv = _parse_kv_colon(lscpu_res.out)
        cpu_model = kv.get("model name") or None
        if kv.get("cpu(s)", "").isdigit():
            cpu_cores = int(kv["cpu(s)"])

    ram_total: str | None = None
    ram_used: str | None = None
    free_res = run_live_cmd(["free", "-b"], timeout=timeout, runner=runner)
    if free_res.ok and free_res.out:
        for line in free_res.out.splitlines():
            if line.startswith("Mem:"):
                parts = line.split()
                if len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
                    ram_total = _fmt_bytes(int(parts[1]))
                    ram_used = _fmt_bytes(int(parts[2]))
                break

    disk_total: str | None = None
    disk_used: str | None = None
    disk_pct: str | None = None
    df_res = run_live_cmd(["df", "-B1", "/"], timeout=timeout, runner=runner)
    if df_res.ok and df_res.out:
        lines = [l for l in df_res.out.splitlines() if l.strip()]
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 5 and parts[1].isdigit() and parts[2].isdigit():
                disk_total = _fmt_bytes(int(parts[1]))
                disk_used = _fmt_bytes(int(parts[2]))
                disk_pct = parts[4]

    gpu: str | None = None
    lspci_res = run_live_cmd(["lspci"], timeout=timeout, runner=runner)
    if lspci_res.ok and lspci_res.out:
        for line in lspci_res.out.splitlines():
            low = line.lower()
            if "vga compatible controller:" in low or "3d controller:" in low or "display controller:" in low:
                parts = line.strip().split(None, 1)
                gpu = parts[1].strip() if len(parts) == 2 else line.strip()
                break

    uptime: str | None = None
    up_res = run_live_cmd(["uptime", "-p"], timeout=timeout, runner=runner)
    if up_res.ok and up_res.out.strip():
        uptime = up_res.out.strip()
    else:
        up_raw = _read_text(paths["proc_uptime"])
        if up_raw:
            secs = _parse_float(up_raw.split()[0])
            if secs is not None:
                mins = int(secs // 60)
                uptime = f"up {mins // 60}h {mins % 60}m"

    hyprland_version: str | None = None
    hv_res = run_live_cmd(["hyprctl", "version"], timeout=timeout, runner=runner)
    if hv_res.ok and hv_res.out.strip():
        first = hv_res.out.splitlines()[0].strip()
        m = re.match(r"^(Hyprland\s+\S+)", first)
        hyprland_version = m.group(1) if m else first

    quickshell_version: str | None = None
    qs_res = run_live_cmd(["quickshell", "--version"], timeout=timeout, runner=runner)
    if qs_res.ok and qs_res.out.strip():
        quickshell_version = qs_res.out.splitlines()[0].strip()

    return {
        "available": True,
        "hostname": hostname,
        "os_name": os_name,
        "kernel": kernel,
        "vendor_model": vendor_model,
        "cpu_model": cpu_model,
        "cpu_cores": cpu_cores,
        "ram_total": ram_total,
        "ram_used": ram_used,
        "disk_root_total": disk_total,
        "disk_root_used": disk_used,
        "disk_root_percent": disk_pct,
        "gpu": gpu,
        "uptime": uptime,
        "hyprland_version": hyprland_version,
        "quickshell_version": quickshell_version,
    }
