from __future__ import annotations

import argparse
import io
import json
import unittest

import dev


class DevelopmentEntryPointTests(unittest.TestCase):
    def test_describe_declares_explicit_corpus_policy(self) -> None:
        output = io.StringIO()
        original_emit = dev.emit
        try:
            dev.emit = lambda data, stream=output: original_emit(data, stream=output)
            self.assertEqual(dev.describe(argparse.Namespace()), 0)
        finally:
            dev.emit = original_emit
        description = json.loads(output.getvalue())
        self.assertEqual(description["entry_point"], "python3 dev.py")
        self.assertEqual(
            description["path_policy"]["corpus"],
            "explicit argument; never written to evidence",
        )

    def test_repository_path_rejects_absolute_paths(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            dev.repository_path("/external/evidence.json")

    def test_bootstrap_dry_run_uses_existing_manifest_recorder(self) -> None:
        args = dev.parser().parse_args(
            ["bootstrap-corpus", "--corpus-dir", "external", "--dry-run"]
        )
        commands = dev.bootstrap_corpus_commands(args)
        self.assertEqual(commands[0][:2], ["bash", "tools/bootstrap_fpc_test_corpus.sh"])
        self.assertIn("tools/record_fpc_compiler_test_corpus.py", commands[1])

    def test_runtime_bootstrap_dry_run_uses_explicit_paths(self) -> None:
        args = dev.parser().parse_args([
            "bootstrap-runtime",
            "--corpus-dir",
            "external",
            "--install-dir",
            "/tmp/fpc-runtime",
            "--host-fpc",
            "/usr/bin/fpc",
            "--workers",
            "4",
            "--dry-run",
        ])
        self.assertEqual(
            dev.bootstrap_runtime_commands(args),
            [[
                "bash",
                "tools/bootstrap_fpc_runtime.sh",
                "external",
                "/tmp/fpc-runtime",
                "/usr/bin/fpc",
                "4",
            ]],
        )

    def test_run_dry_run_uses_existing_run_recorder(self) -> None:
        args = dev.parser().parse_args(
            [
                "run-corpus",
                "--corpus-dir",
                "external",
                "--fpc",
                "/opt/fpc/bin/fpc",
                "--workers",
                "32",
                "--dry-run",
            ]
        )
        commands = dev.run_corpus_commands(args)
        self.assertEqual(
            commands[0],
            ["make", "clean", "TEST_FPC=/opt/fpc/bin/fpc"],
        )
        self.assertEqual(
            commands[1],
            [
                "make",
                "-j32",
                "full",
                "TEST_FPC=/opt/fpc/bin/fpc",
                "PP=/opt/fpc/bin/fpc",
                "QUICKTEST=1",
            ],
        )
        self.assertEqual(
            commands[2][-4:],
            ["--fpc", "/opt/fpc/bin/fpc", "--output", "evidence/fpc-compiler-tests-quick-run.json"],
        )

    def test_triage_dry_run_uses_existing_classifier(self) -> None:
        args = dev.parser().parse_args(
            ["triage-corpus", "--corpus-dir", "external", "--dry-run"]
        )
        command = dev.triage_corpus_commands(args)[0]
        self.assertIn("tools/build_fpc_corpus_triage_queue.py", command)
        self.assertEqual(command[-1], "evidence/fpc-compiler-tests-triage.json")

    def test_setup_failure_explicitly_excludes_conversion_evidence(self) -> None:
        output = io.StringIO()
        original_emit = dev.emit
        try:
            dev.emit = lambda data, stream=output: original_emit(data, stream=output)
            self.assertEqual(dev.failure("run-corpus", "harness unavailable"), 2)
        finally:
            dev.emit = original_emit
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "harness_setup_failure")
        self.assertEqual(result["conversion_evidence"], "none")

    def test_setup_failure_keeps_bounded_diagnostics(self) -> None:
        output = io.StringIO()
        original_emit = dev.emit
        try:
            dev.emit = lambda data, stream=output: original_emit(data, stream=output)
            self.assertEqual(dev.failure("bootstrap-runtime", "failed", "x" * 5_000), 2)
        finally:
            dev.emit = original_emit
        result = json.loads(output.getvalue())
        self.assertEqual(result["diagnostic_output"], "x" * 4_000)
