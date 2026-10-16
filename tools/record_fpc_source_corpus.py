#!/usr/bin/env python3
"""Record an attributed whole-tree manifest for Fedora's Free Pascal sources."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


SOURCE_SUFFIXES = {".pas", ".pp", ".lpr"}


def package_version() -> str:
    result = subprocess.run(
        ["rpm", "-q", "fpc-src"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ValueError("Fedora package `fpc-src` is required")
    return result.stdout.strip()


def source_files(root: Path) -> list[Path]:
    files = sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.casefold() in SOURCE_SUFFIXES
    )
    if not files:
        raise ValueError(f"{root}: contains no Pascal source files")
    return files


def digest(root: Path, files: list[Path]) -> str:
    content = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content.update(relative)
        content.update(b"\0")
        content.update(path.read_bytes())
        content.update(b"\0")
    return content.hexdigest()


def manifest(root: Path) -> dict[str, object]:
    files = source_files(root)
    suffix_counts = {
        suffix: sum(path.suffix.casefold() == suffix for path in files)
        for suffix in sorted(SOURCE_SUFFIXES)
    }
    return {
        "schema_version": 1,
        "source_name": "fedora-fpc-src",
        "source_package": package_version(),
        "source_root": root.as_posix(),
        "scope": "all .pas, .pp, and .lpr files under the installed fpc-src tree",
        "file_count": len(files),
        "suffix_counts": suffix_counts,
        "tree_sha256": digest(root, files),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/usr/share/fpcsrc"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        data = manifest(args.root.resolve())
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    output = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0
