#!/usr/bin/env python3
"""Emit a Sourcebridge JSON engine-test result for one Delphi fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VARIANT = ROOT / "variants" / "fpc-3.2.3-x86_64-linux.json"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from record_fpc_compiler_test_run import compiler_identity
from sourcebridge_delphi.frontend import ExtractionError, extract, extract_program_body
from sourcebridge_delphi.emit_rust import RustEmissionError, emit
from sourcebridge_delphi.porter import emit_program


def _load_rules() -> list[dict[str, Any]]:
    """Load the Rust output-shape rules that govern emission.

    When invoked by the engine, the authoritative active rules resolved from the
    database are provided via ``SOURCEBRIDGE_RESOLVED_RULES``. For standalone
    pack testing, fall back to the pack's versioned ``rules/*.json`` data.
    """

    resolved = os.environ.get("SOURCEBRIDGE_RESOLVED_RULES")
    if resolved:
        return json.loads(Path(resolved).read_text(encoding="utf-8"))
    rules_dir = ROOT / "rules"
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(rules_dir.glob("*.json"))]


_OVERFLOW_FUNCTIONS = {
    "addsigned": ("i32::MAX", "1"),
    "addunsigned": ("u32::MAX", "1"),
}


def _status(status: str, **details: Any) -> dict[str, Any]:
    return {"status": status, **details}


def _variant(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{path}: cannot read FPC variant: {error}") from error
    if not isinstance(value, dict) or not isinstance(value.get("compiler"), dict):
        raise ValueError(f"{path}: FPC variant must contain a compiler object")
    return value


def _compiler_status(fpc: str, variant: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str] | None]:
    expected = variant["compiler"]
    try:
        actual = compiler_identity(fpc)
    except (OSError, ValueError) as error:
        return _status(
            "blocked",
            reason="the configured FPC compiler is unavailable",
            compiler=fpc,
            diagnostic=str(error),
        ), None
    required = {
        "version": expected.get("version"),
        "target_cpu": expected.get("target_cpu"),
        "target_os": expected.get("target_os"),
    }
    if actual != required:
        return _status(
            "blocked",
            reason="the configured FPC compiler does not match the pinned variant",
            compiler=fpc,
            expected_compiler=required,
            actual_compiler=actual,
        ), actual
    return _status("ready", compiler=fpc, actual_compiler=actual), actual


def _compile(
    fixture: Path, fpc: str, variant: dict[str, Any], output_directory: Path
) -> dict[str, Any]:
    compiler, actual = _compiler_status(fpc, variant)
    if compiler["status"] != "ready":
        return compiler
    rtl_path = _installed_rtl_path(actual)
    command = [
        fpc,
        "-Mdelphi",
    ]
    if rtl_path is not None:
        command.append(f"-Fu{rtl_path}")
    command.extend(
        [
            f"-FU{output_directory}",
            f"-FE{output_directory}",
            str(fixture),
        ]
    )
    result = subprocess.run(
        command,
        cwd=fixture.parent,
        check=False,
        capture_output=True,
        text=True,
    )
    details: dict[str, Any] = {
        "compiler": fpc,
        "compiler_identity": actual,
        "command": command,
    }
    if result.returncode:
        details["diagnostic"] = (result.stdout + result.stderr).strip()[-4_000:]
        return _status("failed", **details)
    return _status("passed", **details)


def _installed_rtl_path(identity: dict[str, str] | None) -> Path | None:
    if identity is None:
        return None
    target = f"{identity['target_cpu']}-{identity['target_os']}"
    candidates = (
        Path("/usr/lib64/fpc") / identity["version"] / "units" / target / "rtl",
        Path("/usr/lib/fpc") / identity["version"] / "units" / target / "rtl",
    )
    for candidate in candidates:
        if (candidate / "system.ppu").is_file():
            return candidate
    return None


def _compile_rust(facts: dict[str, Any], output_directory: Path) -> dict[str, Any]:
    rustc = shutil.which("rustc")
    if rustc is None:
        return _status("blocked", reason="Rust compiler (`rustc`) is unavailable")
    try:
        artifact = emit(facts, _load_rules())
    except RustEmissionError as error:
        return _status("blocked", reason=str(error))
    source = output_directory / "generated.rs"
    library = output_directory / "generated.rlib"
    source.write_text(artifact, encoding="utf-8")
    command = [rustc, "--edition", "2021", "--crate-type", "lib", str(source), "-o", str(library)]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    details = {
        "compiler": rustc,
        "command": command,
        "artifact_path": source.name,
        "artifact_digest": hashlib.sha256(artifact.encode("utf-8")).hexdigest(),
    }
    if result.returncode:
        return _status("failed", diagnostic=(result.stdout + result.stderr).strip()[-4_000:], **details)
    return _status("passed", artifact_content=artifact, **details)


_BOOLEAN_COMPARISON_INPUTS: tuple[tuple[int, int], ...] = ((7, 3), (3, 7), (5, 5))


def _scalar_overflow_harness(facts: dict[str, Any]) -> tuple[str, list[str]] | dict[str, Any]:
    """Build the Rust harness that exercises the bounded scalar overflow boundary."""

    functions = {
        str(fact.get("name", "")).casefold(): fact
        for fact in facts.get("facts", [])
        if fact.get("kind") == "scalar_addition_function"
    }
    if set(functions) != set(_OVERFLOW_FUNCTIONS):
        return _status(
            "blocked",
            reason="scalar overflow oracle requires AddSigned and AddUnsigned addition facts",
        )
    lines = [
        "mod generated;",
        "",
        "fn main() {",
        f'    println!("SignedOverflow={{}}", generated::addsigned({_OVERFLOW_FUNCTIONS["addsigned"][0]}, {_OVERFLOW_FUNCTIONS["addsigned"][1]}));',
        f'    println!("UnsignedOverflow={{}}", generated::addunsigned({_OVERFLOW_FUNCTIONS["addunsigned"][0]}, {_OVERFLOW_FUNCTIONS["addunsigned"][1]}));',
        "}",
    ]
    return "overflow", lines


def _boolean_comparison_branch_harness(
    facts: dict[str, Any],
) -> tuple[str, list[str]] | dict[str, Any]:
    """Build the Rust harness that exercises each emitted Boolean comparison branch."""

    functions = [
        fact
        for fact in facts.get("facts", [])
        if fact.get("kind") == "boolean_comparison_branch_function"
    ]
    if not functions:
        return _status(
            "blocked",
            reason="boolean comparison branch oracle requires at least one comparison fact",
        )
    lines = ["mod generated;", "", "fn main() {"]
    for fact in functions:
        name = str(fact.get("name", ""))
        emitted = name.casefold()
        for left, right in _BOOLEAN_COMPARISON_INPUTS:
            lines.append(
                f'    println!("{name}({left},{right})={{}}", '
                f"generated::{emitted}({left}, {right}) as i32);"
            )
    lines.append("}")
    return "boolean-comparison", lines


def _oracle_harness(facts: dict[str, Any]) -> tuple[str, list[str]] | dict[str, Any] | None:
    """Select the executable oracle harness for the extracted fact kinds, if any."""

_STRING_LENGTH_INPUTS: tuple[tuple[str, str], ...] = (
    ("hello", "hello"),
    ("empty", ""),
    ("abcde", "abcde"),
)


def _boolean_comparison_expression_harness(
    facts: dict[str, Any],
) -> tuple[str, list[str]] | dict[str, Any]:
    """Harness exercising each emitted Boolean comparison expression function."""

    functions = [
        fact
        for fact in facts.get("facts", [])
        if fact.get("kind") == "boolean_comparison_expression_function"
    ]
    if not functions:
        return _status("blocked", reason="oracle requires a boolean comparison expression fact")
    lines = ["mod generated;", "", "fn main() {"]
    for fact in functions:
        name = str(fact.get("name", ""))
        emitted = name.casefold()
        for left, right in _BOOLEAN_COMPARISON_INPUTS:
            lines.append(
                f'    println!("{name}({left},{right})={{}}", '
                f"generated::{emitted}({left}, {right}) as i32);"
            )
    lines.append("}")
    return "boolean-expression", lines


def _string_length_harness(
    facts: dict[str, Any],
) -> tuple[str, list[str]] | dict[str, Any]:
    """Harness exercising each emitted string-length function."""

    functions = [
        fact for fact in facts.get("facts", []) if fact.get("kind") == "string_length_function"
    ]
    if not functions:
        return _status("blocked", reason="oracle requires a string length fact")
    lines = ["mod generated;", "", "fn main() {"]
    for fact in functions:
        name = str(fact.get("name", ""))
        emitted = name.casefold()
        for label, value in _STRING_LENGTH_INPUTS:
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(
                f'    println!("{name}({label})={{}}", generated::{emitted}("{escaped}"));'
            )
    lines.append("}")
    return "string-length", lines


def _scalar_layout_harness(
    facts: dict[str, Any],
) -> tuple[str, list[str]] | dict[str, Any]:
    """Harness reproducing the ScalarLayout program output from emitted functions."""

    layout = next(
        (fact for fact in facts.get("facts", []) if fact.get("kind") == "scalar_layout_program"),
        None,
    )
    if layout is None:
        return _status("blocked", reason="oracle requires a scalar layout program fact")
    lines = ["mod generated;", "", "fn main() {"]
    for entry in layout.get("size_of", []):
        delphi_type = entry["type"]
        lines.append(
            f'    println!("{delphi_type.title()}={{}}", generated::size_of_{delphi_type}());'
        )
    for entry in layout.get("typed_additions", []):
        delphi_type = entry["type"]
        label = "AddSigned" if delphi_type == "integer" else "AddUnsigned"
        lines.append(f'    println!("{label}={{}}", generated::add_{delphi_type}());')
    lines.append("}")
    return "scalar-layout", lines


def _scalar_division_harness(
    facts: dict[str, Any],
) -> tuple[str, list[str]] | dict[str, Any]:
    """Harness exercising truncating integer division against fixed cases.

    Inputs cover positive and negative (truncate-toward-zero) signed division and
    an unsigned case; the labels match the oracle fixture's ``Writeln`` output
    exactly so the normalized stdout comparison is meaningful.
    """

    names = {
        str(fact.get("name", "")).casefold()
        for fact in facts.get("facts", [])
        if fact.get("kind") == "scalar_division_function"
    }
    cases = [
        ("divsigned", 7, 2),
        ("divsigned", -7, 2),
        ("divunsigned", 100, 7),
    ]
    required = {name for name, _, _ in cases}
    if not required.issubset(names):
        return _status(
            "blocked",
            reason="division oracle requires DivSigned and DivUnsigned division facts",
        )
    lines = ["mod generated;", "", "fn main() {"]
    for name, left, right in cases:
        lines.append(
            f'    println!("{name}({left},{right})={{}}", generated::{name}({left}, {right}));'
        )
    lines.append("}")
    return "scalar-division", lines


_MUL_OVERFLOW_FUNCTIONS = {
    "mulsigned": ("i32::MAX", "2"),
    "mulunsigned": ("u32::MAX", "2"),
}


def _scalar_multiplication_harness(
    facts: dict[str, Any],
) -> tuple[str, list[str]] | dict[str, Any]:
    """Harness exercising integer multiplication at the modular overflow boundary.

    Using the overflow boundary (MAX * 2) is deliberate: it is the input that
    distinguishes faithful modular (wrapping) multiplication from a naive `*`
    that would panic or diverge, so the oracle actually proves the semantics.
    """

    functions = {
        str(fact.get("name", "")).casefold()
        for fact in facts.get("facts", [])
        if fact.get("kind") == "scalar_multiplication_function"
    }
    if set(functions) != set(_MUL_OVERFLOW_FUNCTIONS):
        return _status(
            "blocked",
            reason="multiplication oracle requires MulSigned and MulUnsigned facts",
        )
    lines = [
        "mod generated;",
        "",
        "fn main() {",
        f'    println!("SignedOverflow={{}}", generated::mulsigned({_MUL_OVERFLOW_FUNCTIONS["mulsigned"][0]}, {_MUL_OVERFLOW_FUNCTIONS["mulsigned"][1]}));',
        f'    println!("UnsignedOverflow={{}}", generated::mulunsigned({_MUL_OVERFLOW_FUNCTIONS["mulunsigned"][0]}, {_MUL_OVERFLOW_FUNCTIONS["mulunsigned"][1]}));',
        "}",
    ]
    return "multiplication-overflow", lines


_SUB_UNDERFLOW_FUNCTIONS = {
    "subsigned": ("i32::MIN", "1"),
    "subunsigned": ("0u32", "1"),
}


def _scalar_subtraction_harness(
    facts: dict[str, Any],
) -> tuple[str, list[str]] | dict[str, Any]:
    """Harness exercising integer subtraction at the modular underflow boundary.

    The boundary (MIN - 1 / 0 - 1) distinguishes faithful modular (wrapping)
    subtraction from a naive `-` that would panic or diverge, so the oracle
    actually proves the semantics.
    """

    functions = {
        str(fact.get("name", "")).casefold()
        for fact in facts.get("facts", [])
        if fact.get("kind") == "scalar_subtraction_function"
    }
    if set(functions) != set(_SUB_UNDERFLOW_FUNCTIONS):
        return _status(
            "blocked",
            reason="subtraction oracle requires SubSigned and SubUnsigned facts",
        )
    lines = [
        "mod generated;",
        "",
        "fn main() {",
        f'    println!("SignedUnderflow={{}}", generated::subsigned({_SUB_UNDERFLOW_FUNCTIONS["subsigned"][0]}, {_SUB_UNDERFLOW_FUNCTIONS["subsigned"][1]}));',
        f'    println!("UnsignedUnderflow={{}}", generated::subunsigned({_SUB_UNDERFLOW_FUNCTIONS["subunsigned"][0]}, {_SUB_UNDERFLOW_FUNCTIONS["subunsigned"][1]}));',
        "}",
    ]
    return "subtraction-underflow", lines


def _oracle_harness(facts: dict[str, Any]) -> tuple[str, list[str]] | dict[str, Any] | None:
    """Select the executable oracle harness for the extracted fact kinds, if any."""

    kinds = {fact.get("kind") for fact in facts.get("facts", [])}
    if "scalar_addition_function" in kinds:
        return _scalar_overflow_harness(facts)
    if "scalar_division_function" in kinds:
        return _scalar_division_harness(facts)
    if "scalar_multiplication_function" in kinds:
        return _scalar_multiplication_harness(facts)
    if "scalar_subtraction_function" in kinds:
        return _scalar_subtraction_harness(facts)
    if "boolean_comparison_branch_function" in kinds:
        return _boolean_comparison_branch_harness(facts)
    if "boolean_comparison_expression_function" in kinds:
        return _boolean_comparison_expression_harness(facts)
    if "string_length_function" in kinds:
        return _string_length_harness(facts)
    if "scalar_layout_program" in kinds:
        return _scalar_layout_harness(facts)
    return None


def _executable_oracle(
    fixture: Path,
    facts: dict[str, Any],
    output_directory: Path,
) -> dict[str, Any]:
    """Compare compiled source program stdout against the generated Rust harness.

    The oracle is data-driven: it runs only when the fixture compiled to an
    executable program (not a source unit) and the extracted facts name a known
    executable harness. It compiles and runs both the FPC source program and the
    generated Rust (emitted purely from the active ``rules/*.json`` output shape)
    and compares their normalized stdout exactly.
    """

    source_executable = output_directory / fixture.stem
    if not source_executable.exists():
        return _status(
            "skipped",
            reason="the fixture is a source unit without an executable source/target harness",
        )
    harness = _oracle_harness(facts)
    if harness is None:
        return _status(
            "skipped",
            reason="no executable oracle is defined for the extracted facts",
        )
    if isinstance(harness, dict):
        return harness
    name, main_lines = harness
    rustc = shutil.which("rustc")
    if rustc is None:
        return _status("blocked", reason="Rust compiler (`rustc`) is unavailable")
    generated = output_directory / "generated.rs"
    main = output_directory / "oracle_main.rs"
    executable = output_directory / f"sourcebridge-{name}-oracle"
    generated.write_text(emit(facts, _load_rules()), encoding="utf-8")
    main.write_text("\n".join(main_lines) + "\n", encoding="utf-8")
    compilation = subprocess.run(
        [rustc, "--edition", "2021", str(main), "-o", str(executable)],
        check=False,
        capture_output=True,
        text=True,
    )
    if compilation.returncode:
        return _status(
            "failed",
            compiler=rustc,
            diagnostic=(compilation.stdout + compilation.stderr).strip()[-4_000:],
        )
    source_execution = subprocess.run(
        [str(source_executable)],
        check=False,
        capture_output=True,
        text=True,
    )
    if source_execution.returncode:
        return _status(
            "failed",
            reason="the compiled source fixture did not execute",
            diagnostic=(source_execution.stdout + source_execution.stderr).strip()[-4_000:],
        )
    target_execution = subprocess.run(
        [str(executable)],
        check=False,
        capture_output=True,
        text=True,
    )
    if target_execution.returncode:
        return _status(
            "failed",
            reason="the generated Rust oracle harness did not execute",
            diagnostic=(target_execution.stdout + target_execution.stderr).strip()[-4_000:],
        )
    source_output = source_execution.stdout.splitlines()
    target_output = target_execution.stdout.splitlines()
    details = {
        "source_output": source_output,
        "target_output": target_output,
    }
    if source_output != target_output:
        return _status("failed", reason="normalized source and target output differ", **details)
    return _status("passed", **details)


def _program_rule() -> dict[str, Any] | None:
    """Return the active statement-level (program_body) rule, if any."""

    for rule in _load_rules():
        shape = rule.get("output_shape", {})
        if shape.get("kind") == "statements" and rule.get("applies_to", {}).get(
            "source_fact_kind"
        ) == "program_body":
            return rule
    return None


def _compile_rust_program(facts: dict[str, Any], output_directory: Path) -> dict[str, Any]:
    """Emit and compile the incremental program port as a runnable Rust binary."""

    rustc = shutil.which("rustc")
    if rustc is None:
        return _status("blocked", reason="Rust compiler (`rustc`) is unavailable")
    rule = _program_rule()
    if rule is None:
        return _status("blocked", reason="no active program_body rule to port statements")
    body = next((f for f in facts["facts"] if f.get("kind") == "program_body"), None)
    if body is None:
        return _status("blocked", reason="facts contain no program_body to port")
    result = emit_program(body, rule)
    artifact = result["rust"]
    source = output_directory / "generated_program.rs"
    binary = output_directory / "generated_program"
    source.write_text(artifact, encoding="utf-8")
    command = [rustc, "--edition", "2021", str(source), "-o", str(binary)]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    details = {
        "compiler": rustc,
        "command": command,
        "artifact_path": source.name,
        "artifact_digest": hashlib.sha256(artifact.encode("utf-8")).hexdigest(),
        "ported_statements": result["ported"],
        "unported_statements": result["unported"],
    }
    if completed.returncode:
        details["diagnostic"] = (completed.stdout + completed.stderr).strip()[-4_000:]
        return _status("failed", **details)
    return _status("passed", artifact_content=artifact, **details)


def _program_oracle(
    fixture: Path, facts: dict[str, Any], output_directory: Path
) -> dict[str, Any]:
    """Run the compiled FPC program and the emitted Rust program; compare output.

    The emitted Rust program is a full ``fn main`` (``writeln`` -> ``println!``,
    ``halt(n)`` -> ``process::exit(n)``), so the oracle executes both and compares
    normalized stdout AND exit code exactly. A port with unported (stubbed)
    statements still compiles and runs; the oracle then reports the mismatch
    honestly rather than hiding the gap.
    """

    source_executable = output_directory / fixture.stem
    rust_executable = output_directory / "generated_program"
    if not source_executable.exists():
        return _status("skipped", reason="the fixture did not compile to an executable program")
    if not rust_executable.exists():
        return _status("blocked", reason="the emitted Rust program was not compiled")
    source_execution = subprocess.run(
        [str(source_executable)], check=False, capture_output=True, text=True
    )
    target_execution = subprocess.run(
        [str(rust_executable)], check=False, capture_output=True, text=True
    )
    details = {
        "source_output": source_execution.stdout.splitlines(),
        "target_output": target_execution.stdout.splitlines(),
        "source_exit": source_execution.returncode,
        "target_exit": target_execution.returncode,
    }
    if (
        source_execution.stdout != target_execution.stdout
        or source_execution.returncode != target_execution.returncode
    ):
        return _status("failed", reason="normalized source and target output differ", **details)
    return _status("passed", **details)


def run_test(fixture: Path, variant_path: Path, fpc: str) -> dict[str, Any]:
    variant = _variant(variant_path)
    source: dict[str, Any]
    extraction: dict[str, Any]
    with tempfile.TemporaryDirectory(prefix="sourcebridge-delphi-engine-test-") as output:
        source = _compile(fixture, fpc, variant, Path(output))
        mode = "function"
        facts = None
        try:
            facts = extract(fixture, variant_path)
        except (ExtractionError, OSError, ValueError):
            try:
                facts = extract_program_body(fixture)
                mode = "program"
            except (ExtractionError, OSError, ValueError) as error:
                extraction = _status("failed", diagnostic=str(error))
        if facts is not None:
            extraction = _status(
                "passed",
                mode=mode,
                fact_count=len(facts["facts"]),
                functions=[fact.get("name") for fact in facts["facts"]],
                variant=variant["compiler"],
            )
        if extraction["status"] != "passed":
            target = _status(
                "blocked", reason="source extraction did not produce target-emittable facts"
            )
        elif mode == "program":
            target = _compile_rust_program(facts, Path(output))
        else:
            target = _compile_rust(facts, Path(output))
        if not (
            source["status"] == "passed"
            and extraction["status"] == "passed"
            and target["status"] == "passed"
        ):
            oracle = _status(
                "blocked",
                reason="source, extraction, and target must pass before oracle execution",
            )
        elif mode == "program":
            oracle = _program_oracle(fixture, facts, Path(output))
        else:
            oracle = _executable_oracle(fixture, facts, Path(output))
    return {
        "schema_version": 1,
        "source": source,
        "extraction": extraction,
        "target": target,
        "oracle": oracle,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--variant", type=Path, default=DEFAULT_VARIANT)
    parser.add_argument("--fpc", default=os.environ.get("SOURCEBRIDGE_FPC", "fpc"))
    args = parser.parse_args(argv)
    try:
        result = run_test(args.fixture.resolve(), args.variant.resolve(), args.fpc)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
