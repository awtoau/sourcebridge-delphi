#!/usr/bin/env python3
"""Run the active conversion rules across a whole source corpus.

For every Pascal source file this reports, as evidence:

- `extraction_unsupported`: the frontend grammar does not yet parse the file
  (a no-rule gap at the frontend);
- `no_emission_rule`: a fact was extracted but no active rule emits it (a
  backend no-rule gap);
- `target_compile_failed`: emitted Rust did NOT compile. This must never happen
  -- every emitted artifact is required to compile -- so each occurrence is a
  rule/interpreter defect and is listed individually;
- `emitted_and_compiled`: extracted, emitted, and the Rust compiled.

It deliberately does not FPC-compile the source: the question is which language
features the current rules cover and whether everything they emit compiles.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sourcebridge_delphi.extract import ExtractionError, extract
from sourcebridge_delphi.emit_rust import RustEmissionError, emit


def _load_rules() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "rules").glob("*.json"))]


def _first_line(text: str) -> str:
    return text.strip().splitlines()[0][:200] if text.strip() else ""


def sweep(corpus_dir: Path, rules: list[dict], *, limit: int | None, rustc: str | None) -> dict:
    files = sorted(
        p for p in corpus_dir.rglob("*") if p.suffix.lower() in {".pp", ".pas", ".lpr"}
    )
    if limit is not None:
        files = files[:limit]

    outcomes: Counter[str] = Counter()
    extraction_gaps: Counter[str] = Counter()
    emission_gaps: Counter[str] = Counter()
    compile_failures: list[dict] = []
    passed_files: list[str] = []

    for path in files:
        relative = path.relative_to(corpus_dir).as_posix()
        try:
            facts = extract(path)
        except (ExtractionError, OSError, ValueError) as error:
            outcomes["extraction_unsupported"] += 1
            extraction_gaps[_classify_extraction(str(error))] += 1
            continue
        try:
            artifact = emit(facts, rules)
        except RustEmissionError as error:
            outcomes["no_emission_rule"] += 1
            emission_gaps[_first_line(str(error))] += 1
            continue
        if rustc is None:
            outcomes["emitted_compiler_unavailable"] += 1
            continue
        with tempfile.TemporaryDirectory(prefix="sourcebridge-sweep-") as tmp:
            source = Path(tmp) / "generated.rs"
            source.write_text(artifact, encoding="utf-8")
            result = subprocess.run(
                [rustc, "--edition", "2021", "--crate-type", "lib", str(source),
                 "-o", str(Path(tmp) / "out.rlib")],
                check=False, capture_output=True, text=True,
            )
        if result.returncode:
            outcomes["target_compile_failed"] += 1
            compile_failures.append({
                "file": relative,
                "diagnostic": (result.stdout + result.stderr).strip()[-1500:],
            })
        else:
            outcomes["emitted_and_compiled"] += 1
            passed_files.append(relative)

    return {
        "schema_version": 1,
        "corpus_dir": str(corpus_dir),
        "files_swept": len(files),
        "outcomes": dict(sorted(outcomes.items())),
        "extraction_gap_signatures": dict(extraction_gaps.most_common()),
        "emission_gap_signatures": dict(emission_gaps.most_common()),
        "target_compile_failures": compile_failures,
        "emitted_and_compiled_files": passed_files,
        "invariant_all_emitted_rust_compiles": not compile_failures,
    }


def _classify_extraction(message: str) -> str:
    # Collapse line-number noise into a stable signature for grouping.
    lowered = message.lower()
    if "missing unit declaration" in lowered or "no supported" in lowered:
        return "no-supported-construct"
    if "unsupported parameter" in lowered:
        return "unsupported-parameter-type"
    if "only `result" in lowered or "is supported" in lowered:
        return "unsupported-function-body"
    if "duplicate" in lowered:
        return "duplicate-declaration"
    return "other-grammar-gap"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not args.corpus_dir.is_dir():
        print(f"{args.corpus_dir}: corpus directory not found", file=sys.stderr)
        return 2
    report = sweep(
        args.corpus_dir.resolve(), _load_rules(),
        limit=args.limit, rustc=shutil.which("rustc"),
    )
    if args.output is not None:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["invariant_all_emitted_rust_compiles"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
