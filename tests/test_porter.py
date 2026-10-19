from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from sourcebridge_delphi.pasfacts import extract_facts
from sourcebridge_delphi.porter import emit_program


ROOT = Path(__file__).parents[1]
RULE = json.loads((ROOT / "rules" / "program-integer-bitwise.json").read_text())


def _fpc_available() -> bool:
    if shutil.which("fpc") is None:
        return False
    try:
        from tools.fpc_runtime import rtl_unit_path
        rtl = rtl_unit_path()
        return rtl is not None and (rtl.parent / "fcl-passrc" / "pparser.ppu").is_file()
    except Exception:
        return False


def _tools_ready() -> bool:
    return _fpc_available() and shutil.which("rustc") is not None


def _compile_and_run_rust(rust: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "port.rs"
        source.write_text(rust, encoding="utf-8")
        binary = Path(tmp) / "port"
        build = subprocess.run(
            [shutil.which("rustc"), "--edition", "2021", str(source), "-o", str(binary)],
            capture_output=True, text=True,
        )
        if build.returncode:
            raise AssertionError(f"emitted Rust did not compile:\n{build.stderr}")
        return subprocess.run([str(binary)], capture_output=True, text=True)


@unittest.skipUnless(_tools_ready(), "FPC + fcl-passrc + rustc required")
class IncrementalPorterTests(unittest.TestCase):
    def _program_body(self, text: str) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "prog.pp"
            src.write_text(text, encoding="utf-8")
            facts = extract_facts(src, program_body=True)
        fact = next(f for f in facts["facts"] if f["kind"] == "program_body")
        fact["source_path"] = "prog.pp"
        return fact

    def test_bitwise_program_ports_fully_and_runs_like_fpc(self) -> None:
        program = (
            "program Bitwise;\n"
            "var b: byte; s: shortint; l: longint;\n"
            "begin\n"
            "  b:=10; s:=-128;\n"
            "  l:=b or s; writeln(l);\n"
            "  if (l<>-118) then halt(1);\n"
            "end.\n"
        )
        fact = self._program_body(program)
        result = emit_program(fact, RULE)
        self.assertEqual(result["unported"], 0)
        run = _compile_and_run_rust(result["rust"])
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout, "-118\n")

    def test_arithmetic_program_ports_and_runs_like_fpc(self) -> None:
        program = (
            "program Arith;\n"
            "var a: longint; b: longint; c: longint;\n"
            "begin\n"
            "  a:=1000000; b:=2000;\n"
            "  c:=a+b; writeln(c); if (c<>1002000) then halt(1);\n"
            "  c:=a-b; writeln(c); if (c<>998000) then halt(2);\n"
            "  c:=b*b; writeln(c); if (c<>4000000) then halt(3);\n"
            "end.\n"
        )
        fact = self._program_body(program)
        result = emit_program(fact, RULE)
        self.assertEqual(result["unported"], 0)
        self.assertIn("wrapping_add", result["rust"])
        run = _compile_and_run_rust(result["rust"])
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout, "1002000\n998000\n4000000\n")

    def test_unported_statement_still_compiles_and_runs(self) -> None:
        # A for-loop is not a modelled statement kind, so it must degrade to a
        # stub while the emitted Rust still compiles and runs the ported lines.
        program = (
            "program Partial;\n"
            "var i: longint; b: byte;\n"
            "begin\n"
            "  b:=3;\n"
            "  writeln(b);\n"
            "  for i:=1 to 2 do b:=0;\n"
            "end.\n"
        )
        fact = self._program_body(program)
        result = emit_program(fact, RULE)
        self.assertGreaterEqual(result["unported"], 1)
        self.assertIn("// UNPORTED", result["rust"])
        run = _compile_and_run_rust(result["rust"])
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout, "3\n")


if __name__ == "__main__":
    unittest.main()
