#!/usr/bin/env python3
"""Compile and run bounded scalar observations for the pinned FPC variant."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
import sys

from fpc_runtime import rtl_arguments

EXPECTED_OUTPUT = [
    "Integer=4",
    "Cardinal=4",
    "AddSigned=3",
    "AddUnsigned=3",
]


def validate(fixture: Path, output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["fpc", "-Mdelphi", *rtl_arguments(), f"-FE{output_directory}", str(fixture)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ValueError((result.stdout + result.stderr).strip())
    executable = output_directory / fixture.stem
    run = subprocess.run([str(executable)], check=False, capture_output=True, text=True)
    if run.returncode:
        raise ValueError((run.stdout + run.stderr).strip())
    output = run.stdout.splitlines()
    if output != EXPECTED_OUTPUT:
        raise ValueError(f"unexpected scalar behavior: {output!r}")
    print(run.stdout, end="")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=Path("fixtures/scalar_layout.pas"))
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/fpc-behavior"))
    args = parser.parse_args()
    try:
        validate(args.fixture, args.output_dir)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
