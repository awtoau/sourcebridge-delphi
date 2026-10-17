from __future__ import annotations

import json
from pathlib import Path
import unittest

from tools.run_sourcebridge_engine_test import run_test


ROOT = Path(__file__).parents[1]


class EngineTestAdapterTests(unittest.TestCase):
    def test_stage1_result_has_source_and_extraction_evidence_only(self) -> None:
        result = run_test(
            ROOT / "fixtures" / "scalars.pas",
            ROOT / "variants" / "fpc-3.2.3-x86_64-linux.json",
            "fpc",
        )
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["source"]["status"], "passed")
        self.assertEqual(result["extraction"]["status"], "passed")
        self.assertEqual(result["target"]["status"], "blocked")
        self.assertEqual(result["oracle"]["status"], "skipped")

    def test_catalogue_uses_a_non_csharp_stable_id(self) -> None:
        catalogue = json.loads((ROOT / "engine-tests.json").read_text(encoding="utf-8"))
        ids = {case["id"] for case in catalogue["tests"]}
        self.assertEqual(ids, {437})
        self.assertTrue(ids.isdisjoint({434, 435, 436}))
