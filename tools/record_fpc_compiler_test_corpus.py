#!/usr/bin/env python3
"""Record a whole-tree manifest for an upstream FPC compiler test checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


SOURCE_SUFFIXES = {".pas", ".pp", ".lpr", ".inc"}


def source_files(root: Path) -> list[Path]:
    files = sorted(
        path for path in root.rglob("*")
        if path.is_file()
        and path.suffix.casefold() in SOURCE_SUFFIXES
        and "output" not in path.relative_to(root).parts
    )
    if not files:
        raise ValueError(f"{root}: contains no Pascal test-source files")
    return files


def git_value(root: Path, arguments: list[str]) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ValueError(f"{root}: is not a readable Git test corpus")
    return result.stdout.strip()


def tree_digest(root: Path, files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def manifest(root: Path) -> dict[str, object]:
    files = source_files(root)
    return {
        "schema_version": 1,
        "source_name": "free-pascal-compiler-tests",
        "source_remote": git_value(root, ["remote", "get-url", "origin"]),
        "source_revision": git_value(root, ["rev-parse", "HEAD"]),
        "scope": "all Pascal test-source files below the upstream tests directory",
        "file_count": len(files),
        "suffix_counts": {
            suffix: sum(path.suffix.casefold() == suffix for path in files)
            for suffix in sorted(SOURCE_SUFFIXES)
        },
        "tree_sha256": tree_digest(root, files),
        "compiler_compatibility": (
            "candidate corpus for the Fedora FPC package; execute its harness "
            "to measure compatibility rather than assuming an exact match"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=os.environ.get("FPC_TEST_CORPUS"),
        required="FPC_TEST_CORPUS" not in os.environ,
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        data = manifest(args.root.resolve())
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    output = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(output, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
