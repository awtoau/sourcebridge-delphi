from __future__ import annotations

from pathlib import Path
import unittest

from sourcebridge_delphi.emit_rust import RustEmissionError, emit
from sourcebridge_delphi.extract import extract


class RustEmissionTests(unittest.TestCase):
    def test_emits_wrapping_addition_module(self) -> None:
        artifact = emit(extract(Path("fixtures/scalars.pas")))
        self.assertIn("pub fn addsigned(left: i32, right: i32) -> i32", artifact)
        self.assertIn("left.wrapping_add(right)", artifact)
        self.assertIn("// SOURCEBRIDGE GAPS:", artifact)

    def test_emits_boolean_comparison_module(self) -> None:
        artifact = emit(extract(Path("fixtures/booleancomparison.pas")))
        self.assertIn("pub fn isgreater(left: i32, right: i32) -> bool", artifact)
        self.assertIn("left > right", artifact)

    def test_rejects_layout_program_without_a_rust_shape(self) -> None:
        with self.assertRaisesRegex(RustEmissionError, "scalar_layout_program"):
            emit(extract(Path("fixtures/scalar_layout.pas")))


if __name__ == "__main__":
    unittest.main()
