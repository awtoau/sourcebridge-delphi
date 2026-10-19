"""Compiler-grounded Delphi/FPC fact extraction via FPC's own parser.

This drives `tools/pasfacts.pas`, a program built on Free Pascal's official
source-parser library (`fcl-passrc`), the same way the C# pack uses Roslyn and
the C pack uses clang. It parses real Pascal into an AST and returns the fact
kinds the Sourcebridge rules consume — unlike the whole-file regex extractor,
it reads real programs, units, directives, and `var`/procedure structure.

The helper compiles `pasfacts` on demand into an ignored build directory,
caching by source digest, then invokes it per source file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from tools.fpc_runtime import rtl_unit_path

_ROOT = Path(__file__).resolve().parents[1]
_SOURCE = _ROOT / "tools" / "pasfacts.pas"
_BUILD = _ROOT / "tmp" / "pasfacts-build"


class PasFactsError(RuntimeError):
    """Raised when the compiler-grounded extractor cannot build or run."""


def _passrc_path() -> Path:
    rtl = rtl_unit_path()
    if rtl is None:
        raise PasFactsError("FPC RTL units not found; cannot locate fcl-passrc")
    candidate = rtl.parent / "fcl-passrc"
    if not (candidate / "pparser.ppu").is_file():
        raise PasFactsError(f"fcl-passrc not found next to the RTL at {candidate}")
    return candidate


def ensure_built() -> Path:
    """Compile pasfacts if missing or stale; return the executable path."""

    fpc = shutil.which("fpc")
    if fpc is None:
        raise PasFactsError("the Free Pascal compiler (`fpc`) is unavailable")
    digest = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()[:16]
    _BUILD.mkdir(parents=True, exist_ok=True)
    executable = _BUILD / f"pasfacts-{digest}"
    if executable.is_file():
        return executable
    rtl = rtl_unit_path()
    result = subprocess.run(
        [
            fpc, "-Mobjfpc", f"-FU{_BUILD}", f"-FE{_BUILD}",
            f"-Fu{_passrc_path()}", f"-Fu{rtl}",
            f"-o{executable}", str(_SOURCE),
        ],
        check=False, capture_output=True, text=True,
    )
    if result.returncode or not executable.is_file():
        raise PasFactsError(f"cannot build pasfacts: {(result.stdout + result.stderr).strip()[-2000:]}")
    return executable


def extract_facts(source: Path, *, program_body: bool = False) -> dict[str, Any]:
    """Parse a Pascal source file with FPC's parser and return its facts.

    When ``program_body`` is true the extractor also emits a structured
    ``program_body`` fact (the incremental statement inventory used by the
    porter). It is opt-in so the default function/unit pipeline is unchanged.
    """

    executable = ensure_built()
    command = [str(executable), str(source)]
    if program_body:
        command.append("--program-body")
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise PasFactsError(f"{source}: pasfacts did not emit JSON: {error}") from error
    if not payload.get("parsed", False):
        raise PasFactsError(f"{source}: parse failed: {payload.get('error', 'unknown')}")
    return payload
