#!/usr/bin/env python3
"""Create a deterministic inventory of the Delphi engine-test catalogue.

The optional Ollama call is deliberately an annotation step.  It cannot alter
the catalogue, adapter outcomes, or any Sourcebridge rule.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib import request


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ENRICHMENT_KEYS = {
    "language_features",
    "complexity_band",
    "prerequisites",
    "uncertainties",
}
PROMPT_TEMPLATE_VERSION = "delphi-engine-test-inventory/v1"
PROMPT_TEMPLATE_PATH = ROOT / "prompts" / "engine-test-inventory-v1.txt"


class OllamaEnrichmentError(RuntimeError):
    """An optional Ollama request failed or returned invalid annotation JSON."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def _status_map(value: dict[str, Any]) -> dict[str, Any]:
    return {name: value[name] for name in ("source", "extraction", "target", "oracle")}


def _adapter_command(catalogue: dict[str, Any], fixture: Path) -> list[str]:
    config = catalogue["adapter"]["config"]
    fixture_dir = fixture.parent
    substitutions = {
        "{fixture_dir}": str(fixture_dir),
        "{fixture_path}": str(fixture),
    }
    return [
        next((argument.replace(old, new) for old, new in substitutions.items() if old in argument), argument)
        for argument in config["argv"]
    ]


def run_adapter(
    catalogue: dict[str, Any], fixture: Path, timeout: int
) -> tuple[dict[str, Any] | None, str | None]:
    command = _adapter_command(catalogue, fixture)
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, str(error)
    if completed.returncode:
        diagnostic = (completed.stdout + completed.stderr).strip()[-4000:]
        return None, f"adapter exited {completed.returncode}: {diagnostic}"
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        return None, f"adapter did not emit JSON: {error}"
    if not isinstance(result, dict) or not all(
        key in result for key in ("source", "extraction", "target", "oracle")
    ):
        return None, "adapter JSON lacks structured source/extraction/target/oracle statuses"
    return result, None


def _prompt(
    case: dict[str, Any],
    fixture_text: str,
    digest: str,
    statuses: dict[str, Any],
    template: str | None = None,
) -> str:
    facts = {
        "test_id": case["id"],
        "name": case["name"],
        "fixture_path": case["fixture"],
        "fixture_sha256": digest,
        "adapter_statuses": statuses,
    }
    template = template or PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    return template.format(
        deterministic_facts=json.dumps(facts, sort_keys=True),
        fixture_source=fixture_text,
    )


