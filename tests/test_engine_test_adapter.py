from __future__ import annotations

import json
from pathlib import Path
import unittest

from tools.run_sourcebridge_engine_test import run_test


ROOT = Path(__file__).parents[1]


def _catalogue() -> dict:
    return json.loads((ROOT / "engine-tests.json").read_text(encoding="utf-8"))


class EngineTestCatalogueTests(unittest.TestCase):
    """Data-driven checks: a rule is proven by its catalogue entry + oracle +
    census, not by a bespoke per-rule Python test. Adding a rule needs no edit
    here -- these derive everything from the versioned data files."""

    def test_catalogue_structure_and_stable_ids(self) -> None:
        catalogue = _catalogue()
        self.assertEqual(catalogue["schema_version"], 1)
        ids = [case["id"] for case in catalogue["tests"]]
        self.assertTrue(ids, "catalogue must declare engine tests")
        self.assertEqual(len(ids), len(set(ids)), "engine-test ids must be unique")
        # Non-C# id range; never reuse the retired C# block.
        self.assertTrue(all(isinstance(i, int) and i >= 437 for i in ids))
        self.assertTrue(set(ids).isdisjoint({434, 435, 436}))
        for case in catalogue["tests"]:
            self.assertIn("fixture", case)
            for side in ("source", "extraction", "target", "oracle"):
                self.assertIn(case["expected"][side]["status"],
                              {"passed", "failed", "blocked", "skipped"})

    def test_catalogue_entries_match_their_declared_statuses(self) -> None:
        # Corpus-style proof: run every registered engine test through the
        # adapter and assert each side matches the status the catalogue declares.
        catalogue = _catalogue()
        variant = ROOT / "variants" / "fpc-3.2.3-x86_64-linux.json"
        for case in catalogue["tests"]:
            with self.subTest(test_id=case["id"], fixture=case["fixture"]):
                result = run_test(ROOT / case["fixture"], variant, "fpc")
                self.assertEqual(result["schema_version"], 1)
                for side in ("source", "extraction", "target", "oracle"):
                    self.assertEqual(
                        result[side]["status"],
                        case["expected"][side]["status"],
                        f"{case['fixture']} {side}",
                    )

    def test_basics_curriculum_is_consistent(self) -> None:
        curriculum = json.loads(
            (ROOT / "rule-curriculum.json").read_text(encoding="utf-8")
        )
        catalogue_ids = {case["id"] for case in _catalogue()["tests"]}
        rule_keys = {
            json.loads(path.read_text(encoding="utf-8"))["rule_key"]
            for path in (ROOT / "rules").glob("*.json")
        }
        entries = curriculum["entries"]
        self.assertEqual(curriculum["selector"], "basics")
        orders = [entry["order"] for entry in entries]
        self.assertEqual(orders, list(range(1, len(entries) + 1)),
                         "curriculum orders must be contiguous from 1")
        for entry in entries:
            self.assertIn(entry["test_id"], catalogue_ids,
                          f"curriculum references unknown engine test {entry['test_id']}")
            self.assertIn(entry["rule"], rule_keys,
                          f"curriculum references unknown rule {entry['rule']}")


if __name__ == "__main__":
    unittest.main()
