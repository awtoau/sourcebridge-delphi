from __future__ import annotations

from pathlib import Path
import unittest

from sourcebridge_delphi.extract import ExtractionError, extract


class ExtractTests(unittest.TestCase):
    def test_extracts_boolean_comparison_branch_fixture(self) -> None:
        result = extract(Path("fixtures/booleancomparison.pas"))
        self.assertEqual(result["unit"], "BooleanComparison")
        self.assertEqual(result["facts"][0]["kind"], "boolean_comparison_branch_function")
        self.assertEqual(result["facts"][0]["operator"], ">")
        self.assertEqual(result["facts"][0]["operands"], ["Left", "Right"])

    def test_extracts_boolean_comparison_expression_fixture(self) -> None:
        result = extract(Path("fixtures/booleanexpression.pas"))
        self.assertEqual(result["unit"], "BooleanExpression")
        fact = result["facts"][0]
        self.assertEqual(fact["kind"], "boolean_comparison_expression_function")
        self.assertEqual(fact["name"], "IsGreater")
        self.assertEqual(fact["return_type"], "boolean")
        self.assertEqual(fact["operator"], ">")
        self.assertEqual(fact["operands"], ["Left", "Right"])

    def test_extracts_string_length_fixture(self) -> None:
        result = extract(Path("fixtures/stringlength.pas"))
        self.assertEqual(result["unit"], "StringLength")
        fact = result["facts"][0]
        self.assertEqual(fact["kind"], "string_length_function")
        self.assertEqual(fact["name"], "TextLength")
        self.assertEqual(fact["return_type"], "integer")
        self.assertEqual(fact["parameters"], [{"name": "Value", "type": "string"}])
        self.assertEqual(fact["operands"][0], "Value")

    def test_rejects_non_boolean_comparison_expression(self) -> None:
        path = Path(self._testMethodName + ".pas")
        self.addCleanup(path.unlink, missing_ok=True)
        path.write_text(
            "unit Invalid;\nfunction A(Left: Integer; Right: Integer): Integer;\n"
            "begin\nResult := Left > Right;\nend;\nend.\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ExtractionError, "must return Boolean"):
            extract(path)

    def test_rejects_length_of_non_string_parameter(self) -> None:
        path = Path(self._testMethodName + ".pas")
        self.addCleanup(path.unlink, missing_ok=True)
        path.write_text(
            "unit Invalid;\nfunction A(Value: Integer): Integer;\n"
            "begin\nResult := Length(Value);\nend;\nend.\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ExtractionError, "must be a declared String parameter"):
            extract(path)

    def test_extracts_scalar_addition_fixture(self) -> None:
        result = extract(Path("fixtures/scalars.pas"))
        self.assertEqual(result["unit"], "Scalars")
        self.assertEqual([fact["name"] for fact in result["facts"]], ["AddSigned", "AddUnsigned"])
        self.assertEqual(result["facts"][0]["parameters"][0]["type"], "integer")
        self.assertEqual(result["facts"][1]["return_type"], "cardinal")
        self.assertEqual(result["facts"][0]["operands"], ["Left", "Right"])

    def test_extracts_scalar_layout_program_fixture(self) -> None:
        result = extract(Path("fixtures/scalar_layout.pas"))
        fact = result["facts"][0]
        self.assertIsNone(result["unit"])
        self.assertEqual(result["program"], "ScalarLayout")
        self.assertEqual(fact["kind"], "scalar_layout_program")
        self.assertEqual(
            [(item["type"], item["expression"]) for item in fact["size_of"]],
            [("integer", "SizeOf(Integer)"), ("cardinal", "SizeOf(Cardinal)")],
        )
        self.assertEqual(
            [(item["type"], item["left"], item["right"]) for item in fact["typed_additions"]],
            [("integer", 1, 2), ("cardinal", 1, 2)],
        )

    def test_rejects_unsupported_body(self) -> None:
        path = Path(self._testMethodName + ".pas")
        self.addCleanup(path.unlink, missing_ok=True)
        path.write_text(
            "unit Invalid;\nfunction A(Value: Integer): Integer;\nbegin\nResult := Value;\nend;\nend.\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ExtractionError, "only `Result := Left \\+ Right`"):
            extract(path)

    def test_embeds_pinned_variant(self) -> None:
        result = extract(
            Path("fixtures/scalars.pas"),
            Path("variants/fpc-3.2.3-x86_64-linux.json"),
        )
        self.assertEqual(result["variant"]["compiler"]["version"], "3.2.3")
        self.assertEqual(result["limitations"], ["fixture grammar only"])
