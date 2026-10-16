#!/usr/bin/env python3
"""Run one bounded, local-only Delphi compiler-triage proposal batch."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
TRIAGE = ROOT / "evidence" / "fpc-compiler-tests-triage.json"
MODEL = "qwen2.5-coder:14b"
MODEL_DIGEST = "9ec8897f747e246e970bc5cfdda85d22f1123dc2e3d34978a010a75968716849"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
KEEP_ALIVE = "30m"


@dataclass(frozen=True)
class ModelIdentity:
    name: str
    digest: str


def request_json(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, sort_keys=True).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    try:
        with urlopen(request, timeout=900) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except OSError as error:
        raise ValueError(f"Ollama request failed: {error}") from error
    if not isinstance(decoded, dict):
        raise ValueError("Ollama response must be a JSON object")
    return decoded


def endpoint(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in LOCAL_HOSTS or parsed.path not in ("", "/"):
        raise ValueError("endpoint must be HTTP on localhost, 127.0.0.1, or ::1")
    return value.rstrip("/")


def resolve_model(base_url: str) -> ModelIdentity:
    models = request_json(f"{base_url}/api/tags").get("models")
    if not isinstance(models, list):
        raise ValueError("Ollama model list does not contain models")
    for item in models:
        if isinstance(item, dict) and item.get("name") == MODEL:
            digest = item.get("digest")
            if digest != MODEL_DIGEST:
                raise ValueError(f"model digest differs: expected {MODEL_DIGEST}, got {digest}")
            return ModelIdentity(MODEL, digest)
    raise ValueError(f"required local model is not installed: {MODEL}")


def choose_entries(limit: int) -> list[dict[str, str]]:
    entries = json.loads(TRIAGE.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("triage evidence must be a JSON array")
    candidates = [
        entry for entry in entries
        if isinstance(entry, dict)
        and entry.get("category") in {"compiler_or_runtime_diagnostic", "unclassified"}
    ]
    if len(candidates) < limit:
        raise ValueError(f"only {len(candidates)} non-setup triage entries are available")
    return candidates[:limit]


def request_payload(entry: dict[str, str]) -> dict[str, Any]:
    schema = {
        "type": "object",
        "required": [
            "status_claim",
            "test_path",
            "log_path",
            "category",
            "diagnostic",
            "classification",
            "next_action",
            "open_question",
        ],
        "properties": {
            "status_claim": {"const": "unvalidated-llm-proposal"},
            "test_path": {"type": "string"},
            "log_path": {"type": "string"},
            "category": {"type": "string"},
            "diagnostic": {"type": "string"},
            "classification": {
                "enum": [
                    "compiler_diagnostic",
                    "harness_setup",
                    "missing_log",
                    "needs_source_or_log_inspection",
                ]
            },
            "next_action": {"type": "string"},
            "open_question": {"type": "string"},
        },
        "additionalProperties": False,
    }
    return {
        "model": MODEL,
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "format": schema,
        "options": {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 512},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Delphi compiler-test triage assistant. Return exactly one JSON object. "
                    "Treat the supplied entry as the only evidence. Copy test_path, log_path, category, "
                    "and diagnostic exactly. Do not invent source syntax, compiler behavior, missing files, "
                    "or a conversion rule. Classify only the next investigation step. "
                    "status_claim must be unvalidated-llm-proposal."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "source_language": "delphi",
                        "compiler_variant": "free-pascal-3.2.3-x86_64-linux-delphi",
                        "triage_entry": entry,
                    },
                    sort_keys=True,
                ),
            },
        ],
    }


def validate(entry: dict[str, str], proposal: Any) -> dict[str, str]:
    if not isinstance(proposal, dict):
        raise ValueError("proposal is not an object")
    required = {
        "status_claim",
        "test_path",
        "log_path",
        "category",
        "diagnostic",
        "classification",
        "next_action",
        "open_question",
    }
    if set(proposal) != required:
        raise ValueError("proposal fields differ from the triage schema")
    for field in ("test_path", "log_path", "category", "diagnostic"):
        if proposal[field] != entry[field]:
            raise ValueError(f"proposal changed evidence field `{field}`")
    if proposal["status_claim"] != "unvalidated-llm-proposal":
        raise ValueError("proposal status claim is invalid")
    if proposal["classification"] not in {
        "compiler_diagnostic",
        "harness_setup",
        "missing_log",
        "needs_source_or_log_inspection",
    }:
        raise ValueError("proposal classification is invalid")
    if not all(isinstance(proposal[field], str) for field in required):
        raise ValueError("proposal fields must all be strings")
    return proposal


def unload(base_url: str) -> None:
    request_json(f"{base_url}/api/generate", {"model": MODEL, "keep_alive": 0})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evidence" / "ollama-triage")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.limit <= 20:
        parser.error("--limit must be between 1 and 20")
    base_url = endpoint(args.endpoint)
    entries = choose_entries(args.limit)
    if args.dry_run:
        print(json.dumps({"language": "delphi", "entries": entries}, indent=2, sort_keys=True))
        return 0
    model = resolve_model(base_url)
    session_id = hashlib.sha256(
        json.dumps(
            {"model": asdict(model), "entries": entries, "limit": args.limit},
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    staged_root = args.output_dir / "staged"
    rejected_root = args.output_dir / "rejected"
    outcomes = []
    try:
        for index, entry in enumerate(entries, start=1):
            payload = request_payload(entry)
            started = time.monotonic()
            raw = request_json(f"{base_url}/api/chat", payload)
            elapsed_seconds = time.monotonic() - started
            content = raw.get("message", {}).get("content") if isinstance(raw.get("message"), dict) else None
            record = {
                "status": "unvalidated-llm-proposal",
                "worker_session_id": session_id,
                "sequence": index,
                "model": asdict(model),
                "payload_sha256": hashlib.sha256(
                    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
                "input": entry,
                "elapsed_seconds": elapsed_seconds,
                "raw_response": raw,
            }
            try:
                proposal = json.loads(content) if isinstance(content, str) else None
                record["proposal"] = validate(entry, proposal)
                target = staged_root
            except (ValueError, json.JSONDecodeError) as error:
                record["rejection_reason"] = str(error)
                record["proposal"] = None
                target = rejected_root
            target.mkdir(parents=True, exist_ok=True)
            path = target / f"{record['payload_sha256']}.json"
            path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            outcomes.append({"sequence": index, "path": path.as_posix(), "status": record["status"] if target == staged_root else "rejected"})
    finally:
        unload(base_url)
    print(json.dumps({"language": "delphi", "session_id": session_id, "outcomes": outcomes}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
