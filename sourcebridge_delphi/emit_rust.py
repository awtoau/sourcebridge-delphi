"""Apply versioned Rust output-shape rules to verified Delphi extraction facts.

This module is a deterministic interpreter. It contains no language policy: the
Rust syntax, type mapping, and operator mapping come from the rule definitions
passed in (see ``rules/*.json``). An unmatched fact is an explicit gap, never a
hardcoded fallback.
"""

from __future__ import annotations

from typing import Any


class RustEmissionError(ValueError):
    """Raised when facts cannot be emitted under the supplied rules."""


def _rules_by_fact_kind(rules: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for rule in rules:
        applies = rule.get("applies_to", {})
        kind = applies.get("source_fact_kind")
        shape = rule.get("output_shape", {})
        if shape.get("kind") == "statements":
            continue  # incremental program-body rules are emitted by porter.py
        if not isinstance(kind, str) or shape.get("target") != "rust":
            raise RustEmissionError(f"rule `{rule.get('rule_key')}` has no Rust output shape")
        if shape.get("kind") == "program":
            if not isinstance(shape.get("emitters"), list) or not shape["emitters"]:
                raise RustEmissionError(f"rule `{rule.get('rule_key')}` has no Rust output shape")
        elif "body" not in shape:
            raise RustEmissionError(f"rule `{rule.get('rule_key')}` has no Rust output shape")
        index[kind] = rule
    return index


def _signature(fact: dict[str, Any], type_map: dict[str, str]) -> tuple[str, list[str], str]:
    try:
        name = str(fact["name"]).lower()
        parameters = [f"{p['name'].lower()}: {type_map[p['type']]}" for p in fact["parameters"]]
        return_type = type_map[fact["return_type"]]
    except (KeyError, TypeError) as error:
        raise RustEmissionError(f"fact not expressible under rule type map: {error}") from error
    return name, parameters, return_type


def _body(shape: dict[str, Any], fact: dict[str, Any]) -> str:
    operands = fact.get("operands")
    if not isinstance(operands, list) or len(operands) != 2:
        raise RustEmissionError("supported facts require two operands")
    substitutions = {"op0": operands[0].lower(), "op1": operands[1].lower()}
    if "{operator}" in shape["body"]:
        operator = shape.get("operator_map", {}).get(fact.get("operator"))
        if operator is None:
            raise RustEmissionError(f"rule has no operator mapping for `{fact.get('operator')}`")
        substitutions["operator"] = operator
    try:
        return shape["body"].format(**substitutions)
    except KeyError as error:
        raise RustEmissionError(f"rule body references unknown placeholder {error}") from error


def _program_functions(shape: dict[str, Any], fact: dict[str, Any]) -> list[str]:
    """Render one Rust function per structured entry, driven entirely by rule data."""

    type_map = shape.get("type_map", {})
    functions: list[str] = []
    for emitter in shape["emitters"]:
        try:
            source_field = emitter["from"]
            signature_template = emitter["signature"]
            body_template = emitter["body"]
        except KeyError as error:
            raise RustEmissionError(f"program emitter missing {error}") from error
        entries = fact.get(source_field)
        if not isinstance(entries, list):
            raise RustEmissionError(f"fact has no `{source_field}` list to emit")
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise RustEmissionError(f"`{source_field}` entries must be objects")
            substitutions = dict(entry)
            substitutions["index"] = index
            delphi_type = entry.get("type")
            if delphi_type is not None:
                if delphi_type not in type_map:
                    raise RustEmissionError(
                        f"rule type map has no entry for `{delphi_type}`"
                    )
                substitutions["rust_type"] = type_map[delphi_type]
            try:
                signature = signature_template.format(**substitutions)
                body = body_template.format(**substitutions)
            except KeyError as error:
                raise RustEmissionError(
                    f"rule template references unknown placeholder {error}"
                ) from error
            functions.append(f"{signature} {{\n    {body}\n}}")
    if not functions:
        raise RustEmissionError("program fact produced no emittable entries")
    return functions


def emit(facts: dict[str, Any], rules: list[dict[str, Any]]) -> str:
    """Emit a Rust module by applying the supplied output-shape rules to facts."""

    index = _rules_by_fact_kind(rules)
    functions: list[str] = []
    applied: list[str] = []
    for fact in facts.get("facts", []):
        kind = fact.get("kind")
        rule = index.get(kind)
        if rule is None:
            raise RustEmissionError(f"no active rule for extracted fact kind `{kind}`")
        shape = rule["output_shape"]
        if shape.get("kind") == "program":
            functions.extend(_program_functions(shape, fact))
        else:
            name, parameters, return_type = _signature(fact, shape["type_map"])
            functions.append(
                f"pub fn {name}({', '.join(parameters)}) -> {return_type} {{\n"
                f"    {_body(shape, fact)}\n"
                "}"
            )
        applied.append(rule["rule_key"])
    if not functions:
        raise RustEmissionError("no supported extracted functions to emit")
    return "\n".join(
        [
            "// SOURCEBRIDGE INPUT:",
            f"// - source: {facts.get('source_path')}",
            "//",
            "// SOURCEBRIDGE RULES:",
            *[f"// - {key}" for key in sorted(set(applied))],
            "//",
            "// SOURCEBRIDGE GAPS:",
            "// - none in this bounded emitted module",
            "//",
            "// SOURCEBRIDGE VALIDATION:",
            "// - source/target/oracle: recorded by the invoking adapter",
            "",
            *functions,
            "",
        ]
    )
