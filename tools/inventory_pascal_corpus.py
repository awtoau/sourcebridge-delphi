#!/usr/bin/env python3
"""Inventory the whole FPC source corpus without claiming semantic extraction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

try:  # Supports both `python tools/...` and package-style test imports.
    from tools.record_fpc_source_corpus import source_files
except ModuleNotFoundError:
    from record_fpc_source_corpus import source_files


SUPPORTED_FUNCTION = re.compile(
    r"^\s*function\s+[A-Za-z_][A-Za-z0-9_]*\([^)]*\)\s*:\s*(Integer|Cardinal)\s*;",
    re.IGNORECASE,
)


def inventory(root: Path) -> dict[str, int]:
    files = source_files(root)
    supported_signatures = 0
    lines = 0
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        file_lines = text.splitlines()
        lines += len(file_lines)
        supported_signatures += sum(
            SUPPORTED_FUNCTION.match(line) is not None for line in file_lines
        )
    return {
        "source_files": len(files),
        "source_lines": lines,
        "stage1_scalar_signature_candidates": supported_signatures,
        "status": "discovery-only; candidates are not extracted facts or validated rules",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/usr/share/fpcsrc"))
    args = parser.parse_args()
    try:
        print(json.dumps(inventory(args.root.resolve()), indent=2, sort_keys=True))
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0
