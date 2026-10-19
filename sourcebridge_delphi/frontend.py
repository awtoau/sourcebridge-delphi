"""Unified Delphi/FPC frontend: compiler-grounded first, regex fallback.

Extraction prefers Free Pascal's own parser via `pasfacts` (fcl-passrc) — a
real AST, the way the C# pack uses Roslyn and the C pack uses clang. It falls
back to the bounded regex extractor only for shapes the AST pass does not yet
emit (today: the scalar-layout program), or when FPC/fcl-passrc is unavailable.

The public `extract` keeps the existing signature and raises the existing
`ExtractionError`, so the engine-test adapter is unchanged apart from the
import.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sourcebridge_delphi.extract import ExtractionError
from sourcebridge_delphi.extract import extract as _regex_extract
from sourcebridge_delphi.pasfacts import PasFactsError
from sourcebridge_delphi.pasfacts import extract_facts as _pasfacts


def extract(path: Path, variant_path: Path | None = None) -> dict[str, Any]:
    """Extract facts via FPC's parser, falling back to the regex extractor."""

    path = Path(path)
    facts: list[dict[str, Any]] | None = None
    try:
        parsed = _pasfacts(path)
        facts = parsed.get("facts", [])
    except PasFactsError:
        facts = None  # FPC/fcl-passrc unavailable or parse failed; use fallback.

    if facts:
        return {
            "schema_version": 1,
            "source_language": "delphi",
            "source_path": path.as_posix(),
            "facts": facts,
            "extractor": "fcl-passrc",
        }

    # Fallback: bounded regex extractor (e.g. scalar-layout program), which
    # raises ExtractionError when it, too, finds no supported construct.
    fallback = _regex_extract(path, variant_path)
    fallback["extractor"] = "regex-fallback"
    return fallback


def extract_program_body(path: Path) -> dict[str, Any]:
    """Extract the incremental ``program_body`` statement inventory via FPC's parser.

    This is the program-level counterpart to :func:`extract`: it asks the
    fcl-passrc extractor for the structured main-block statement list used by the
    incremental porter. It raises :class:`ExtractionError` when the file has no
    convertible program body (e.g. it is a unit, or the parser is unavailable).
    """

    path = Path(path)
    try:
        parsed = _pasfacts(path, program_body=True)
    except PasFactsError as error:
        raise ExtractionError(f"{path}: {error}") from error
    bodies = [f for f in parsed.get("facts", []) if f.get("kind") == "program_body"]
    if not bodies:
        raise ExtractionError(f"{path}: no program body statements to port")
    return {
        "schema_version": 1,
        "source_language": "delphi",
        "source_path": path.as_posix(),
        "facts": bodies,
        "extractor": "fcl-passrc",
    }


__all__ = ["extract", "extract_program_body", "ExtractionError"]