def enrich(
    endpoint: str,
    model: str,
    model_digest: str,
    prompt: str,
    prompt_template_digest: str,
    timeout: int = 60,
) -> dict[str, Any]:
    payload = json.dumps(
        {"model": model, "prompt": prompt, "stream": False, "format": "json"}
    ).encode("utf-8")
    req = request.Request(
        endpoint.rstrip("/") + "/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    envelope = json.loads(raw)
    model_response = envelope.get("response")
    if not isinstance(model_response, str):
        raise ValueError("Ollama response lacks a string response field")
    annotation = json.loads(model_response)
    if (
        not isinstance(annotation, dict)
        or set(annotation) != REQUIRED_ENRICHMENT_KEYS
        or not isinstance(annotation["language_features"], list)
        or not isinstance(annotation["complexity_band"], str)
        or not isinstance(annotation["prerequisites"], list)
        or not isinstance(annotation["uncertainties"], list)
        or not all(isinstance(item, str) for key in REQUIRED_ENRICHMENT_KEYS - {"complexity_band"} for item in annotation[key])
    ):
        raise ValueError("Ollama response is not the required strict enrichment JSON")
    return {
        "authoritative": False,
        "annotation": annotation,
        "raw_response": model_response,
        "model": model,
        "model_digest": model_digest,
        "prompt_template_digest": prompt_template_digest,
        "prompt": prompt,
        "prompt_sha256": sha256_text(prompt),
    }


def build_report(
    catalogue_path: Path,
    *,
    ollama_endpoint: str | None = None,
    ollama_model: str | None = None,
    ollama_digest: str | None = None,
    prompt_template_path: Path = PROMPT_TEMPLATE_PATH,
    prompt_template_version: str = PROMPT_TEMPLATE_VERSION,
    timeout: int = 60,
) -> dict[str, Any]:
    catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
    prompt_template = prompt_template_path.read_text(encoding="utf-8")
    prompt_template_digest = sha256_text(prompt_template)
    tests: list[dict[str, Any]] = []
    for case in catalogue["tests"]:
        fixture = (catalogue_path.parent / case["fixture"]).resolve()
        fixture_bytes = fixture.read_bytes()
        digest = sha256_bytes(fixture_bytes)
        adapter, error = run_adapter(catalogue, fixture, timeout)
        if adapter is not None:
            statuses = _status_map(adapter)
            outcome_source = "structured_adapter"
        else:
            statuses = case["expected"]
            outcome_source = "catalogue_declared_outcome"
        entry: dict[str, Any] = {
            "id": case["id"],
            "name": case["name"],
            "fixture": case["fixture"],
            "fixture_sha256": digest,
            "statuses": statuses,
            "status_source": outcome_source,
        }
        if error:
            entry["adapter_error"] = error
        if ollama_endpoint is not None:
            prompt = _prompt(
                case,
                fixture_bytes.decode("utf-8"),
                digest,
                statuses,
                prompt_template,
            )
            try:
                entry["ollama"] = enrich(
                    ollama_endpoint,
                    ollama_model or "",
                    ollama_digest or "",
                    prompt,
                    prompt_template_digest,
                    timeout,
                )
            except (OSError, ValueError, json.JSONDecodeError) as error:
                raise OllamaEnrichmentError(
                    f"{case['id']} ({case['name']}): {error}"
                ) from error
        tests.append(entry)
    return {
        "schema_version": 1,
        "pack_id": catalogue["pack_id"],
        "catalogue": str(catalogue_path),
        "mode": "ollama-supplemental" if ollama_endpoint else "deterministic-only",
        "ollama_authority": "supplemental; non-authoritative; no rules, catalogue changes, or target-equivalence claims",
        "prompt_template_version": prompt_template_version,
        "prompt_template_digest": prompt_template_digest,
        "tests": tests,
    }


def write_evidence_records(report: dict[str, Any], directory: Path) -> list[Path]:
    if report["mode"] != "ollama-supplemental":
        raise ValueError("Ollama evidence records require --ollama-endpoint, --ollama-model, and --ollama-digest")
    written: list[Path] = []
    for test in report["tests"]:
        ollama = test["ollama"]
        model_digest = ollama["model_digest"]
        record = {
            "kind": "ollama_test_inventory",
            "pack_id": report["pack_id"],
            "test_id": test["id"],
            "fixture_path": test["fixture"],
            "fixture_sha256": test["fixture_sha256"],
            "model": {"name": ollama["model"], "digest": model_digest},
            "prompt_template_version": report["prompt_template_version"],
            "prompt_template_digest": ollama["prompt_template_digest"],
            "prompt": {"text": ollama["prompt"]},
            "prompt_sha256": ollama["prompt_sha256"],
            "raw_response": ollama["raw_response"],
            "inventory": ollama["annotation"],
            "statuses": test["statuses"],
            "status_source": test["status_source"],
        }
        path = directory / model_digest / ollama["prompt_template_digest"] / f"{test['id']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", type=Path, default=ROOT / "engine-tests.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ollama-endpoint")
    parser.add_argument("--ollama-model")
    parser.add_argument("--ollama-digest")
    parser.add_argument("--prompt-template", type=Path, default=PROMPT_TEMPLATE_PATH)
    parser.add_argument(
        "--prompt-template-version",
        default=PROMPT_TEMPLATE_VERSION,
        help="version label for the immutable prompt template used by this run",
    )
    parser.add_argument(
        "--evidence-directory",
        type=Path,
        help="write one importable Sourcebridge Ollama-inventory record per test",
    )
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args(argv)
    if bool(args.ollama_endpoint) != bool(args.ollama_model and args.ollama_digest):
        parser.error("--ollama-endpoint, --ollama-model, and --ollama-digest must be supplied together")
    if args.evidence_directory and not args.ollama_endpoint:
        parser.error("--evidence-directory requires Ollama enrichment")
    try:
        report = build_report(
            args.catalogue.resolve(),
            ollama_endpoint=args.ollama_endpoint,
            ollama_model=args.ollama_model,
            ollama_digest=args.ollama_digest,
            prompt_template_path=args.prompt_template,
            prompt_template_version=args.prompt_template_version,
            timeout=args.timeout,
        )
    except OllamaEnrichmentError as error:
        print(f"Ollama enrichment failed: {error}", file=sys.stderr)
        return 1
    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    if args.evidence_directory:
        write_evidence_records(report, args.evidence_directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
