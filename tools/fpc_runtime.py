"""Resolve the installed Free Pascal RTL for isolated fixture compiles."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess


def _identity(flag: str) -> str:
    result = subprocess.run(
        ["fpc", flag], check=False, capture_output=True, text=True
    )
    if result.returncode:
        raise ValueError((result.stdout + result.stderr).strip())
    return result.stdout.strip()


def rtl_unit_path() -> Path | None:
    """Return a verified RTL unit directory when the user config omits it."""

    version = _identity("-iV")
    cpu = _identity("-iTP")
    operating_system = _identity("-iTO")
    configured = os.environ.get("SOURCEBRIDGE_FPC_RTL")
    roots = [Path(configured)] if configured else [
        Path("/usr/lib/fpc"),
        Path("/usr/lib64/fpc"),
    ]
    for root in roots:
        candidate = root / version / "units" / f"{cpu}-{operating_system}" / "rtl"
        if (candidate / "system.ppu").is_file():
            return candidate
    return None


def rtl_arguments() -> list[str]:
    """Return a portable explicit RTL search argument or fail clearly."""

    path = rtl_unit_path()
    if path is None:
        raise ValueError(
            "FPC RTL `system.ppu` was not found for the selected compiler; "
            "set SOURCEBRIDGE_FPC_RTL to its directory"
        )
    return [f"-Fu{path}"]
