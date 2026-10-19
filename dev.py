#!/usr/bin/env python3
"""Development entry point for the verified Delphi corpus workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = Path("evidence/fpc-compiler-tests-manifest.json")
DEFAULT_DIGEST = Path("tmp/fpc-compiler-tests-digest.txt")
DEFAULT_RUN = Path("evidence/fpc-compiler-tests-quick-run.json")
DEFAULT_TRIAGE = Path("evidence/fpc-compiler-tests-triage.json")
DEFAULT_CANDIDATES = Path("evidence/fpc-source-candidates.sqlite3")
PYTHON = "python3"


def repository_path(value: str) -> Path:
    """Return a repository-contained output path, rejecting local absolute paths."""
    path = Path(value)
    if path.is_absolute():
        raise argparse.ArgumentTypeError("output paths must be repository-relative")
    resolved = (ROOT / path).resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "output paths must stay inside this repository"
        ) from error
    return resolved


def command_plan(name: str, commands: Sequence[Sequence[str]]) -> dict[str, Any]:
    return {
        "command": name,
        "status": "dry-run",
        "corpus_location": "explicit argument; not persisted",
        "commands": [list(command) for command in commands],
    }


def emit(data: dict[str, Any], stream: Any = sys.stdout) -> None:
    print(json.dumps(data, indent=2, sort_keys=True), file=stream)


def invoke(command: Sequence[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def failure(name: str, detail: str, output: str | None = None) -> int:
    result: dict[str, Any] = {
        "command": name,
        "conversion_evidence": "none",
        "status": "harness_setup_failure",
        "detail": detail,
    }
    if output:
        result["diagnostic_output"] = output[-4_000:]
    emit(result, stream=sys.stderr)
    return 2


def readiness(_: argparse.Namespace) -> int:
    result = invoke([PYTHON, "tools/toolchain_report.py"], cwd=ROOT)
    if result.returncode:
        return failure("readiness", "the compiler readiness probe could not run")
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        return failure("readiness", "the compiler readiness probe produced invalid JSON")
    emit(
        {
            "command": "readiness",
            "status": report.get("validation_status", "unknown"),
            "compiler_report": report,
        }
    )
    return 0


def bootstrap_corpus_commands(args: argparse.Namespace) -> list[list[str]]:
    return [
        ["bash", "tools/bootstrap_fpc_test_corpus.sh", str(args.corpus_dir)],
        [
            PYTHON,
            "tools/record_fpc_compiler_test_corpus.py",
            "--root",
            str(args.corpus_dir),
            "--output",
            str(args.manifest.relative_to(ROOT)),
        ],
    ]


def bootstrap_corpus(args: argparse.Namespace) -> int:
    commands = bootstrap_corpus_commands(args)
    if args.dry_run:
        emit(command_plan("bootstrap-corpus", commands))
        return 0
    result = invoke(commands[0], cwd=ROOT)
    if result.returncode:
        return failure("bootstrap-corpus", "the upstream corpus bootstrap did not complete")
    manifest = invoke(commands[1], cwd=ROOT)
    if manifest.returncode:
        return failure("bootstrap-corpus", "the corpus manifest could not be recorded")
    emit(
        {
            "command": "bootstrap-corpus",
            "conversion_evidence": "none",
            "status": "harness_setup_completed",
        }
    )
    return 0


def bootstrap_runtime_commands(args: argparse.Namespace) -> list[list[str]]:
    return [
        [
            "bash",
            "tools/bootstrap_fpc_runtime.sh",
            str(args.corpus_dir),
            str(args.install_dir),
            args.host_fpc,
            str(args.workers),
        ]
    ]


def bootstrap_runtime(args: argparse.Namespace) -> int:
    commands = bootstrap_runtime_commands(args)
    if args.dry_run:
        emit(command_plan("bootstrap-runtime", commands))
        return 0
    result = invoke(commands[0], cwd=ROOT)
    if result.returncode:
        return failure(
            "bootstrap-runtime",
            "the self-hosted FPC runtime bootstrap did not complete",
            (result.stdout or "") + (result.stderr or ""),
        )
    emit(
        {
            "command": "bootstrap-runtime",
            "conversion_evidence": "none",
            "status": "harness_runtime_completed",
            "runtime_compiler": str(args.install_dir / "bin" / "sourcebridge-fpc"),
        }
    )
    return 0


def run_corpus_commands(args: argparse.Namespace) -> list[list[str]]:
    return [
        [
            "make",
            "clean",
            f"TEST_FPC={args.fpc}",
        ],
        [
            "make",
            f"-j{args.workers}",
            "full",
            f"TEST_FPC={args.fpc}",
            f"PP={args.fpc}",
            "QUICKTEST=1",
        ],
        [
            PYTHON,
            "tools/record_fpc_compiler_test_run.py",
            "--manifest",
            str(args.manifest.relative_to(ROOT)),
            "--digest",
            str(args.digest.relative_to(ROOT)),
            "--workers",
            str(args.workers),
            "--fpc",
            args.fpc,
            "--output",
            str(args.output.relative_to(ROOT)),
        ],
    ]


def run_corpus(args: argparse.Namespace) -> int:
    commands = run_corpus_commands(args)
    if args.dry_run:
        emit(command_plan("run-corpus", commands))
        return 0

    try:
        cleanup = invoke(commands[0], cwd=args.corpus_dir / "tests")
        if cleanup.returncode:
            return failure(
                "run-corpus",
                "the upstream harness cleanup did not complete",
                (cleanup.stdout or "") + (cleanup.stderr or ""),
            )
        result = invoke(commands[1], cwd=args.corpus_dir / "tests")
    except OSError:
        return failure("run-corpus", "the upstream harness could not be started")

    args.digest.parent.mkdir(parents=True, exist_ok=True)
    args.digest.write_text(
        (result.stdout or "") + (result.stderr or ""), encoding="utf-8"
    )
    record = invoke(commands[2], cwd=ROOT)
    if record.returncode:
        return failure(
            "run-corpus",
            "the harness output could not be recorded as structured evidence",
        )
    emit(
        {
            "command": "run-corpus",
            "conversion_evidence": "none",
            "harness_exit_code": result.returncode,
            "status": "harness_evidence_recorded",
        }
    )
    return 0


def triage_corpus_commands(args: argparse.Namespace) -> list[list[str]]:
    return [
        [
            PYTHON,
            "tools/build_fpc_corpus_triage_queue.py",
            "--output-dir",
            str(args.corpus_dir / "tests" / "output" / args.target),
            "--output",
            str(args.output.relative_to(ROOT)),
        ]
    ]


def triage_corpus(args: argparse.Namespace) -> int:
    commands = triage_corpus_commands(args)
    if args.dry_run:
        emit(command_plan("triage-corpus", commands))
        return 0
    result = invoke(commands[0], cwd=ROOT)
    if result.returncode:
        return failure("triage-corpus", "the harness failure list could not be triaged")
    emit(
        {
            "command": "triage-corpus",
            "conversion_evidence": "none",
            "status": "harness_triage_recorded",
        }
    )
    return 0


def find_next_rule(args: argparse.Namespace) -> int:
    """Report the top-ranked conversion-rule candidate from the triaged queue.

    This is the documented rule selector: it reads the persisted, already
    ollama-triaged FPC source-candidate queue and returns the single highest
    priority accepted candidate using the harness' own deterministic ranking
    (tests/ paths first, then rtl/, then source order). It calls no model and
    spends no new tokens; identification is a pure read over existing evidence.
    """

    import sqlite3

    database = args.database
    if not database.is_file():
        return failure(
            "find-next-rule",
            f"{database}: candidate queue not found; populate it with the "
            "source-candidate harness first",
        )
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from run_fpc_source_candidates import _priority
    except Exception:  # pragma: no cover - import guard
        return failure("find-next-rule", "the candidate selector could not be loaded")
    connection = sqlite3.connect(database)
    try:
        rows = [
            json.loads(value)
            for (value,) in connection.execute(
                "SELECT candidate_json FROM fpc_source_candidate WHERE outcome = 'candidate'"
            )
        ]
        tokens = connection.execute(
            "SELECT COALESCE(SUM(prompt_tokens), 0), COALESCE(SUM(generated_tokens), 0), "
            "COUNT(*) FROM fpc_source_candidate WHERE outcome = 'candidate'"
        ).fetchone()
    finally:
        connection.close()
    if not rows:
        emit(
            {
                "command": "find-next-rule",
                "status": "empty",
                "detail": "no accepted candidates remain in the triaged queue",
            }
        )
        return 0
    rows.sort(
        key=lambda item: (
            *_priority(item["source_path"]),
            item["line"],
            item["signature"],
            item["id"],
        )
    )
    top = rows[0]
    emit(
        {
            "command": "find-next-rule",
            "status": "recommended",
            "selector": "deterministic priority over ollama-triaged FPC source candidates",
            "recommendation": {
                "candidate_id": top["id"],
                "source_path": top["source_path"],
                "line": top["line"],
                "symbol": top["symbol"],
                "signature": top["signature"],
                "selection_reason": top["selection_reason"],
            },
            "queue": {
                "accepted_candidates": tokens[2],
                "triage_tokens": {
                    "prompt": tokens[0],
                    "generated": tokens[1],
                    "model_host": "local ollama",
                    "cloud_cost": "none",
                },
            },
            "identification_cost": {
                "new_tokens": 0,
                "note": "pure read over the persisted candidate queue; no model call",
            },
        }
    )
    return 0


def describe(_: argparse.Namespace) -> int:
    emit(
        {
            "schema_version": 1,
            "entry_point": "python3 dev.py",
            "commands": {
                "readiness": {
                    "description": "Probe compiler readiness without provisioning.",
                    "side_effects": "none",
                },
                "bootstrap-corpus": {
                    "description": "Bootstrap the pinned upstream corpus.",
                    "required_arguments": ["--corpus-dir"],
                    "dry_run": True,
                },
                "bootstrap-runtime": {
                    "description": "Build a self-hosted FPC runtime from the pinned corpus.",
                    "required_arguments": ["--corpus-dir", "--install-dir"],
                    "dry_run": True,
                    "conversion_evidence": "none",
                },
                "run-corpus": {
                    "description": "Run the upstream harness and record its evidence.",
                    "required_arguments": ["--corpus-dir"],
                    "dry_run": True,
                    "conversion_evidence": "none",
                },
                "triage-corpus": {
                    "description": "Classify upstream harness failures for follow-up.",
                    "required_arguments": ["--corpus-dir"],
                    "dry_run": True,
                    "conversion_evidence": "none",
                },
                "find-next-rule": {
                    "description": "Report the top-ranked conversion-rule candidate from the triaged queue.",
                    "optional_arguments": ["--database"],
                    "token_cost": "none (pure read of persisted evidence)",
                },
            },
            "conversion_evidence_and_reports": {
                "owner": "sourcebridge engine (not this pack)",
                "record": "sourcebridge record-catalogue-census --profile <profile.json> --catalogue engine-tests.json --curriculum rule-curriculum.json",
                "report": "sourcebridge report-conversion-census / report-diagnostics",
            },
            "path_policy": {
                "corpus": "explicit argument; never written to evidence",
                "outputs": "repository-relative only",
            },
        }
    )
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subcommands = result.add_subparsers(dest="subcommand", required=True)

    describe_parser = subcommands.add_parser("describe")
    describe_parser.set_defaults(handler=describe)
    readiness_parser = subcommands.add_parser("readiness")
    readiness_parser.set_defaults(handler=readiness)

    bootstrap = subcommands.add_parser("bootstrap-corpus")
    bootstrap.add_argument("--corpus-dir", type=Path, required=True)
    bootstrap.add_argument(
        "--manifest", type=repository_path, default=ROOT / DEFAULT_MANIFEST
    )
    bootstrap.add_argument("--dry-run", action="store_true")
    bootstrap.set_defaults(handler=bootstrap_corpus)

    runtime = subcommands.add_parser("bootstrap-runtime")
    runtime.add_argument("--corpus-dir", type=Path, required=True)
    runtime.add_argument("--install-dir", type=Path, required=True)
    runtime.add_argument("--host-fpc", default="fpc")
    runtime.add_argument("--workers", type=int, default=32)
    runtime.add_argument("--dry-run", action="store_true")
    runtime.set_defaults(handler=bootstrap_runtime)

    run = subcommands.add_parser("run-corpus")
    run.add_argument("--corpus-dir", type=Path, required=True)
    run.add_argument("--fpc", default="fpc")
    run.add_argument("--workers", type=int, default=32)
    run.add_argument("--manifest", type=repository_path, default=ROOT / DEFAULT_MANIFEST)
    run.add_argument("--digest", type=repository_path, default=ROOT / DEFAULT_DIGEST)
    run.add_argument("--output", type=repository_path, default=ROOT / DEFAULT_RUN)
    run.add_argument("--dry-run", action="store_true")
    run.set_defaults(handler=run_corpus)

    triage = subcommands.add_parser("triage-corpus")
    triage.add_argument("--corpus-dir", type=Path, required=True)
    triage.add_argument("--target", default="x86_64-linux")
    triage.add_argument("--output", type=repository_path, default=ROOT / DEFAULT_TRIAGE)
    triage.add_argument("--dry-run", action="store_true")
    triage.set_defaults(handler=triage_corpus)

    find = subcommands.add_parser("find-next-rule")
    find.add_argument("--database", type=repository_path, default=ROOT / DEFAULT_CANDIDATES)
    find.set_defaults(handler=find_next_rule)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if getattr(args, "workers", 1) < 1:
        parser().error("--workers must be positive")
    if getattr(args, "timeout", 1) < 1:
        parser().error("--timeout must be positive")
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
