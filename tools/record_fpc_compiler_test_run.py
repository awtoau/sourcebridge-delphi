#!/usr/bin/env python3
"""Turn an upstream FPC digest report into durable structured evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


FIELDS = {
    "total": r"^Total = (\d+)",
    "compilations": r"^Total number of compilations = (\d+)",
    "compiled": r"^Successfully compiled = (\d+)",
    "expected_compile_failures": r"^Successfully failed = (\d+)",
    "unexpected_compile_failures": r"^Compilation failures = (\d+)",
    "unexpected_compile_successes": r"^Compilation that did not fail while they should = (\d+)",
    "runs": r"^Total number of runs = (\d+)",
    "successful_runs": r"^Successful runs = (\d+)",
    "unexpected_run_failures": r"^Failed runs = (\d+)",
    "skipped": r"^Number of skipped tests = (\d+)",
}


def parse_digest(text: str) -> dict[str, int]:
    summary: dict[str, int] = {}
    for field, pattern in FIELDS.items():
        match = re.search(pattern, text, flags=re.MULTILINE)
        if match is None:
            raise ValueError(f"digest report is missing `{field}`")
        summary[field] = int(match.group(1))
    return summary


def compiler_identity(fpc: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for field, argument in (
        ("version", "-iV"),
        ("target_cpu", "-iTP"),
        ("target_os", "-iTO"),
    ):
        result = subprocess.run(
            [fpc, argument],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise ValueError(f"cannot read FPC {field} from `{fpc}`")
        values[field] = result.stdout.strip()
    return values


def record(manifest_path: Path, digest_path: Path, workers: int, fpc: str) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("corpus manifest must be an object")
    return {
        "schema_version": 1,
        "corpus": {
            "source_name": manifest["source_name"],
            "source_remote": manifest["source_remote"],
            "source_revision": manifest["source_revision"],
            "tree_sha256": manifest["tree_sha256"],
        },
        "compiler": compiler_identity(fpc),
        "run": {
            "target": f"make full TEST_FPC={fpc} PP={fpc} QUICKTEST=1",
            "workers": workers,
            "summary": parse_digest(digest_path.read_text(encoding="utf-8")),
            "interpretation": (
                "The corpus revision is a compatibility candidate for the Fedora "
                "compiler, not an assumed exact source match. Unexpected outcomes "
                "are triage inputs, not converter-rule evidence."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--digest", type=Path, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--fpc", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.workers < 1:
        print("--workers must be positive", file=sys.stderr)
        return 1
    try:
        data = record(args.manifest, args.digest, args.workers, args.fpc)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
