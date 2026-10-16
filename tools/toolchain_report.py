#!/usr/bin/env python3
"""Report available Delphi-compatible compilers and provisioning guidance."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any


def os_release() -> dict[str, str]:
    path = Path("/etc/os-release")
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')
    return values


def command_version(command: str, arguments: list[str]) -> str | None:
    if shutil.which(command) is None:
        return None
    result = subprocess.run(
        [command, *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    output = (result.stdout or result.stderr).strip()
    return output if result.returncode == 0 else None


def install_guidance(platform_id: str) -> list[str]:
    if platform_id == "fedora":
        return ["sudo dnf install -y fpc"]
    if platform_id in {"debian", "ubuntu"}:
        return ["sudo apt-get update", "sudo apt-get install -y fp-compiler"]
    return [
        "Install Free Pascal through the host package manager.",
        "Or configure a licensed Embarcadero Delphi compiler and record its version.",
    ]


def report() -> dict[str, Any]:
    platform = os_release()
    fpc_path = shutil.which("fpc")
    return {
        "platform": {
            "id": platform.get("ID", "unknown"),
            "version_id": platform.get("VERSION_ID", "unknown"),
            "pretty_name": platform.get("PRETTY_NAME", "unknown"),
        },
        "compilers": {
            "fpc": {
                "path": fpc_path,
                "version": command_version("fpc", ["-iV"]),
                "target_cpu": command_version("fpc", ["-iTP"]),
                "target_os": command_version("fpc", ["-iTO"]),
            },
            "dcc32": {"path": shutil.which("dcc32")},
            "dcc64": {"path": shutil.which("dcc64")},
        },
        "install_guidance": install_guidance(platform.get("ID", "")),
        "validation_status": (
            "compiler-available" if fpc_path else "compiler-required"
        ),
    }


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, sort_keys=True))
