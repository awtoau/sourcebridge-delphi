#!/usr/bin/env python3
"""Build a structured triage queue from the upstream FPC harness failure list."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


MISSING_UNIT = re.compile(r"Fatal: Can't find unit (?P<unit>\S+) used by")


def classify(log: str) -> tuple[str, str]:
    missing = MISSING_UNIT.search(log)
    if missing is not None:
        return "missing_test_dependency", f"missing unit `{missing['unit']}`"
    for line in log.splitlines():
        if "Fatal:" in line or "Error:" in line:
            if "returned an error exitcode" not in line:
                return "compiler_or_runtime_diagnostic", line
    return "unclassified", "no diagnostic line found in harness log"


def build_queue(output_directory: Path) -> list[dict[str, str]]:
    failure_list = output_directory / "faillist"
    if not failure_list.is_file():
        raise ValueError(f"{failure_list}: upstream harness failure list is missing")
    queue: list[dict[str, str]] = []
    for test_path in failure_list.read_text(encoding="utf-8").splitlines():
        if not test_path:
            continue
        log_path = output_directory / f"{test_path}.log"
        if log_path.is_file():
            category, diagnostic = classify(log_path.read_text(encoding="utf-8", errors="replace"))
        else:
            category, diagnostic = "missing_harness_log", "no log file exists for failure-list entry"
        queue.append(
            {
                "test_path": test_path,
                "log_path": log_path.relative_to(output_directory).as_posix(),
                "category": category,
                "diagnostic": diagnostic,
            }
        )
    return queue


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        queue = build_queue(args.output_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(queue, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
