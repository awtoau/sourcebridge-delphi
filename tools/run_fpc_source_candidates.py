#!/usr/bin/env python3
"""Run bounded, source-only FPC candidate classifications through local Ollama."""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
from typing import Any, Callable, Iterable
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import uuid4

try:  # Supports both `python tools/...` and package-style test imports.
    from tools.inventory_pascal_corpus import source_files
except ModuleNotFoundError:
    from inventory_pascal_corpus import source_files


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "tmp" / "fpc"
DEFAULT_QUEUE = ROOT / "evidence" / "fpc-source-candidates.sqlite3"
DEFAULT_ARTIFACTS = ROOT / "evidence" / "fpc-source-candidate-transcripts"
MODEL = "qwen3-coder:30b"
MAX_LIMIT = 100
EXCERPT_LINES = 12
EXCERPT_CHARS = 2_000
SYMBOL = re.compile(
    r"^\s*(?:class\s+)?(?:function|procedure|constructor|destructor|operator|"
    r"type|var|const)\s+([A-Za-z_][A-Za-z0-9_.]*)",
    re.IGNORECASE,
)
OUTCOMES = frozenset({"candidate", "rejected", "failed", "blocked-on-target"})

SOURCE_ONLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["source_assessment", "reason"],
    "properties": {
        "source_assessment": {
            "type": "string",
            "enum": ["candidate", "rejected", "blocked-on-target"],
        },
        "reason": {"type": "string", "minLength": 1, "maxLength": 500},
    },
}


@dataclass(frozen=True)
class Candidate:
    id: str
    source_path: str
    source_digest: str
    corpus_revision: str
    line: int
    signature: str
    symbol: str
    excerpt: str
    selection_reason: str


class NoRedirect(HTTPRedirectHandler):
    """Keep a loopback request from being redirected to a non-local endpoint."""

    def redirect_request(
        self, request: Request, fp: Any, code: int, message: str, headers: Any, newurl: str
    ) -> Request | None:
        return None


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def corpus_revision(root: Path) -> str:
    """Return the pinned git revision, refusing an unpinned corpus."""

    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    revision = result.stdout.strip()
    if result.returncode or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError(f"{root}: pinned FPC corpus must be a git checkout with a HEAD revision")
    return revision


def _priority(relative_path: str) -> tuple[int, str]:
    parts = Path(relative_path).parts
    if "tests" in parts:
        return (0, relative_path)
    if "rtl" in parts:
        return (1, relative_path)
    return (2, relative_path)


def _excerpt(lines: list[str], line_index: int) -> str:
    start = max(0, line_index - 2)
    end = min(len(lines), start + EXCERPT_LINES)
    text = "\n".join(
        f"{number + 1}: {line}" for number, line in enumerate(lines[start:end], start)
    )
    return text[:EXCERPT_CHARS]


def discover_candidates(root: Path, revision: str | None = None) -> list[Candidate]:
    """Produce a deterministic, deduplicated source candidate inventory."""

    root = root.resolve()
    revision = revision or corpus_revision(root)
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for path in source_files(root):
        relative = path.relative_to(root).as_posix()
        contents = path.read_bytes()
        source_digest = sha256(contents)
        lines = contents.decode("utf-8", errors="replace").splitlines()
        for index, line in enumerate(lines):
            match = SYMBOL.match(line)
            if match is None:
                continue
            signature = line.strip()[:500]
            symbol = match.group(1)
            identity = {
                "source_path": relative,
                "source_digest": source_digest,
                "corpus_revision": revision,
                "line": index + 1,
                "signature": signature,
            }
            candidate_id = sha256(canonical_json(identity))
            if candidate_id in seen:
                continue
            seen.add(candidate_id)
            location = "tests/" if "tests" in Path(relative).parts else "rtl/"
            candidates.append(
                Candidate(
                    id=candidate_id,
                    source_path=relative,
                    source_digest=source_digest,
                    corpus_revision=revision,
                    line=index + 1,
                    signature=signature,
                    symbol=symbol,
                    excerpt=_excerpt(lines, index),
                    selection_reason=(
                        f"deterministic declaration candidate; preferred {location} "
                        "corpus path"
                    ),
                )
            )
    return sorted(
        candidates,
        key=lambda item: (*_priority(item.source_path), item.line, item.signature, item.id),
    )


