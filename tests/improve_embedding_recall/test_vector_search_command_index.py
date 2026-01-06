"""Tests for command-level vector indexing."""

import unittest

import numpy as np

from context_retrieval.doc_enrichment import CapabilityDoc
from context_retrieval.models import Device
from context_retrieval.vector_search import InMemoryVectorSearcher


class RecordingEmbeddingModel:
    """Embedding model that records input texts."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, texts: list[str]) -> np.ndarray:
        self.calls.append(list(texts))
        vectors = [self._to_vector(text) for text in texts]
        return np.asarray(vectors, dtype=np.float32)

    def _to_vector(self, text: str) -> list[float]:
        text_lower = text.lower()
        return [
            1.0 if "enable" in text_lower else 0.0,
            1.0 if "adjust" in text_lower else 0.0,
            1.0 if "high" in text_lower else 0.0,
        ]


class TestCommandLevelIndexing(unittest.TestCase):
    """Tests for command-level indexing with spec index."""

    def test_index_builds_command_docs(self):
        """Indexes one document per capability when spec exists."""
        model = RecordingEmbeddingModel()
        spec_index = {
            "p1": [
                CapabilityDoc(
                    id="cap-on",
                    description="enable",
                    value_descriptions=["high"],
                ),
                CapabilityDoc(
                    id="cap-level",
                    description="adjust",
                    value_descriptions=[],
                ),
            ]
        }

        device = Device(id="d1", name="Lamp", room="Living", type="Light")
        device.profile_id = "p1"
        device.category = "Light"

        searcher = InMemoryVectorSearcher(model, spec_index=spec_index)
        searcher.index([device])

        self.assertEqual(
            model.calls[0],
            [
                "Light cap-on enable turn on on start high",
                "Light cap-level adjust",
            ],
        )

    def test_search_returns_capability_ids(self):
        """Returns capability ids for command-level results."""
        model = RecordingEmbeddingModel()
        spec_index = {
            "p1": [
                CapabilityDoc(id="cap-on", description="enable", value_descriptions=[]),
                CapabilityDoc(id="cap-level", description="adjust", value_descriptions=[]),
            ]
        }

        device = Device(id="d1", name="Lamp", room="Living", type="Light")
        device.profile_id = "p1"
        device.category = "Light"

        searcher = InMemoryVectorSearcher(model, spec_index=spec_index)
        searcher.index([device])

        candidates = searcher.search("adjust", top_k=2)
        cap_ids = {c.capability_id for c in candidates}

        self.assertEqual(cap_ids, {"cap-on", "cap-level"})
        self.assertEqual(candidates[0].capability_id, "cap-level")
        self.assertTrue(all(c.entity_id == "d1" for c in candidates))


class TestFallbackIndexing(unittest.TestCase):
    """Tests for fallback indexing when spec is missing."""

    def test_fallback_uses_device_metadata(self):
        """Uses device metadata when spec index is missing."""
        model = RecordingEmbeddingModel()
        device = Device(id="d1", name="Lamp", room="Living", type="Light")

        searcher = InMemoryVectorSearcher(model, spec_index={})
        searcher.index([device])

        self.assertEqual(model.calls[0], ["Lamp Living Light"])


if __name__ == "__main__":
    unittest.main()
