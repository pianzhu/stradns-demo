"""Tests for DashScopeEmbeddingModel enriched docs."""

import unittest
from http import HTTPStatus

import numpy as np

from context_retrieval.doc_enrichment import CapabilityDoc
from context_retrieval.models import Device
from context_retrieval.vector_search import DashScopeEmbeddingModel


class RecordingEmbeddingClient:
    """Embedding client that records input texts."""

    def __init__(self, dim: int = 2, status: HTTPStatus = HTTPStatus.OK):
        self.dim = dim
        self.status = status
        self.calls: list[dict] = []

    def call(self, model: str, input: list[str], **kwargs):
        self.calls.append({"model": model, "input": input, "kwargs": kwargs})
        embeddings = [{"embedding": [float(i) for i in range(self.dim)]} for _ in input]
        return type(
            "Resp",
            (),
            {
                "status_code": self.status,
                "output": {"embeddings": embeddings},
                "message": "",
            },
        )


class TestDashScopeEmbeddingModelEnrichedDocs(unittest.TestCase):
    """Tests for enriched doc encoding."""

    def test_encode_enriched_docs_with_spec(self):
        """Builds enriched docs and returns capability ids."""
        client = RecordingEmbeddingClient()
        model = DashScopeEmbeddingModel(embedding_client=client)

        device = Device(id="d1", name="Lamp", room="Living", type="Light")
        device.profile_id = "p1"
        device.category = "Light"

        spec_index = {
            "p1": [
                CapabilityDoc(id="cap-on", description="enable", value_descriptions=["high"]),
            ]
        }

        entries, embeddings = model.encode_enriched_docs([device], spec_index)

        self.assertEqual(entries, [("d1", "cap-on")])
        self.assertIsInstance(embeddings, np.ndarray)
        self.assertEqual(embeddings.shape, (1, 2))
        self.assertEqual(
            client.calls[0]["input"],
            ["Light cap-on enable turn on on start high"],
        )

    def test_encode_enriched_docs_fallback(self):
        """Falls back to device metadata when spec is missing."""
        client = RecordingEmbeddingClient()
        model = DashScopeEmbeddingModel(embedding_client=client)

        device = Device(id="d1", name="Lamp", room="Living", type="Light")

        entries, embeddings = model.encode_enriched_docs([device], {})

        self.assertEqual(entries, [("d1", None)])
        self.assertEqual(embeddings.shape, (1, 2))
        self.assertEqual(client.calls[0]["input"], ["Lamp Living Light"])


if __name__ == "__main__":
    unittest.main()