def initialize_queue(database: Path) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS fpc_source_candidate (
                id TEXT PRIMARY KEY,
                candidate_json TEXT NOT NULL,
                candidate_digest TEXT NOT NULL,
                outcome TEXT CHECK (outcome IN
                    ('candidate', 'rejected', 'failed', 'blocked-on-target')),
                claimed_by TEXT,
                claimed_at TEXT,
                completed_at TEXT,
                request_digest TEXT,
                response_digest TEXT,
                prompt_tokens INTEGER,
                generated_tokens INTEGER,
                error_json TEXT
            )
            """
        )
        connection.commit()


def enqueue_candidates(database: Path, candidates: Iterable[Candidate]) -> int:
    inserted = 0
    with closing(sqlite3.connect(database)) as connection:
        for candidate in candidates:
            payload = canonical_json(asdict(candidate))
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO fpc_source_candidate
                    (id, candidate_json, candidate_digest)
                VALUES (?, ?, ?)
                """,
                (candidate.id, payload.decode("utf-8"), sha256(payload)),
            )
            inserted += cursor.rowcount
        connection.commit()
    return inserted


def existing_candidate_ids(database: Path) -> set[str]:
    with closing(sqlite3.connect(database)) as connection:
        return {row[0] for row in connection.execute("SELECT id FROM fpc_source_candidate")}


