"""Incremental program-body porter: emit runnable Rust with graceful degradation.

This is the incremental-conversion core. It walks the ``program_body`` fact
produced by the fcl-passrc frontend and emits a Rust ``main`` where every
statement is EITHER ported (a real, data-driven translation under the active
rule) OR replaced with a clearly-marked stub comment. Unported constructs never
break the build: the emitted Rust always compiles and runs, it is just
incompletely ported. Teaching the converter one more construct is a rule/handler
change, not a rewrite.
"""

from __future__ import annotations

from typing import Any


class PortError(ValueError):
    """Raised when the program-body fact cannot be ported under the rule."""


def emit_program(fact: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    shape = rule["output_shape"]
    type_map = shape["type_map"]
    operator_map = shape["operator_map"]
    compare_map = shape["compare_map"]

    var_types = {v["name"]: v["type"] for v in fact.get("variables", [])}
    body: list[str] = []
    ported = 0
    unported = 0

    def stub(note: str) -> None:
        nonlocal unported
        body.append(f"    // UNPORTED: {note}")
        unported += 1

    for variable in fact.get("variables", []):
        rust_type = type_map.get(variable["type"])
        if rust_type is None:
            stub(f'var {variable["name"]}: {variable["type"]} (unmapped type)')
            continue
        body.append(f'    let mut {variable["name"]}: {rust_type} = 0;')

    for statement in fact.get("statements", []):
        kind = statement.get("stmt")
        if kind == "assign_const":
            rust_type = type_map.get(var_types.get(statement["target"], ""))
            if rust_type is None:
                stub(f'{statement["target"]} := {statement["value"]} (unmapped target)')
                continue
            body.append(f'    {statement["target"]} = ({statement["value"]}) as {rust_type};')
            ported += 1
        elif kind == "assign_binary":
            template = operator_map.get(statement.get("op"))
            rust_type = type_map.get(var_types.get(statement["target"], ""))
            if template is None or rust_type is None:
                stub(f'{statement["target"]} := {statement.get("left")} {statement.get("op")} {statement.get("right")}')
                continue
            rendered = template.format(l=statement["left"], r=statement["right"], t=rust_type)
            body.append(f'    {statement["target"]} = {rendered};')
            ported += 1
        elif kind == "writeln":
            body.append(f'    println!("{{}}", {statement["arg"]});')
            ported += 1
        elif kind == "if_halt":
            operator = compare_map.get(statement.get("op"))
            if operator is None:
                stub(f'if {statement.get("left")} {statement.get("op")} {statement.get("right")} then halt')
                continue
            body.append(
                f'    if {statement["left"]} {operator} {statement["right"]} '
                f'{{ std::process::exit({statement["code"]}); }}'
            )
            ported += 1
        else:
            stub(statement.get("note", "unsupported statement"))

    source = fact.get("source_path", "<unknown>")
    rust = "\n".join(
        [
            f"// SOURCEBRIDGE incremental port of {source}",
            f"// ported statements: {ported}; unported (stubbed): {unported}",
            "#![allow(unused_assignments, unused_mut, unused_variables)]",
            "",
            "fn main() {",
            *body,
            "}",
            "",
        ]
    )
    return {"rust": rust, "ported": ported, "unported": unported}
