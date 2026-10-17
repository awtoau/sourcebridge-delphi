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

    def test_extracts_scalar_addition_fixture(self) -> None:
        result = extract(Path("fixtures/scalars.pas"))
        self.assertEqual(result["unit"], "Scalars")
        self.assertEqual([fact["name"] for fact in result["facts"]], ["AddSigned", "AddUnsigned"])
        self.assertEqual(result["facts"][0]["parameters"][0]["type"], "integer")
        self.assertEqual(result["facts"][1]["return_type"], "cardinal")
        self.assertEqual(result["facts"][0]["operands"], ["Left", "Right"])

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