def claim_candidate(database: Path, owner: str, lease_seconds: int = 900) -> Candidate | None:
    if not owner.strip():
        raise ValueError("owner must be non-empty")
    now = datetime.now(UTC)
    expired = (now - timedelta(seconds=lease_seconds)).isoformat()
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT id, candidate_json FROM fpc_source_candidate
            WHERE outcome IS NULL
              AND (claimed_at IS NULL OR claimed_at < ?)
            ORDER BY candidate_json, id
            LIMIT 1
            """,
            (expired,),
        ).fetchone()
        if row is None:
            connection.commit()
            return None
        connection.execute(
            "UPDATE fpc_source_candidate SET claimed_by = ?, claimed_at = ? WHERE id = ?",
            (owner, now.isoformat(), row[0]),
        )
        connection.commit()
    return Candidate(**json.loads(row[1]))


def complete_candidate(
    database: Path,
    candidate_id: str,
    owner: str,
    outcome: str,
    *,
    request_digest: str | None = None,
    response_digest: str | None = None,
    prompt_tokens: int = 0,
    generated_tokens: int = 0,
    error: Any | None = None,
) -> None:
    if outcome not in OUTCOMES:
        raise ValueError(f"unsupported outcome: {outcome}")
    if prompt_tokens < 0 or generated_tokens < 0:
        raise ValueError("token counts cannot be negative")
    with closing(sqlite3.connect(database)) as connection:
        cursor = connection.execute(
            """
            UPDATE fpc_source_candidate
            SET outcome = ?, completed_at = ?, request_digest = ?, response_digest = ?,
                prompt_tokens = ?, generated_tokens = ?, error_json = ?
            WHERE id = ? AND outcome IS NULL AND claimed_by = ?
            """,
            (
                outcome,
                utc_now(),
                request_digest,
                response_digest,
                prompt_tokens,
                generated_tokens,
                None if error is None else canonical_json(error).decode("utf-8"),
                candidate_id,
                owner,
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError("candidate does not have the specified active claim")
        connection.commit()


def validate_local_ollama(endpoint: str, expected_digest: str) -> dict[str, Any]:
    parsed = urlparse(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Ollama endpoint must use http on localhost only")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Ollama endpoint cannot contain credentials, query, or fragment")
    if not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", expected_digest):
        raise ValueError("model digest must be an exact SHA-256 digest")
    base = endpoint.rstrip("/")
    tags = http_json(Request(f"{base}/api/tags", method="GET"))
    models = tags.get("models")
    if not isinstance(models, list):
        raise ValueError("Ollama /api/tags did not return a models list")
    expected = expected_digest.removeprefix("sha256:")
    matches = [
        model
        for model in models
        if isinstance(model, dict)
        and model.get("name") == MODEL
        and str(model.get("digest", "")).removeprefix("sha256:") == expected
    ]
    if len(matches) != 1:
        raise ValueError(f"local Ollama does not expose {MODEL} with the requested exact digest")
    return matches[0]


def http_json(request: Request, timeout: float = 60.0) -> dict[str, Any]:
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("HTTP response must be a JSON object")
    return payload


def artifact(artifacts: Path, kind: str, payload: Any) -> tuple[str, Path]:
    content = canonical_json(payload)
    digest = sha256(content)
    path = artifacts / kind / f"{digest}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(content + b"\n")
    return digest, path


def request_payload(candidate: Candidate, model_digest: str) -> dict[str, Any]:
    return {
        "model": MODEL,
        "stream": False,
        "format": SOURCE_ONLY_SCHEMA,
        "options": {"temperature": 0},
        "prompt": (
            "Classify this FPC source location only. Do not infer, propose, validate, "
            "or output rules. Do not claim any target behavior is validated. Return only "
            "the required JSON object.\n\n"
            + json.dumps(asdict(candidate), sort_keys=True)
        ),
        "metadata": {
            "local_only": True,
            "model_digest": model_digest,
            "purpose": "source-candidate-classification-only",
        },
    }


def classify(
    endpoint: str, candidate: Candidate, artifacts: Path, model_digest: str
) -> tuple[str, int, int, str, str, dict[str, Any] | None]:
    request = request_payload(candidate, model_digest)
    request_digest, _ = artifact(artifacts, "requests", request)
    start = time.monotonic()
    try:
        raw_response = http_json(
            Request(
                f"{endpoint.rstrip('/')}/api/generate",
                data=canonical_json(request),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        )
        elapsed_ms = round((time.monotonic() - start) * 1000, 3)
        transcript = {"elapsed_ms": elapsed_ms, "response": raw_response}
        response_digest, _ = artifact(artifacts, "responses", transcript)
        prompt_tokens = token_count(raw_response.get("prompt_eval_count"))
        generated_tokens = token_count(raw_response.get("eval_count"))
        generated = raw_response.get("response")
        decoded = json.loads(generated) if isinstance(generated, str) else None
        if not valid_source_response(decoded):
            return "failed", prompt_tokens, generated_tokens, request_digest, response_digest, {
                "message": "model response did not satisfy source-only schema"
            }
        return (
            decoded["source_assessment"],
            prompt_tokens,
            generated_tokens,
            request_digest,
            response_digest,
            None,
        )
    except Exception as error:
        transcript = {"error": {"type": type(error).__name__, "message": str(error)}}
        response_digest, _ = artifact(artifacts, "responses", transcript)
        return "failed", 0, 0, request_digest, response_digest, transcript["error"]


def token_count(value: Any) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def valid_source_response(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"source_assessment", "reason"}
        and value.get("source_assessment") in OUTCOMES - {"failed"}
        and isinstance(value.get("reason"), str)
        and 0 < len(value["reason"]) <= 500
    )


def summary(database: Path) -> dict[str, int]:
    result = {outcome: 0 for outcome in sorted(OUTCOMES)}
    result.update({"pending": 0, "prompt_tokens": 0, "generated_tokens": 0})
    with closing(sqlite3.connect(database)) as connection:
        for outcome, count in connection.execute(
            "SELECT COALESCE(outcome, 'pending'), COUNT(*) FROM fpc_source_candidate GROUP BY outcome"
        ):
            result[outcome] = count
        row = connection.execute(
            "SELECT COALESCE(SUM(prompt_tokens), 0), COALESCE(SUM(generated_tokens), 0) "
            "FROM fpc_source_candidate"
        ).fetchone()
        result["prompt_tokens"], result["generated_tokens"] = row
    return result


def run(
    *,
    corpus: Path,
    database: Path,
    artifacts: Path,
    endpoint: str,
    model_digest: str,
    limit: int,
    owner: str,
    discover: Callable[[Path], list[Candidate]] = discover_candidates,
) -> dict[str, int]:
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    validate_local_ollama(endpoint, model_digest)
    initialize_queue(database)
    known = existing_candidate_ids(database)
    selected = [candidate for candidate in discover(corpus) if candidate.id not in known][:limit]
    enqueue_candidates(database, selected)
    for _ in selected:
        candidate = claim_candidate(database, owner)
        if candidate is None:
            break
        outcome, prompt_tokens, generated_tokens, request_digest, response_digest, error = classify(
            endpoint, candidate, artifacts, model_digest
        )
        complete_candidate(
            database,
            candidate.id,
            owner,
            outcome,
            request_digest=request_digest,
            response_digest=response_digest,
            prompt_tokens=prompt_tokens,
            generated_tokens=generated_tokens,
            error=error,
        )
    return summary(database)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--database", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--endpoint", default="http://localhost:11434")
    parser.add_argument("--model-digest", required=True)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--owner", default=f"fpc-source-candidate-{uuid4()}")
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                run(
                    corpus=args.corpus,
                    database=args.database,
                    artifacts=args.artifacts,
                    endpoint=args.endpoint,
                    model_digest=args.model_digest,
                    limit=args.limit,
                    owner=args.owner,
                ),
                sort_keys=True,
            )
        )
    except (OSError, ValueError, sqlite3.Error) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
