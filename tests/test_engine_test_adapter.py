from __future__ import annotations

import json
from pathlib import Path
import unittest

from tools.run_sourcebridge_engine_test import run_test


ROOT = Path(__file__).parents[1]


class EngineTestAdapterTests(unittest.TestCase):
    def test_stage1_result_has_source_and_extraction_evidence_only(self) -> None:
        result = run_test(
            ROOT / "fixtures" / "scalars.pas",
            ROOT / "variants" / "fpc-3.2.3-x86_64-linux.json",
            "fpc",
        )
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["source"]["status"], "passed")
        self.assertEqual(result["extraction"]["status"], "passed")
        self.assertEqual(result["target"]["status"], "blocked")
        self.assertEqual(result["oracle"]["status"], "skipped")

    def test_catalogue_uses_a_non_csharp_stable_id(self) -> None:
        catalogue = json.loads((ROOT / "engine-tests.json").read_text(encoding="utf-8"))
        ids = {case["id"] for case in catalogue["tests"]}
        self.assertEqual(ids, {437, 438, 439, 440, 441})
        self.assertTrue(ids.isdisjoint({434, 435, 436}))

    def test_boolean_case_has_honest_expected_statuses(self) -> None:
        catalogue = json.loads((ROOT / "engine-tests.json").read_text(encoding="utf-8"))
        case = next(item for item in catalogue["tests"] if item["id"] == 438)
        self.assertEqual(case["fixture"], "fixtures/booleancomparison.pas")
        self.assertEqual(case["expected"]["source"]["status"], "passed")
        self.assertEqual(case["expected"]["extraction"]["status"], "passed")
        self.assertEqual(case["expected"]["target"]["status"], "blocked")
        self.assertEqual(case["expected"]["oracle"]["status"], "skipped")

    def test_remaining_unsupported_basics_primitives_are_blocked_at_extraction(self) -> None:
        catalogue = json.loads((ROOT / "engine-tests.json").read_text(encoding="utf-8"))
        cases = {item["id"]: item for item in catalogue["tests"]}
        self.assertEqual(cases[439]["expected"]["extraction"]["status"], "passed")
        for test_id in (440, 441):
            self.assertEqual(cases[test_id]["expected"]["source"]["status"], "passed")
            self.assertEqual(cases[test_id]["expected"]["extraction"]["status"], "failed")
            self.assertEqual(cases[test_id]["expected"]["target"]["status"], "blocked")
            self.assertEqual(cases[test_id]["expected"]["oracle"]["status"], "skipped")

    def test_basics_curriculum_is_ordered_and_names_engine_tests(self) -> None:
        curriculum = json.loads(
            (ROOT / "rule-curriculum.json").read_text(encoding="utf-8")
        )
        self.assertEqual(curriculum["selector"], "basics")
        self.assertEqual(
            [(entry["order"], entry["test_id"]) for entry in curriculum["entries"]],
            [(1, 437), (2, 439), (3, 440), (4, 438), (5, 441)],
        )
