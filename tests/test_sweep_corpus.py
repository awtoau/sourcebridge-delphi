from __future__ import annotations

from pathlib import Path
import shutil
import unittest

from tools.sweep_corpus import _load_rules, sweep


ROOT = Path(__file__).parents[1]


class SweepCorpusTests(unittest.TestCase):
    def test_fixtures_all_emit_and_compile(self) -> None:
        report = sweep(ROOT / "fixtures", _load_rules(), limit=None, rustc=shutil.which("rustc"))
        self.assertTrue(report["invariant_all_emitted_rust_compiles"])
        self.assertEqual(report["target_compile_failures"], [])
        self.assertGreaterEqual(report["outcomes"].get("emitted_and_compiled", 0), 6)

    def test_unsupported_source_is_a_noted_gap_not_a_crash(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "weird.pp"
            bad.write_text("program Weird; begin WriteLn(Unsupported) end.", encoding="utf-8")
            report = sweep(Path(tmp), _load_rules(), limit=None, rustc=shutil.which("rustc"))
        self.assertEqual(report["outcomes"].get("extraction_unsupported"), 1)
        self.assertTrue(report["invariant_all_emitted_rust_compiles"])


if __name__ == "__main__":
    unittest.main()
