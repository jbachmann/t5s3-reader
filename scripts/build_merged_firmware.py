#!/usr/bin/env python3
"""Build a PlatformIO environment and create a single flashable firmware image."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def local_tool(name: str) -> str | None:
    candidate = REPO_ROOT / ".venv" / "bin" / name
    if candidate.exists():
        return str(candidate)
    return shutil.which(name)


def platformio_core_dir() -> Path:
    return Path(os.environ.get("PLATFORMIO_CORE_DIR", Path.home() / ".platformio")).expanduser()


def app_offset() -> str:
    platformio_ini = REPO_ROOT / "platformio.ini"
    match = re.search(r"^\s*board_upload\.offset_address\s*=\s*(0x[0-9a-fA-F]+|\d+)\s*$", platformio_ini.read_text(),
                      re.MULTILINE)
    return match.group(1) if match else "0x10000"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and merge T5S3 firmware into one bin flashable at 0x0.")
    parser.add_argument("-e", "--environment", default="default", help="PlatformIO environment to build")
    parser.add_argument("-o", "--output", help="Output merged bin path")
    parser.add_argument("--no-build", action="store_true", help="Only merge existing build artifacts")
    args = parser.parse_args()

    pio = local_tool("pio")
    python = local_tool("python") or sys.executable
    if pio is None and not args.no_build:
        print(
            "Could not find pio. Try: python3 -m venv .venv && .venv/bin/python -m pip install platformio==6.1.19",
            file=sys.stderr,
        )
        return 1

    build_dir = REPO_ROOT / ".pio" / "build" / args.environment
    output = Path(args.output) if args.output else build_dir / "firmware-merged.bin"
    if not output.is_absolute():
        output = REPO_ROOT / output

    if not args.no_build:
        run([pio, "run", "-e", args.environment])

    bootloader = build_dir / "bootloader.bin"
    partitions = build_dir / "partitions.bin"
    firmware = build_dir / "firmware.bin"
    missing = [path for path in (bootloader, partitions, firmware) if not path.exists()]
    if missing:
        print("Missing build artifact(s):", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        return 1

    esptool = platformio_core_dir() / "packages" / "tool-esptoolpy" / "esptool.py"
    if not esptool.exists():
        print(f"Could not find esptool.py at {esptool}. Run the PlatformIO build first.", file=sys.stderr)
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    run([
        python,
        str(esptool),
        "--chip",
        "esp32s3",
        "merge_bin",
        "-o",
        str(output),
        "--flash_mode",
        "qio",
        "--flash_size",
        "16MB",
        "0x0",
        str(bootloader),
        "0x8000",
        str(partitions),
        app_offset(),
        str(firmware),
    ])

    print(f"\nMerged firmware ready: {output.relative_to(REPO_ROOT)}")
    print("Flash this merged image at offset 0x0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
