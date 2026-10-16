from __future__ import annotations

import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from record_fpc_compiler_test_corpus import source_files
from record_fpc_compiler_test_run import parse_digest, record
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

    def test_classifies_linker_and_semantic_differences(self) -> None:
        self.assertEqual(
            classify("Error: Error while linking\nundefined reference to `example`"),
            ("linker_environment_failure", "linker could not produce the test executable"),
        )
        self.assertEqual(
            classify('Error: Identifier not found "BMI2Support"'),
            ("compiler_semantic_difference", 'Identifier not found "BMI2Support"'),
        )

    def test_classifies_empty_harness_log(self) -> None:
        self.assertEqual(
            classify(""),
            ("empty_harness_log", "harness recorded a failure without a diagnostic"),
        )

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

    def test_records_the_compiler_used_by_the_harness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "manifest.json"
            manifest.write_text(
                '{"source_name":"fpc","source_remote":"https://example.test/fpc",'
                '"source_revision":"r1","tree_sha256":"digest"}',
                encoding="utf-8",
            )
            digest = root / "digest.txt"
            digest.write_text(
                "\n".join([
                    "Total = 1 (0:1)",
                    "Total number of compilations = 1 (0:1)",
                    "Successfully compiled = 1",
                    "Successfully failed = 0",
                    "Compilation failures = 0",
                    "Compilation that did not fail while they should = 0",
                    "Total number of runs = 0 (0:0)",
                    "Successful runs = 0",
                    "Failed runs = 0",
                    "Number of skipped tests = 0",
                ]),
                encoding="utf-8",
            )
            with patch(
                "record_fpc_compiler_test_run.compiler_identity",
                return_value={"version": "3.2.4", "target_cpu": "x86_64", "target_os": "linux"},
            ) as compiler_identity:
                result = record(manifest, digest, 4, "/opt/fpc/bin/fpc")

        compiler_identity.assert_called_once_with("/opt/fpc/bin/fpc")
        self.assertEqual(
            result["run"]["target"],
            "make full TEST_FPC=/opt/fpc/bin/fpc PP=/opt/fpc/bin/fpc QUICKTEST=1",
        )
