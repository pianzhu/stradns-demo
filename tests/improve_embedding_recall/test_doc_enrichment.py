"""Tests for document enrichment helpers."""

import json
import logging
import tempfile
import unittest
from pathlib import Path

from context_retrieval.doc_enrichment import (
    CapabilityDoc,
    build_enriched_doc,
    enrich_description,
    load_spec_index,
)
from context_retrieval.models import Device


class TestLoadSpecIndex(unittest.TestCase):
    """Tests for spec index loading."""

    def test_load_spec_index(self):
        """Loads profiles and value descriptions."""
        data = [
            {
                "profileId": "p1",
                "capabilities": [
                    {
                        "id": "cap-on",
                        "description": "enable",
                        "value_list": [
                            {"value": "high", "description": "high"},
                            {"value": "low", "description": "low"},
                        ],
                    }
                ],
            },
            {"profileId": "p2", "capabilities": []},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spec.jsonl"
            path.write_text(json.dumps(data), encoding="utf-8")

            index = load_spec_index(str(path))

        self.assertIn("p1", index)
        self.assertIn("p2", index)
        self.assertEqual(index["p2"], [])
        self.assertEqual(len(index["p1"]), 1)
        self.assertEqual(index["p1"][0].id, "cap-on")
        self.assertEqual(index["p1"][0].value_descriptions, ["high", "low"])

    def test_load_spec_index_ignores_empty_value_descriptions(self):
        """Skips empty value descriptions from value_list."""
        data = [
            {
                "profileId": "p1",
                "capabilities": [
                    {
                        "id": "cap-on",
                        "description": "enable",
                        "value_list": [
                            {"value": "high", "description": "high"},
                            {"value": "low", "description": ""},
                            {"value": "mid"},
                            {"value": "empty", "description": "   "},
                        ],
                    }
                ],
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spec.jsonl"
            path.write_text(json.dumps(data), encoding="utf-8")

            index = load_spec_index(str(path))

        self.assertEqual(index["p1"][0].value_descriptions, ["high"])


class TestEnrichDescription(unittest.TestCase):
    """Tests for description enrichment."""

    def test_enrich_description_adds_synonyms(self):
        """Adds synonyms when a rule matches."""
        self.assertEqual(
            enrich_description("enable"),
            "enable turn on on start",
        )

    def test_enrich_description_no_match(self):
        """Returns original description when no rule matches."""
        self.assertEqual(enrich_description("brightness"), "brightness")


class TestBuildEnrichedDoc(unittest.TestCase):
    """Tests for enriched doc building."""

    def test_build_with_spec(self):
        """Builds docs from spec index with value list."""
        device = Device(id="d1", name="Lamp", room="Living", type="Light")
        device.profile_id = "p1" # type: ignore
        device.category = "Light" # type: ignore

        spec_index = {
            "p1": [
                CapabilityDoc(
                    id="cap-on",
                    description="enable",
                    value_descriptions=["high", "low"],
                )
            ]
        }

        docs = build_enriched_doc(device, spec_index)

        self.assertEqual(
            docs,
            ["enable turn on on start high low"],
        )

    def test_build_with_empty_value_descriptions(self):
        """Skips empty value descriptions when building docs."""
        device = Device(id="d1", name="Lamp", room="Living", type="Light")
        device.profile_id = "p1" # type: ignore
        device.category = "Light" # type: ignore

        spec_index = {
            "p1": [
                CapabilityDoc(
                    id="cap-on",
                    description="enable",
                    value_descriptions=["", "high", " "],
                )
            ]
        }

        docs = build_enriched_doc(device, spec_index)

        self.assertEqual(
            docs,
            ["enable turn on on start high"],
        )

    def test_build_fallback_without_profile(self):
        """Falls back to device metadata when spec is missing."""
        device = Device(id="d1", name="Lamp", room="Living", type="Light")

        docs = build_enriched_doc(device, {})

        self.assertEqual(docs, ["Lamp Living"])

    def test_build_fallback_without_profile_no_warning(self):
        """Does not warn when profile id is missing."""
        device = Device(id="d1", name="Lamp", room="Living", type="Light")

        logger = logging.getLogger("context_retrieval.doc_enrichment")
        handler = _LogCaptureHandler()
        previous_level = logger.level
        previous_propagate = logger.propagate
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        logger.propagate = False
        try:
            build_enriched_doc(device, {})
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)
            logger.propagate = previous_propagate

        self.assertEqual(handler.records, [])


class _LogCaptureHandler(logging.Handler):
    """Capture log records for assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


if __name__ == "__main__":
    unittest.main()
