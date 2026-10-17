"""Extract Delphi language-basics facts from a constrained fixture grammar."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


_UNIT = re.compile(r"^unit\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*;$", re.IGNORECASE)
_SIGNATURE = re.compile(
    r"^function\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"\((?P<parameters>[^)]*)\)\s*:\s*(?P<return>Integer|Cardinal|Boolean)\s*;$",
    re.IGNORECASE,
)
_PARAMETER = re.compile(
    r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<type>Integer|Cardinal)$",
    re.IGNORECASE,
)
_ASSIGNMENT = re.compile(
    r"^Result\s*:=\s*(?P<left>[A-Za-z_][A-Za-z0-9_]*)\s*\+\s*"
    r"(?P<right>[A-Za-z_][A-Za-z0-9_]*)\s*;$",
    re.IGNORECASE,
)
_COMPARISON = re.compile(
    r"^if\s+(?P<left>[A-Za-z_][A-Za-z0-9_]*)\s*"
    r"(?P<operator>=|<>|<|>|<=|>=)\s*"
    r"(?P<right>[A-Za-z_][A-Za-z0-9_]*)\s+then$",
    re.IGNORECASE,
)
_BOOLEAN_ASSIGNMENT = re.compile(
    r"^Result\s*:=\s*(?P<value>True|False)\s*;?$", re.IGNORECASE
)


class ExtractionError(ValueError):
    """Raised when input is outside the explicitly supported Stage-1 grammar."""


def _source_span(line: int) -> dict[str, int]:
    return {"start_line": line, "end_line": line}


def _parameters(text: str, line: int) -> list[dict[str, str]]:
    if not text.strip():
        return []
    values: list[dict[str, str]] = []
    for item in text.split(";"):
        match = _PARAMETER.fullmatch(item.strip())
        if match is None:
            raise ExtractionError(f"line {line}: unsupported parameter `{item.strip()}`")
        values.append({"name": match["name"], "type": match["type"].lower()})
    return values


def _variant(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ExtractionError(f"{path}: cannot read variant: {error}") from error
    if not isinstance(data, dict) or not isinstance(data.get("compiler"), dict):
        raise ExtractionError(f"{path}: variant must contain a compiler object")
    return data


def extract(path: Path, variant_path: Path | None = None) -> dict[str, Any]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ExtractionError(f"{path}: cannot read source: {error}") from error
    unit_name: str | None = None
    declarations: dict[str, tuple[list[dict[str, str]], str, int]] = {}
    facts: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        line_number = index + 1
        text = lines[index].strip()
        index += 1
        if not text or text.lower() in {"interface", "implementation", "end."}:
            continue
        unit = _UNIT.fullmatch(text)
        if unit is not None:
            if unit_name is not None:
                raise ExtractionError(f"line {line_number}: duplicate unit declaration")
            unit_name = unit["name"]
            continue
        signature = _SIGNATURE.fullmatch(text)
        if signature is None:
            continue
        parameters = _parameters(signature["parameters"], line_number)
        name = signature["name"]
        return_type = signature["return"].lower()
        if index < len(lines) and lines[index].strip().lower() == "begin":
            index += 1
            if index >= len(lines):
                raise ExtractionError(f"line {line_number}: function body is incomplete")
            parameter_names = {parameter["name"].casefold() for parameter in parameters}
            operation_line = index + 1
            operation = lines[index].strip()
            if (assignment := _ASSIGNMENT.fullmatch(operation)) is not None:
                index += 1
                operands = [assignment["left"], assignment["right"]]
                if any(operand.casefold() not in parameter_names for operand in operands):
                    raise ExtractionError(
                        f"line {operation_line}: addition operands must be declared parameters")
                facts.append(
                    {
                        "kind": "scalar_addition_function",
                        "name": name,
                        "parameters": parameters,
                        "return_type": return_type,
                        "operands": operands,
                        "signature_span": _source_span(line_number),
                        "operation_span": _source_span(operation_line),
                    }
                )
            elif (comparison := _COMPARISON.fullmatch(operation)) is not None:
                if return_type != "boolean":
                    raise ExtractionError(
                        f"line {line_number}: comparison branch must return Boolean")
                operands = [comparison["left"], comparison["right"]]
                if any(operand.casefold() not in parameter_names for operand in operands):
                    raise ExtractionError(
                        f"line {operation_line}: comparison operands must be declared parameters")
                index += 1
                if index >= len(lines):
                    raise ExtractionError(f"line {operation_line}: branch body is incomplete")
                true_line = index + 1
                true_assignment = _BOOLEAN_ASSIGNMENT.fullmatch(lines[index].strip())
                index += 1
                if true_assignment is None or true_assignment["value"].casefold() != "true":
                    raise ExtractionError(
                        f"line {true_line}: true branch must assign `Result := True`")
                if index >= len(lines) or lines[index].strip().lower() != "else":
                    raise ExtractionError(f"line {true_line}: comparison branch must have `else`")
                index += 1
                if index >= len(lines):
                    raise ExtractionError(f"line {true_line}: false branch is incomplete")
                false_line = index + 1
                false_assignment = _BOOLEAN_ASSIGNMENT.fullmatch(lines[index].strip())
                index += 1
                if false_assignment is None or false_assignment["value"].casefold() != "false":
                    raise ExtractionError(
                        f"line {false_line}: false branch must assign `Result := False`")
                facts.append(
                    {
                        "kind": "boolean_comparison_branch_function",
                        "name": name,
                        "parameters": parameters,
                        "return_type": return_type,
                        "operands": operands,
                        "operator": comparison["operator"],
                        "true_value": True,
                        "false_value": False,
                        "signature_span": _source_span(line_number),
                        "operation_span": _source_span(operation_line),
                    }
                )
            else:
                raise ExtractionError(
                    f"line {operation_line}: only `Result := Left + Right` or a Boolean comparison branch is supported")
            if index >= len(lines) or lines[index].strip().lower() != "end;":
                raise ExtractionError(f"line {operation_line}: function must end with `end;`")
            index += 1
        else:
            declarations[name.casefold()] = (parameters, return_type, line_number)
    if unit_name is None:
        raise ExtractionError(f"{path}: missing unit declaration")
    if not facts:
        raise ExtractionError(f"{path}: no supported function implementations found")
    result = {
        "schema_version": 1,
        "source_language": "delphi",
        "source_path": path.as_posix(),
        "unit": unit_name,
        "facts": facts,
        "limitations": [
            "fixture grammar only",
            "no compiler, dialect, or runtime validation",
        ],
    }
    variant = _variant(variant_path)
    if variant is not None:
        result["variant"] = variant
        result["limitations"] = ["fixture grammar only"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--variant", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(extract(args.source, args.variant), indent=2, sort_keys=True))
    except ExtractionError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
