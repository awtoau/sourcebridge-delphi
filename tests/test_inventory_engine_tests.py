from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tools import inventory_engine_tests as inventory
from tools import monitor_ollama


ROOT = Path(__file__).parents[1]


class EngineTestInventoryTests(unittest.TestCase):
    def test_deterministic_report_records_fixture_digest_and_declared_fallback(self) -> None:
        with patch.object(inventory, "run_adapter", return_value=(None, "unavailable")):
            report = inventory.build_report(ROOT / "engine-tests.json")
        self.assertEqual(report["mode"], "deterministic-only")
        self.assertEqual(len(report["tests"]), 2)
        first = report["tests"][0]
        expected = hashlib.sha256(
            (ROOT / "fixtures" / "scalars.pas").read_bytes()
        ).hexdigest()
        self.assertEqual(first["fixture_sha256"], expected)
        self.assertEqual(first["status_source"], "catalogue_declared_outcome")
        self.assertEqual(first["statuses"]["target"]["status"], "blocked")
        self.assertNotIn("ollama", first)

    def test_structured_adapter_statuses_are_preserved(self) -> None:
        adapter_result = {
            "schema_version": 1,
            "source": {"status": "passed"},
            "extraction": {"status": "failed", "diagnostic": "fixture"},
            "target": {"status": "blocked"},
            "oracle": {"status": "skipped"},
        }
        with patch.object(inventory, "run_adapter", return_value=(adapter_result, None)):
            report = inventory.build_report(ROOT / "engine-tests.json")
        self.assertEqual(report["tests"][0]["status_source"], "structured_adapter")
        self.assertEqual(
            report["tests"][0]["statuses"]["extraction"]["diagnostic"], "fixture"
        )

    @patch("tools.inventory_engine_tests.request.urlopen")
    def test_ollama_enrichment_retains_raw_response_and_digests(self, urlopen) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(
                    {
                        "response": json.dumps(
                            {
                                "language_features": ["function"],
                                "complexity_band": "small",
                                "prerequisites": [],
                                "uncertainties": ["target unavailable"],
                            }
                        )
                    }
                ).encode()

        urlopen.return_value = Response()
        with patch.object(
            inventory,
            "run_adapter",
            return_value=(
                {
                    "source": {"status": "passed"},
                    "extraction": {"status": "passed"},
                    "target": {"status": "blocked"},
                    "oracle": {"status": "skipped"},
                },
                None,
            ),
        ):
            report = inventory.build_report(
                ROOT / "engine-tests.json",
                ollama_endpoint="http://localhost:11434",
                ollama_model="delphi-planner",
                ollama_digest="sha256:model",
            )
        self.assertEqual(urlopen.call_count, 2)
        enrichment = report["tests"][0]["ollama"]
        self.assertFalse(enrichment["authoritative"])
        self.assertEqual(enrichment["model_digest"], "sha256:model")
        self.assertIn('"language_features"', enrichment["raw_response"])
        self.assertEqual(
            enrichment["prompt_sha256"],
            inventory.sha256_text(
                inventory._prompt(
                    json.loads((ROOT / "engine-tests.json").read_text())["tests"][0],
                    (ROOT / "fixtures" / "scalars.pas").read_text(),
                    report["tests"][0]["fixture_sha256"],
                    report["tests"][0]["statuses"],
                )
            ),
        )

    @patch("tools.inventory_engine_tests.request.urlopen")
    def test_deterministic_mode_makes_no_model_request(self, urlopen) -> None:
        with patch.object(inventory, "run_adapter", return_value=(None, "blocked")):
            inventory.build_report(ROOT / "engine-tests.json")
        urlopen.assert_not_called()

    def test_requested_ollama_failure_is_not_embedded_in_report(self) -> None:
        with patch.object(inventory, "run_adapter", return_value=(None, "blocked")):
            with patch.object(
                inventory,
                "enrich",
                side_effect=ValueError("invalid strict JSON"),
            ):
                with self.assertRaises(inventory.OllamaEnrichmentError) as context:
                    inventory.build_report(
                        ROOT / "engine-tests.json",
                        ollama_endpoint="http://localhost:11434",
                        ollama_model="planner",
                        ollama_digest="sha256:model",
                    )
        self.assertIn("437", str(context.exception))

    @patch("tools.monitor_ollama.request.urlopen")
    def test_monitor_poll_selects_operational_model_fields(self, urlopen) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(
                    {
                        "models": [
                            {
                                "name": "planner:latest",
                                "digest": "sha256:model",
                                "size": 123,
                                "expires_at": "2026-10-17T14:00:00Z",
                                "ignored": "not reported",
                            }
                        ]
                    }
                ).encode()

        urlopen.return_value = Response()
        self.assertEqual(
            monitor_ollama.poll("http://localhost:11434"),
            [
                {
                    "name": "planner:latest",
                    "digest": "sha256:model",
                    "size": 123,
                    "expires_at": "2026-10-17T14:00:00Z",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
