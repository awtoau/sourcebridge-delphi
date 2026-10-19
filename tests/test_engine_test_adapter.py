from __future__ import annotations

import json
from pathlib import Path
import unittest

from tools.run_sourcebridge_engine_test import run_test


ROOT = Path(__file__).parents[1]


class EngineTestAdapterTests(unittest.TestCase):
    def test_stage1_result_emits_and_compiles_rust(self) -> None:
        result = run_test(
            ROOT / "fixtures" / "scalars.pas",
            ROOT / "variants" / "fpc-3.2.3-x86_64-linux.json",
            "fpc",
        )
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["source"]["status"], "passed")
        self.assertEqual(result["extraction"]["status"], "passed")
        self.assertEqual(result["target"]["status"], "passed")
        self.assertEqual(result["oracle"]["status"], "skipped")

    def test_catalogue_uses_a_non_csharp_stable_id(self) -> None:
        catalogue = json.loads((ROOT / "engine-tests.json").read_text(encoding="utf-8"))
        ids = {case["id"] for case in catalogue["tests"]}
        self.assertEqual(
            ids,
            {437, 438, 439, 440, 441, 442, 443, 444, 445, 446, 447, 448, 449, 450, 451, 452},
        )
        self.assertTrue(ids.isdisjoint({434, 435, 436}))

    def test_boolean_case_has_honest_expected_statuses(self) -> None:
        catalogue = json.loads((ROOT / "engine-tests.json").read_text(encoding="utf-8"))
        case = next(item for item in catalogue["tests"] if item["id"] == 438)
        self.assertEqual(case["fixture"], "fixtures/booleancomparison.pas")
        self.assertEqual(case["expected"]["source"]["status"], "passed")
        self.assertEqual(case["expected"]["extraction"]["status"], "passed")
        self.assertEqual(case["expected"]["target"]["status"], "passed")
        self.assertEqual(case["expected"]["oracle"]["status"], "skipped")

    def test_boolean_branch_emits_and_compiles_rust(self) -> None:
        result = run_test(
            ROOT / "fixtures" / "booleancomparison.pas",
            ROOT / "variants" / "fpc-3.2.3-x86_64-linux.json",
            "fpc",
        )
        self.assertEqual(result["source"]["status"], "passed")
        self.assertEqual(result["extraction"]["status"], "passed")
        self.assertEqual(result["target"]["status"], "passed")
        self.assertEqual(result["oracle"]["status"], "skipped")

    def test_scalar_overflow_compares_source_and_generated_rust_output(self) -> None:
        result = run_test(
            ROOT / "fixtures" / "scalar_overflow.pas",
            ROOT / "variants" / "fpc-3.2.3-x86_64-linux.json",
            "fpc",
        )
        self.assertEqual(result["source"]["status"], "passed")
        self.assertEqual(result["extraction"]["status"], "passed")
        self.assertEqual(result["target"]["status"], "passed")
        self.assertEqual(result["oracle"]["status"], "passed")
        self.assertEqual(
            result["oracle"]["source_output"],
            ["SignedOverflow=-2147483648", "UnsignedOverflow=0"],
        )
        self.assertEqual(result["oracle"]["target_output"], result["oracle"]["source_output"])

    def test_boolean_branch_oracle_compares_source_and_generated_rust_output(self) -> None:
        result = run_test(
            ROOT / "fixtures" / "booleancomparison_oracle.pas",
            ROOT / "variants" / "fpc-3.2.3-x86_64-linux.json",
            "fpc",
        )
        self.assertEqual(result["source"]["status"], "passed")
        self.assertEqual(result["extraction"]["status"], "passed")
        self.assertEqual(result["target"]["status"], "passed")
        self.assertEqual(result["oracle"]["status"], "passed")
        self.assertEqual(
            result["oracle"]["source_output"],
            ["IsGreater(7,3)=1", "IsGreater(3,7)=0", "IsGreater(5,5)=0"],
        )
        self.assertEqual(result["oracle"]["target_output"], result["oracle"]["source_output"])

    def test_remaining_basics_primitives_now_emit_compilable_rust(self) -> None:
        catalogue = json.loads((ROOT / "engine-tests.json").read_text(encoding="utf-8"))
        cases = {item["id"]: item for item in catalogue["tests"]}
        for test_id in (440, 441):
            self.assertEqual(cases[test_id]["expected"]["source"]["status"], "passed")
            self.assertEqual(cases[test_id]["expected"]["extraction"]["status"], "passed")
            self.assertEqual(cases[test_id]["expected"]["target"]["status"], "passed")
            self.assertEqual(cases[test_id]["expected"]["oracle"]["status"], "skipped")
        # scalar_layout is an executable program; its oracle now runs.
        self.assertEqual(cases[439]["expected"]["oracle"]["status"], "passed")

    def test_basics_primitives_have_executable_oracle_coverage(self) -> None:
        catalogue = json.loads((ROOT / "engine-tests.json").read_text(encoding="utf-8"))
        cases = {item["id"]: item for item in catalogue["tests"]}
        # Every observable basics rule has an oracle fixture proving behavior.
        for test_id in (439, 444, 445):
            self.assertEqual(cases[test_id]["expected"]["oracle"]["status"], "passed")

    def test_basics_curriculum_is_ordered_and_names_engine_tests(self) -> None:
        curriculum = json.loads(
            (ROOT / "rule-curriculum.json").read_text(encoding="utf-8")
        )
        self.assertEqual(curriculum["selector"], "basics")
        self.assertEqual(
            [(entry["order"], entry["test_id"]) for entry in curriculum["entries"]],
            [(1, 437), (2, 439), (3, 440), (4, 438), (5, 441), (6, 442), (7, 443),
             (8, 444), (9, 445), (10, 446), (11, 447), (12, 448), (13, 449), (14, 450),
             (15, 451), (16, 452)],
        )

    def test_scalar_subtraction_oracle_proves_modular_underflow(self) -> None:
        result = run_test(
            ROOT / "fixtures" / "scalarsubtraction_oracle.pas",
            ROOT / "variants" / "fpc-3.2.3-x86_64-linux.json",
            "fpc",
        )
        self.assertEqual(result["source"]["status"], "passed")
        self.assertEqual(result["extraction"]["status"], "passed")
        self.assertEqual(result["target"]["status"], "passed")
        self.assertEqual(result["oracle"]["status"], "passed")
        self.assertEqual(
            result["oracle"]["source_output"],
            ["SignedUnderflow=2147483647", "UnsignedUnderflow=4294967295"],
        )
        self.assertEqual(result["oracle"]["target_output"], result["oracle"]["source_output"])

    def test_scalar_multiplication_oracle_proves_modular_overflow(self) -> None:
        result = run_test(
            ROOT / "fixtures" / "scalarmultiplication_oracle.pas",
            ROOT / "variants" / "fpc-3.2.3-x86_64-linux.json",
            "fpc",
        )
        self.assertEqual(result["source"]["status"], "passed")
        self.assertEqual(result["extraction"]["status"], "passed")
        self.assertEqual(result["target"]["status"], "passed")
        self.assertEqual(result["oracle"]["status"], "passed")
        self.assertEqual(
            result["oracle"]["source_output"],
            ["SignedOverflow=-2", "UnsignedOverflow=4294967294"],
        )
        self.assertEqual(result["oracle"]["target_output"], result["oracle"]["source_output"])

    def test_scalar_division_oracle_compares_source_and_generated_rust_output(self) -> None:
        result = run_test(
            ROOT / "fixtures" / "scalardivision_oracle.pas",
            ROOT / "variants" / "fpc-3.2.3-x86_64-linux.json",
            "fpc",
        )
        self.assertEqual(result["source"]["status"], "passed")
        self.assertEqual(result["extraction"]["status"], "passed")
        self.assertEqual(result["target"]["status"], "passed")
        self.assertEqual(result["oracle"]["status"], "passed")
        self.assertEqual(
            result["oracle"]["source_output"],
            ["divsigned(7,2)=3", "divsigned(-7,2)=-3", "divunsigned(100,7)=14"],
        )
        self.assertEqual(result["oracle"]["target_output"], result["oracle"]["source_output"])

    def test_program_bitwise_oracle_compares_source_and_generated_rust_output(self) -> None:
        result = run_test(
            ROOT / "fixtures" / "program_bitwise.pp",
            ROOT / "variants" / "fpc-3.2.3-x86_64-linux.json",
            "fpc",
        )
        self.assertEqual(result["source"]["status"], "passed")
        self.assertEqual(result["extraction"]["status"], "passed")
        self.assertEqual(result["extraction"]["mode"], "program")
        self.assertEqual(result["target"]["status"], "passed")
        self.assertEqual(result["target"]["unported_statements"], 0)
        self.assertEqual(result["oracle"]["status"], "passed")
        self.assertEqual(
            result["oracle"]["source_output"], ["8", "14", "6", "22", "2", "120"]
        )
        self.assertEqual(result["oracle"]["target_output"], result["oracle"]["source_output"])
        self.assertEqual(result["oracle"]["source_exit"], result["oracle"]["target_exit"])
