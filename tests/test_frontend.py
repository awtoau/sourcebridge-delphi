from __future__ import annotations

from pathlib import Path
import shutil
import unittest

from sourcebridge_delphi.frontend import ExtractionError, extract


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


class FrontendFallbackTests(unittest.TestCase):
    def test_layout_program_uses_regex_fallback(self) -> None:
        result = extract(ROOT / "fixtures" / "scalar_layout.pas")
        self.assertEqual(result["extractor"], "regex-fallback")
        kinds = {f["kind"] for f in result["facts"]}
        self.assertIn("scalar_layout_program", kinds)

    def test_unsupported_source_raises_extraction_error(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "empty.pp"
            src.write_text("{$mode objfpc}\nbegin\nend.\n", encoding="utf-8")
            with self.assertRaises(ExtractionError):
                extract(src)


@unittest.skipUnless(_fpc_available(), "FPC + fcl-passrc required")
class FrontendCompilerPathTests(unittest.TestCase):
    def test_function_fixtures_use_fcl_passrc(self) -> None:
        for name in ("scalars", "booleancomparison", "booleanexpression", "stringlength"):
            result = extract(ROOT / "fixtures" / f"{name}.pas")
            self.assertEqual(result["extractor"], "fcl-passrc", name)
            self.assertTrue(result["facts"], name)


if __name__ == "__main__":
    unittest.main()
