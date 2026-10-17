from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from tools import run_fpc_source_candidates as runner


ROOT = Path(__file__).parents[1]
WORK = ROOT / "tests" / ".fpc-source-candidate-runner-work"
DIGEST = "a" * 64


def candidate(identifier: str, path: str = "tests/a.pas") -> runner.Candidate:
    return runner.Candidate(
        id=identifier,
        source_path=path,
        source_digest="b" * 64,
        corpus_revision="c" * 40,
        line=2,
        signature="function Sample: Integer;",
        symbol="Sample",
        excerpt="1: unit a;\n2: function Sample: Integer;",
        selection_reason="deterministic declaration candidate; preferred tests/ corpus path",
    )


class SourceCandidateRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        shutil.rmtree(WORK, ignore_errors=True)
        WORK.mkdir(parents=True)
        self.database = WORK / "queue.sqlite3"
        self.artifacts = WORK / "artifacts"

    def tearDown(self) -> None:
        shutil.rmtree(WORK, ignore_errors=True)

    def test_discovery_prefers_tests_then_rtl_and_records_attribution(self) -> None:
        corpus = WORK / "fpc"
        for relative, content in {
            "packages/x.pas": "function Last: Integer;\n",
            "rtl/core.pas": "function Middle: Integer;\n",
            "tests/first.pas": "function First: Integer;\n",
        }.items():
            path = corpus / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        found = runner.discover_candidates(corpus, revision="d" * 40)

        self.assertEqual([item.source_path for item in found], [
            "tests/first.pas", "rtl/core.pas", "packages/x.pas"
        ])
        first = found[0]
        self.assertEqual(first.line, 1)
        self.assertEqual(first.corpus_revision, "d" * 40)
        self.assertEqual(first.source_digest, hashlib.sha256(b"function First: Integer;\n").hexdigest())
        self.assertIn("1: function First: Integer;", first.excerpt)

    def test_local_endpoint_and_exact_model_digest_are_required(self) -> None:
        with patch.object(
            runner,
            "http_json",
            return_value={"models": [{"name": runner.MODEL, "digest": f"sha256:{DIGEST}"}]},
        ):
            model = runner.validate_local_ollama("http://localhost:11434", DIGEST)
        self.assertEqual(model["name"], runner.MODEL)

        with self.assertRaises(ValueError):
            runner.validate_local_ollama("https://remote.example", DIGEST)
        with self.assertRaises(ValueError):
            runner.validate_local_ollama("http://localhost:11434", "not-a-digest")

    def test_classification_writes_content_hash_transcripts_and_separates_tokens(self) -> None:
        source = candidate("one")
        generated = json.dumps({"source_assessment": "candidate", "reason": "source declaration"})
        with patch.object(
            runner,
            "http_json",
            return_value={"response": generated, "prompt_eval_count": 7, "eval_count": 11},
        ):
            outcome, prompt, generated_count, request_digest, response_digest, error = runner.classify(
                "http://localhost:11434", source, self.artifacts, DIGEST
            )

        self.assertEqual((outcome, prompt, generated_count, error), ("candidate", 7, 11, None))
        self.assertTrue((self.artifacts / "requests" / f"{request_digest}.json").is_file())
        self.assertTrue((self.artifacts / "responses" / f"{response_digest}.json").is_file())

    def test_run_is_bounded_durable_and_zero_safe(self) -> None:
        candidates = [candidate("first"), candidate("second", "rtl/b.pas")]
        tags = {"models": [{"name": runner.MODEL, "digest": DIGEST}]}
        response = {"response": json.dumps({"source_assessment": "rejected", "reason": "out of scope"})}
        with patch.object(runner, "http_json", side_effect=[tags, response]):
            result = runner.run(
                corpus=WORK / "unused",
                database=self.database,
                artifacts=self.artifacts,
                endpoint="http://127.0.0.1:11434",
                model_digest=DIGEST,
                limit=1,
                owner="test",
                discover=lambda _: candidates,
            )

        self.assertEqual(result["rejected"], 1)
        self.assertEqual(result["candidate"], 0)
        self.assertEqual(result["prompt_tokens"], 0)
        self.assertEqual(result["generated_tokens"], 0)
        with self.assertRaises(ValueError):
            runner.run(
                corpus=WORK / "unused",
                database=self.database,
                artifacts=self.artifacts,
                endpoint="http://localhost:11434",
                model_digest=DIGEST,
                limit=101,
                owner="test",
                discover=lambda _: candidates,
            )


if __name__ == "__main__":
    unittest.main()
