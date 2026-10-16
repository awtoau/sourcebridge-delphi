#!/usr/bin/env python3
"""Compile the Stage-1 fixture with the pinned Free Pascal variant."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys


def _run(arguments: list[str]) -> str:
    result = subprocess.run(arguments, check=False, capture_output=True, text=True)
    if result.returncode:
        raise ValueError((result.stdout + result.stderr).strip())
    return result.stdout.strip()


def validate(variant_path: Path, fixture: Path, output_directory: Path) -> None:
    if shutil.which("fpc") is None:
        raise ValueError("Free Pascal (`fpc`) is required")
    variant = json.loads(variant_path.read_text(encoding="utf-8"))
    compiler = variant["compiler"]
    version = _run(["fpc", "-iV"])
    target_cpu = _run(["fpc", "-iTP"])
    target_os = _run(["fpc", "-iTO"])
    expected = {
        "version": compiler["version"],
        "target_cpu": compiler["target_cpu"],
        "target_os": compiler["target_os"],
    }
    actual = {"version": version, "target_cpu": target_cpu, "target_os": target_os}
    if actual != expected:
        raise ValueError(f"FPC variant mismatch: expected {expected}, got {actual}")
    output_directory.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["fpc", "-Mdelphi", f"-FU{output_directory}", f"-FE{output_directory}", str(fixture)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ValueError((result.stdout + result.stderr).strip())
    print(json.dumps(
        {
            "fixture": fixture.as_posix(),
            "variant": variant_path.as_posix(),
            "compiler": actual,
            "status": "passed",
            "output": result.stdout.strip(),
        },
        indent=2,
        sort_keys=True,
    ))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant",
        type=Path,
        default=Path("variants/fpc-3.2.3-x86_64-linux.json"),
    )
    parser.add_argument("--fixture", type=Path, default=Path("fixtures/scalars.pas"))
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/fpc"))
    args = parser.parse_args()
    try:
        validate(args.variant, args.fixture, args.output_dir)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
