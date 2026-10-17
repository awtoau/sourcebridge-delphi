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


def _prompt(case: dict[str, Any], fixture_text: str, digest: str, statuses: dict[str, Any]) -> str:
    facts = {
        "test_id": case["id"],
        "name": case["name"],
        "fixture_path": case["fixture"],
        "fixture_sha256": digest,
        "adapter_statuses": statuses,
    }
    return (
        "Classify this Delphi fixture for prototype planning. Return JSON only, "
        "with exactly these keys: language_features (array of strings), "
        "complexity_band (string), prerequisites (array of strings), "
        "uncertainties (array of strings). This is supplemental and non-authoritative; "
        "do not infer target equivalence, rules, or catalogue changes.\n"
        f"Deterministic facts:\n{json.dumps(facts, sort_keys=True)}\n"
        f"Fixture source:\n{fixture_text}"
    )


def enrich(
    endpoint: str,
    model: str,
    model_digest: str,
    prompt: str,
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
        "prompt_sha256": sha256_text(prompt),
    }


def build_report(
    catalogue_path: Path,
    *,
    ollama_endpoint: str | None = None,
    ollama_model: str | None = None,
    ollama_digest: str | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
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
            prompt = _prompt(case, fixture_bytes.decode("utf-8"), digest, statuses)
            try:
                entry["ollama"] = enrich(
                    ollama_endpoint, ollama_model or "", ollama_digest or "", prompt, timeout
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
        "tests": tests,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", type=Path, default=ROOT / "engine-tests.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ollama-endpoint")
    parser.add_argument("--ollama-model")
    parser.add_argument("--ollama-digest")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args(argv)
    if bool(args.ollama_endpoint) != bool(args.ollama_model and args.ollama_digest):
        parser.error("--ollama-endpoint, --ollama-model, and --ollama-digest must be supplied together")
    try:
        report = build_report(
            args.catalogue.resolve(),
            ollama_endpoint=args.ollama_endpoint,
            ollama_model=args.ollama_model,
            ollama_digest=args.ollama_digest,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
