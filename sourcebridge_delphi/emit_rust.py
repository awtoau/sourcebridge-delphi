"""Emit bounded Rust modules from verified Delphi extraction facts."""

from __future__ import annotations

from typing import Any


class RustEmissionError(ValueError):
    """Raised when facts cannot be emitted as a complete Rust module."""


_TYPE_MAP = {"integer": "i32", "cardinal": "u32", "boolean": "bool"}
_COMPARISON_MAP = {"=": "==", "<>": "!=", "<": "<", ">": ">", "<=": "<=", ">=": ">="}


def emit(facts: dict[str, Any]) -> str:
    """Emit a compilable module for the supported constrained fixture grammar."""

    functions: list[str] = []
    source_path = facts.get("source_path")
    for fact in facts.get("facts", []):
        kind = fact.get("kind")
        if kind == "scalar_addition_function":
            functions.append(_emit_addition(fact))
        elif kind == "boolean_comparison_branch_function":
            functions.append(_emit_comparison(fact))
        else:
            raise RustEmissionError(f"unsupported extracted fact kind `{kind}`")
    if not functions:
        raise RustEmissionError("no supported extracted functions to emit")
    return "\n".join(
        [
            "// SOURCEBRIDGE INPUT:",
            f"// - source: {source_path}",
            "//",
            "// SOURCEBRIDGE RULES:",
            "// - delphi-stage1-rust/v1",
            "//",
            "// SOURCEBRIDGE GAPS:",
            "// - none in this bounded emitted module",
            "//",
            "// SOURCEBRIDGE VALIDATION:",
            "// - source: recorded by the invoking adapter",
            "// - target: recorded by the invoking adapter",
            "// - oracle: skipped when the source unit has no executable harness",
            "",
            *functions,
            "",
        ]
    )


def _signature(fact: dict[str, Any]) -> tuple[str, list[str], str]:
    try:
        name = str(fact["name"])
        parameters = [
            f"{parameter['name'].lower()}: {_TYPE_MAP[parameter['type']]}"
            for parameter in fact["parameters"]
        ]
        return_type = _TYPE_MAP[fact["return_type"]]
    except (KeyError, TypeError) as error:
        raise RustEmissionError("incomplete extracted function fact") from error
    return name.lower(), parameters, return_type


def _emit_addition(fact: dict[str, Any]) -> str:
    name, parameters, return_type = _signature(fact)
    operands = fact.get("operands")
    if not isinstance(operands, list) or len(operands) != 2:
        raise RustEmissionError("addition fact requires two operands")
    return (
        f"pub fn {name}({', '.join(parameters)}) -> {return_type} {{\n"
        f"    {operands[0].lower()}.wrapping_add({operands[1].lower()})\n"
        "}"
    )


def _emit_comparison(fact: dict[str, Any]) -> str:
    name, parameters, return_type = _signature(fact)
    operands = fact.get("operands")
    operator = _COMPARISON_MAP.get(fact.get("operator"))
    if not isinstance(operands, list) or len(operands) != 2 or operator is None:
        raise RustEmissionError("comparison fact requires two operands and a supported operator")
    return (
        f"pub fn {name}({', '.join(parameters)}) -> {return_type} {{\n"
        f"    {operands[0].lower()} {operator} {operands[1].lower()}\n"
        "}"
    )
