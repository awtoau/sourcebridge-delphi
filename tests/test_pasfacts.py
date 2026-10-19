from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from sourcebridge_delphi.pasfacts import PasFactsError, extract_facts
from sourcebridge_delphi.emit_rust import emit


ROOT = Path(__file__).parents[1]


def _fpc_available() -> bool:
    if shutil.which("fpc") is None:
        return False
    try:
        from tools.fpc_runtime import rtl_unit_path
        rtl = rtl_unit_path()
        return rtl is not None and (rtl.parent / "fcl-passrc" / "pparser.ppu").is_file()
    except Exception:
        return False


@unittest.skipUnless(_fpc_available(), "FPC + fcl-passrc required")
class PasFactsTests(unittest.TestCase):
    def test_extracts_addition_facts_from_a_unit_via_real_parser(self) -> None:
        facts = extract_facts(ROOT / "fixtures" / "scalars.pas")
        by_name = {f["name"]: f for f in facts["facts"]}
        self.assertEqual(by_name["AddSigned"]["return_type"], "integer")
        self.assertEqual(by_name["AddUnsigned"]["return_type"], "cardinal")
        self.assertEqual(by_name["AddSigned"]["operands"], ["Left", "Right"])

    def test_parses_a_program_the_regex_rejects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "prog.pp"
            src.write_text(
                "{$mode objfpc}\n"
                "function AddC(A: Cardinal; B: Cardinal): Cardinal;\n"
                "begin\n  Result := A + B;\nend;\n"
                "begin end.\n",
                encoding="utf-8",
            )
            facts = extract_facts(src)
        names = {f["name"] for f in facts["facts"]}
        self.assertIn("AddC", names)

    def test_facts_feed_the_data_driven_emitter(self) -> None:
        facts = extract_facts(ROOT / "fixtures" / "scalars.pas")
        rules = [json.loads(p.read_text()) for p in sorted((ROOT / "rules").glob("*.json"))]
        rust = emit(facts, rules)
        self.assertIn("pub fn addsigned(left: i32, right: i32) -> i32", rust)
        self.assertIn("left.wrapping_add(right)", rust)

    def test_extracts_boolean_comparison_branch_fact(self) -> None:
        (fact,) = extract_facts(ROOT / "fixtures" / "booleancomparison.pas")["facts"]
        self.assertEqual(fact["kind"], "boolean_comparison_branch_function")
        self.assertEqual(fact["return_type"], "boolean")
        self.assertEqual(fact["operator"], ">")
        self.assertEqual(fact["operands"], ["Left", "Right"])
        self.assertIs(fact["true_value"], True)
        self.assertIs(fact["false_value"], False)

    def test_extracts_boolean_comparison_expression_fact(self) -> None:
        (fact,) = extract_facts(ROOT / "fixtures" / "booleanexpression.pas")["facts"]
        self.assertEqual(fact["kind"], "boolean_comparison_expression_function")
        self.assertEqual(fact["return_type"], "boolean")
        self.assertEqual(fact["operator"], ">")
        self.assertEqual(fact["operands"], ["Left", "Right"])

    def test_extracts_string_length_fact_with_doubled_operands(self) -> None:
        (fact,) = extract_facts(ROOT / "fixtures" / "stringlength.pas")["facts"]
        self.assertEqual(fact["kind"], "string_length_function")
        self.assertEqual(fact["return_type"], "integer")
        self.assertEqual(fact["parameters"], [{"name": "Value", "type": "string"}])
        self.assertEqual(fact["operands"], ["Value", "Value"])

    def test_extracts_scalar_division_facts(self) -> None:
        facts = extract_facts(ROOT / "fixtures" / "scalardivision.pas")
        by_name = {f["name"]: f for f in facts["facts"]}
        self.assertEqual(by_name["DivSigned"]["kind"], "scalar_division_function")
        self.assertEqual(by_name["DivSigned"]["return_type"], "integer")
        self.assertEqual(by_name["DivSigned"]["operands"], ["Left", "Right"])
        self.assertEqual(by_name["DivUnsigned"]["return_type"], "cardinal")

    def test_extracts_scalar_multiplication_facts(self) -> None:
        facts = extract_facts(ROOT / "fixtures" / "scalarmultiplication.pas")
        by_name = {f["name"]: f for f in facts["facts"]}
        self.assertEqual(by_name["MulSigned"]["kind"], "scalar_multiplication_function")
        self.assertEqual(by_name["MulSigned"]["return_type"], "integer")
        self.assertEqual(by_name["MulSigned"]["operands"], ["Left", "Right"])
        self.assertEqual(by_name["MulUnsigned"]["return_type"], "cardinal")

    def test_extracts_scalar_subtraction_facts(self) -> None:
        facts = extract_facts(ROOT / "fixtures" / "scalarsubtraction.pas")
        by_name = {f["name"]: f for f in facts["facts"]}
        self.assertEqual(by_name["SubSigned"]["kind"], "scalar_subtraction_function")
        self.assertEqual(by_name["SubSigned"]["return_type"], "integer")
        self.assertEqual(by_name["SubSigned"]["operands"], ["Left", "Right"])
        self.assertEqual(by_name["SubUnsigned"]["return_type"], "cardinal")

    def test_extracts_scalar_modulo_facts(self) -> None:
        facts = extract_facts(ROOT / "fixtures" / "scalarmodulo.pas")
        by_name = {f["name"]: f for f in facts["facts"]}
        self.assertEqual(by_name["ModSigned"]["kind"], "scalar_modulo_function")
        self.assertEqual(by_name["ModSigned"]["return_type"], "integer")
        self.assertEqual(by_name["ModSigned"]["operands"], ["Left", "Right"])
        self.assertEqual(by_name["ModUnsigned"]["return_type"], "cardinal")

    def test_extracts_scalar_bitwise_and_facts(self) -> None:
        facts = extract_facts(ROOT / "fixtures" / "scalarbitwiseand.pas")
        by_name = {f["name"]: f for f in facts["facts"]}
        self.assertEqual(by_name["BitAndSigned"]["kind"], "scalar_bitwise_and_function")
        self.assertEqual(by_name["BitAndSigned"]["return_type"], "integer")
        self.assertEqual(by_name["BitAndSigned"]["operands"], ["Left", "Right"])
        self.assertEqual(by_name["BitAndUnsigned"]["return_type"], "cardinal")


if __name__ == "__main__":
    unittest.main()
