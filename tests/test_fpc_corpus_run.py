from __future__ import annotations

import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from record_fpc_compiler_test_corpus import source_files
from record_fpc_compiler_test_run import parse_digest
from build_fpc_corpus_triage_queue import classify


class FpcCorpusRunTests(unittest.TestCase):
    def test_classifies_missing_unit_as_harness_dependency(self) -> None:
        category, diagnostic = classify(
            "Fatal: Can't find unit variants used by Example\n"
            "Fatal: Compilation aborted\n"
            "Error: compiler returned an error exitcode\n"
        )
        self.assertEqual(category, "missing_test_dependency")
        self.assertEqual(diagnostic, "missing unit `variants`")

    def test_manifest_ignores_harness_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "test.pp").write_text("program Test;", encoding="utf-8")
            output = root / "output" / "x86_64-linux"
            output.mkdir(parents=True)
            (output / "generated.inc").write_text("generated", encoding="utf-8")
            self.assertEqual(source_files(root), [root / "test.pp"])

    def test_parses_upstream_digest_counts(self) -> None:
        digest = "\n".join([
            "Total = 10 (1:9)",
            "Total number of compilations = 7 (1:6)",
            "Successfully compiled = 4",
            "Successfully failed = 2",
            "Compilation failures = 1",
            "Compilation that did not fail while they should = 0",
            "Total number of runs = 3 (0:3)",
            "Successful runs = 3",
            "Failed runs = 0",
            "Number of skipped tests = 2",
        ])
        self.assertEqual(
            parse_digest(digest),
            {
                "total": 10,
                "compilations": 7,
                "compiled": 4,
                "expected_compile_failures": 2,
                "unexpected_compile_failures": 1,
                "unexpected_compile_successes": 0,
                "runs": 3,
                "successful_runs": 3,
                "unexpected_run_failures": 0,
                "skipped": 2,
            },
        )
