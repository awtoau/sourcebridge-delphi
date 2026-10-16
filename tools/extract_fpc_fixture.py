#!/usr/bin/env python3
"""Extract source facts carrying the pinned FPC variant identity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sourcebridge_delphi.extract import extract


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=Path("fixtures/scalars.pas"))
    parser.add_argument(
        "--variant",
        type=Path,
        default=Path("variants/fpc-3.2.3-x86_64-linux.json"),
    )
    args = parser.parse_args()
    print(json.dumps(extract(args.fixture, args.variant), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
