from __future__ import annotations

import json
from pathlib import Path
import unittest

from sourcebridge_delphi.emit_rust import RustEmissionError, emit
from sourcebridge_delphi.extract import extract


ROOT = Path(__file__).parents[1]


def _rules() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "rules").glob("*.json"))]


class RustEmissionTests(unittest.TestCase):
    def test_addition_output_comes_from_rule_data_not_hardcode(self) -> None:
        artifact = emit(extract(Path("fixtures/scalars.pas")), _rules())
        self.assertIn("pub fn addsigned(left: i32, right: i32) -> i32", artifact)
        self.assertIn("left.wrapping_add(right)", artifact)
        # The applied rule key is recorded in the header from data.
        self.assertIn("delphi.basics.scalar-addition", artifact)

    def test_changing_rule_data_changes_emitted_body(self) -> None:
        rules = _rules()
        for rule in rules:
            if rule["rule_key"] == "delphi.basics.scalar-addition":
                rule["output_shape"]["body"] = "{op0} + {op1}"
        artifact = emit(extract(Path("fixtures/scalars.pas")), rules)
        self.assertIn("left + right", artifact)
        self.assertNotIn("wrapping_add", artifact)

    def test_boolean_comparison_from_rule_data(self) -> None:
        artifact = emit(extract(Path("fixtures/booleancomparison.pas")), _rules())
        self.assertIn("pub fn isgreater(left: i32, right: i32) -> bool", artifact)
        self.assertIn("left > right", artifact)

    def test_boolean_comparison_expression_from_rule_data(self) -> None:
        artifact = emit(extract(Path("fixtures/booleanexpression.pas")), _rules())
        self.assertIn("pub fn isgreater(left: i32, right: i32) -> bool", artifact)
        self.assertIn("left > right", artifact)
        self.assertIn("delphi.basics.boolean-comparison-expression", artifact)

    def test_string_length_primitive_from_rule_data(self) -> None:
        artifact = emit(extract(Path("fixtures/stringlength.pas")), _rules())
        self.assertIn("pub fn textlength(value: &str) -> i32", artifact)
        self.assertIn("value.chars().count() as i32", artifact)
        self.assertIn("delphi.basics.string-length-primitive", artifact)

    def test_scalar_layout_program_from_rule_data(self) -> None:
        artifact = emit(extract(Path("fixtures/scalar_layout.pas")), _rules())
        self.assertIn("pub fn size_of_integer() -> usize", artifact)
        self.assertIn("std::mem::size_of::<i32>()", artifact)
        self.assertIn("pub fn size_of_cardinal() -> usize", artifact)
        self.assertIn("std::mem::size_of::<u32>()", artifact)
        self.assertIn("pub fn add_integer() -> i32", artifact)
        self.assertIn("(1i32).wrapping_add(2i32)", artifact)
        self.assertIn("pub fn add_cardinal() -> u32", artifact)
        self.assertIn("(1u32).wrapping_add(2u32)", artifact)
        self.assertIn("delphi.basics.integer-layout", artifact)

    def test_unmatched_fact_is_an_explicit_gap(self) -> None:
        unmatched = {"source_path": "synthetic", "facts": [{"kind": "no_such_fact_kind"}]}
        with self.assertRaisesRegex(RustEmissionError, "no active rule"):
            emit(unmatched, _rules())


if __name__ == "__main__":
    unittest.main()
