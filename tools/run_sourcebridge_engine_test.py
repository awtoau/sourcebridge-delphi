#!/usr/bin/env python3
"""Emit a Sourcebridge JSON engine-test result for one Delphi fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VARIANT = ROOT / "variants" / "fpc-3.2.3-x86_64-linux.json"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from record_fpc_compiler_test_run import compiler_identity
from sourcebridge_delphi.extract import ExtractionError, extract
from sourcebridge_delphi.emit_rust import RustEmissionError, emit


def _status(status: str, **details: Any) -> dict[str, Any]:
    return {"status": status, **details}


def _variant(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{path}: cannot read FPC variant: {error}") from error
    if not isinstance(value, dict) or not isinstance(value.get("compiler"), dict):
        raise ValueError(f"{path}: FPC variant must contain a compiler object")
    return value


def _compiler_status(fpc: str, variant: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str] | None]:
    expected = variant["compiler"]
    try:
        actual = compiler_identity(fpc)
    except (OSError, ValueError) as error:
        return _status(
            "blocked",
            reason="the configured FPC compiler is unavailable",
            compiler=fpc,
            diagnostic=str(error),
        ), None
    required = {
        "version": expected.get("version"),
        "target_cpu": expected.get("target_cpu"),
        "target_os": expected.get("target_os"),
    }
    if actual != required:
        return _status(
            "blocked",
            reason="the configured FPC compiler does not match the pinned variant",
            compiler=fpc,
            expected_compiler=required,
            actual_compiler=actual,
        ), actual
    return _status("ready", compiler=fpc, actual_compiler=actual), actual


def _compile(
    fixture: Path, fpc: str, variant: dict[str, Any], output_directory: Path
) -> dict[str, Any]:
    compiler, actual = _compiler_status(fpc, variant)
    if compiler["status"] != "ready":
        return compiler
    rtl_path = _installed_rtl_path(actual)
    command = [
        fpc,
        "-Mdelphi",
    ]
    if rtl_path is not None:
        command.append(f"-Fu{rtl_path}")
    command.extend(
        [
            f"-FU{output_directory}",
            f"-FE{output_directory}",
            str(fixture),
        ]
    )
    result = subprocess.run(
        command,
        cwd=fixture.parent,
        check=False,
        capture_output=True,
        text=True,
    )
    details: dict[str, Any] = {
        "compiler": fpc,
        "compiler_identity": actual,
        "command": command,
    }
    if result.returncode:
        details["diagnostic"] = (result.stdout + result.stderr).strip()[-4_000:]
        return _status("failed", **details)
    return _status("passed", **details)


def _installed_rtl_path(identity: dict[str, str] | None) -> Path | None:
    if identity is None:
        return None
    target = f"{identity['target_cpu']}-{identity['target_os']}"
    candidates = (
        Path("/usr/lib64/fpc") / identity["version"] / "units" / target / "rtl",
        Path("/usr/lib/fpc") / identity["version"] / "units" / target / "rtl",
    )
    for candidate in candidates:
        if (candidate / "system.ppu").is_file():
            return candidate
    return None


def _compile_rust(facts: dict[str, Any], output_directory: Path) -> dict[str, Any]:
    rustc = shutil.which("rustc")
    if rustc is None:
        return _status("blocked", reason="Rust compiler (`rustc`) is unavailable")
    try:
        artifact = emit(facts)
    except RustEmissionError as error:
        return _status("blocked", reason=str(error))
    source = output_directory / "generated.rs"
    library = output_directory / "generated.rlib"
    source.write_text(artifact, encoding="utf-8")
    command = [rustc, "--edition", "2021", "--crate-type", "lib", str(source), "-o", str(library)]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    details = {
        "compiler": rustc,
        "command": command,
        "artifact_path": source.name,
        "artifact_digest": hashlib.sha256(artifact.encode("utf-8")).hexdigest(),
    }
    if result.returncode:
        return _status("failed", diagnostic=(result.stdout + result.stderr).strip()[-4_000:], **details)
    return _status("passed", **details)


def run_test(fixture: Path, variant_path: Path, fpc: str) -> dict[str, Any]:
    variant = _variant(variant_path)
    source: dict[str, Any]
    extraction: dict[str, Any]
    with tempfile.TemporaryDirectory(prefix="sourcebridge-delphi-engine-test-") as output:
        source = _compile(fixture, fpc, variant, Path(output))
        try:
            facts = extract(fixture, variant_path)
        except (ExtractionError, OSError, ValueError) as error:
            extraction = _status("failed", diagnostic=str(error))
        else:
            extraction = _status(
                "passed",
                fact_count=len(facts["facts"]),
                functions=[fact["name"] for fact in facts["facts"]],
                variant=variant["compiler"],
            )
        target = (
            _compile_rust(facts, Path(output))
            if extraction["status"] == "passed"
            else _status("blocked", reason="source extraction did not produce target-emittable facts")
        )
    return {
        "schema_version": 1,
        "source": source,
        "extraction": extraction,
        "target": target,
        "oracle": _status(
            "skipped",
            reason="the fixture is a source unit without an executable source/target harness",
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--variant", type=Path, default=DEFAULT_VARIANT)
    parser.add_argument("--fpc", default=os.environ.get("SOURCEBRIDGE_FPC", "fpc"))
    args = parser.parse_args(argv)
    try:
        result = run_test(args.fixture.resolve(), args.variant.resolve(), args.fpc)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
