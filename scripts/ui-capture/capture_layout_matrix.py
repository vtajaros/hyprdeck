#!/usr/bin/env python3
"""Headless offscreen screenshot + ImageMagick contact sheet generator for HyprDeck Settings."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

CAPTURE_SIZES = (
    (1880, 1130),
    (1030, 1130),
    (930, 1130),
    (610, 1130),
    (455, 1130),
)

CAPTURE_PAGES = (
    ("appearance", ""),
    ("desktop", ""),
    ("display", ""),
    ("input", "keyboard"),
    ("audio", ""),
    ("bluetooth", ""),
    ("network", ""),
    ("themes", ""),
    ("power", ""),
    ("sysinfo", ""),
    ("keyboard", ""),
)


def _png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as fh:
            header = fh.read(24)
    except OSError:
        return None
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", header[16:24])


def _wait_ready(pid: int) -> bool:
    for _ in range(40):
        res = subprocess.run(
            ["quickshell", "ipc", "--pid", str(pid), "show"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0 and "target settings" in res.stdout:
            return True
        time.sleep(0.15)
    return False


def _wait_services(pid: int) -> None:
    for _ in range(40):
        res = subprocess.run(
            ["quickshell", "ipc", "--pid", str(pid), "call", "settings", "debugState"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            st = json.loads(res.stdout.strip())
            if not (
                st["loading"]
                or st["display"]["loading"]
                or st["input"]["loading"]
                or st["audio"]["loading"]
                or st["bluetooth"]["loading"]
                or st["network"]["loading"]
                or st["themes"]["loading"]
                or st["power"]["loading"]
                or st["system"]["loading"]
                or st["keyboard"]["loading"]
            ):
                return
        time.sleep(0.15)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture headless offscreen layout matrix PNGs.")
    parser.add_argument("--out-dir", default="", help="Output directory (default: <repo>/build/layout-shots)")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent.parent
    shell_qml = repo_root / "settings" / "shell.qml"
    out_dir = Path(args.out_dir) if args.out_dir else (repo_root / "build" / "layout-shots")
    out_dir.mkdir(parents=True, exist_ok=True)

    montage_bin = shutil.which("montage") or "/usr/bin/montage"
    has_montage = Path(montage_bin).is_file()

    env = {
        **os.environ,
        "QT_QPA_PLATFORM": "offscreen",
        "HYPRDECK_KEEP_ALIVE": "1",
        "HKS_KEEP_ALIVE": "1",
        "HYPRDECK_SETTINGS_DEBUG": "1",
        "HKS_SETTINGS_DEBUG": "1",
        "HYPRDECK_ROOT": str(repo_root),
        "HKS_ROOT": str(repo_root),
    }
    env.pop("HYPRDECK_START_HIDDEN", None)
    env.pop("HKS_START_HIDDEN", None)

    proc = subprocess.Popen(
        ["quickshell", "-p", str(shell_qml)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    captured_count = 0
    contact_count = 0
    try:
        if not _wait_ready(proc.pid):
            sys.stderr.write("capture_layout_matrix: Quickshell IPC did not become ready.\n")
            return 1
        _wait_services(proc.pid)

        for page_id, sub_tab in CAPTURE_PAGES:
            page_pngs: list[Path] = []
            for w, h in CAPTURE_SIZES:
                subprocess.run(
                    [
                        "quickshell",
                        "ipc",
                        "--pid",
                        str(proc.pid),
                        "call",
                        "settings",
                        "debugConfigureLayoutProbe",
                        str(w),
                        str(h),
                        page_id,
                        sub_tab,
                        "false",
                        "false",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                time.sleep(0.10)
                png_path = out_dir / f"{page_id}-{w}x{h}.png"
                if png_path.exists():
                    png_path.unlink()

                grab_res = subprocess.run(
                    [
                        "quickshell",
                        "ipc",
                        "--pid",
                        str(proc.pid),
                        "call",
                        "settings",
                        "debugGrabWindowToFile",
                        str(png_path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                grab_data = json.loads(grab_res.stdout.strip())
                if not grab_data.get("ok"):
                    sys.stderr.write(f"capture_layout_matrix: grab failed to start for {png_path.name}: {grab_data}\n")
                    return 1
                target_seq = int(grab_data.get("seq", 0))

                saved_ok = False
                for _ in range(40):
                    st_res = subprocess.run(
                        ["quickshell", "ipc", "--pid", str(proc.pid), "call", "settings", "debugGrabStatus"],
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    st_data = json.loads(st_res.stdout.strip())
                    status_str = str(st_data.get("status", ""))
                    if int(st_data.get("seq", 0)) >= target_seq and status_str.startswith(f"ok:{target_seq}:"):
                        saved_ok = True
                        break
                    if status_str.startswith(f"fail:{target_seq}:"):
                        break
                    time.sleep(0.05)

                dims = _png_dimensions(png_path)
                if not saved_ok or not png_path.exists() or png_path.stat().st_size == 0 or dims is None:
                    sys.stderr.write(
                        f"capture_layout_matrix: invalid screenshot {png_path.name} (saved_ok={saved_ok}, dims={dims})\n"
                    )
                    return 1
                captured_count += 1
                page_pngs.append(png_path)

            if has_montage and page_pngs:
                contact_path = out_dir / f"contact-{page_id}.png"
                cmd = [
                    montage_bin,
                    *[str(p) for p in page_pngs],
                    "-tile",
                    f"{len(page_pngs)}x1",
                    "-geometry",
                    "380x260+8+8",
                    "-background",
                    "#0b0e10",
                    "-border",
                    "1",
                    "-bordercolor",
                    "#2b303b",
                    str(contact_path),
                ]
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
                if not contact_path.exists() or contact_path.stat().st_size == 0:
                    sys.stderr.write(f"capture_layout_matrix: failed writing {contact_path}\n")
                    return 1
                contact_count += 1
    finally:
        proc.terminate()
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=5)

    print(f"capture_layout_matrix: wrote {captured_count} PNGs and {contact_count} contact sheets in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
