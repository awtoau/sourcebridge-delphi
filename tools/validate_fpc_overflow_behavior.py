#!/usr/bin/env python3
"""Observe default FPC overflow behavior for the pinned scalar variant."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

from fpc_runtime import rtl_arguments


EXPECTED_OUTPUT = [
    "SignedOverflow=-2147483648",
    "UnsignedOverflow=0",
]


def validate(fixture: Path, output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    compilation = subprocess.run(
        ["fpc", "-Mdelphi", *rtl_arguments(), f"-FE{output_directory}", str(fixture)],
        check=False,
        capture_output=True,
        text=True,
    )
    if compilation.returncode:
        raise ValueError((compilation.stdout + compilation.stderr).strip())
    execution = subprocess.run(
        [str(output_directory / fixture.stem)],
        check=False,
        capture_output=True,
        text=True,
    )
    if execution.returncode:
        raise ValueError((execution.stdout + execution.stderr).strip())
    output = execution.stdout.splitlines()
    if output != EXPECTED_OUTPUT:
        raise ValueError(f"unexpected default overflow behavior: {output!r}")
    print(execution.stdout, end="")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=Path("fixtures/scalar_overflow.pas"))
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/fpc-overflow"))
    args = parser.parse_args()
    try:
        validate(args.fixture, args.output_dir)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
