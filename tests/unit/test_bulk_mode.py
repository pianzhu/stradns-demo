"""Bulk mode tests for quantifier semantics."""

import os
import unittest
from unittest import mock

from context_retrieval.doc_enrichment import CapabilityDoc
from context_retrieval.ir_compiler import FakeLLM
from context_retrieval.models import Device, ValueRange
from context_retrieval.pipeline import retrieve
from context_retrieval.state import ConversationState
from context_retrieval.vector_search import StubVectorSearcher


class ArbitrationLLM(FakeLLM):
    """FakeLLM + 可控的 parse_with_prompt 输出。"""

    def __init__(self, preset_responses, arbitration_response):
        super().__init__(preset_responses=preset_responses)
        self._arbitration_response = arbitration_response

    def parse_with_prompt(self, text: str, system_prompt: str):  # type: ignore[override]
        return self._arbitration_response


def _device(device_id: str, profile_id: str, category: str = "Light") -> Device:
    dev = Device(id=device_id, name=device_id, room="R", category=category)
    dev.profile_id = profile_id  # type: ignore[attr-defined]
    return dev


class TestBulkMode(unittest.TestCase):
    def test_low_confidence_returns_need_clarification(self):
        devices = [_device("d1", "p1"), _device("d2", "p1")]
        llm = FakeLLM(
            {
                "打开所有灯": {
                    "action": "打开",
                    "quantifier": "all",
                    "type_hint": "Light",
                }
            }
        )
        spec_index = {
            "p1": [
                CapabilityDoc(id="cap-on", description="打开"),
                CapabilityDoc(id="cap-off", description="关闭"),
            ]
        }
        vector = StubVectorSearcher(
            stub_results={
                "打开": [
                    ("d1", "cap-on", 0.90),
                    ("d2", "cap-off", 0.89),
                ]
            },
            spec_index=spec_index,
        )

        result = retrieve(
            text="打开所有灯",
            devices=devices,
            llm=llm,
            state=ConversationState(),
            vector_searcher=vector,
        )

        self.assertEqual(result.hint, "need_clarification")
        self.assertEqual(result.candidates, [])
        self.assertEqual(result.groups, [])
        self.assertGreaterEqual(len(result.options), 2)

    def test_arbitration_choice_index_selects_capability(self):
        devices = [_device("d1", "p1"), _device("d2", "p1")]
        llm = ArbitrationLLM(
            preset_responses={
                "打开所有灯": {
                    "action": "打开",
                    "quantifier": "all",
                    "type_hint": "Light",
                }
            },
            arbitration_response={"choice_index": 0},
        )
        spec_index = {
            "p1": [
                CapabilityDoc(id="cap-on", description="打开"),
                CapabilityDoc(id="cap-off", description="关闭"),
            ]
        }
        vector = StubVectorSearcher(
            stub_results={
                "打开": [
                    ("d1", "cap-on", 0.90),
                    ("d2", "cap-off", 0.89),
                ]
            },
            spec_index=spec_index,
        )

        with mock.patch.dict(os.environ, {"ENABLE_BULK_ARBITRATION_LLM": "1"}):
            result = retrieve(
                text="打开所有灯",
                devices=devices,
                llm=llm,
                state=ConversationState(),
                vector_searcher=vector,
            )

        self.assertEqual(result.selected_capability_id, "cap-on")
        self.assertEqual(len(result.groups), 1)
        self.assertEqual(set(result.groups[0].device_ids), {"d1", "d2"})
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].entity_kind, "group")

        batches = result.batches.get(result.groups[0].id)
        self.assertEqual(batches, [["d1", "d2"]])

    def test_arbitration_invalid_choice_index_returns_need_clarification(self):
        devices = [_device("d1", "p1"), _device("d2", "p1")]
        llm = ArbitrationLLM(
            preset_responses={
                "打开所有灯": {
                    "action": "打开",
                    "quantifier": "all",
                    "type_hint": "Light",
                }
            },
            arbitration_response={"choice_index": 99},
        )
        spec_index = {
            "p1": [
                CapabilityDoc(id="cap-on", description="打开"),
                CapabilityDoc(id="cap-off", description="关闭"),
            ]
        }
        vector = StubVectorSearcher(
            stub_results={
                "打开": [
                    ("d1", "cap-on", 0.90),
                    ("d2", "cap-off", 0.89),
                ]
            },
            spec_index=spec_index,
        )

        with mock.patch.dict(os.environ, {"ENABLE_BULK_ARBITRATION_LLM": "1"}):
            result = retrieve(
                text="打开所有灯",
                devices=devices,
                llm=llm,
                state=ConversationState(),
                vector_searcher=vector,
            )

        self.assertEqual(result.hint, "need_clarification")
        self.assertEqual(result.candidates, [])
        self.assertEqual(result.groups, [])

    def test_arbitration_question_returns_need_clarification_with_question(self):
        devices = [_device("d1", "p1"), _device("d2", "p1")]
        llm = ArbitrationLLM(
            preset_responses={
                "打开所有灯": {
                    "action": "打开",
                    "quantifier": "all",
                    "type_hint": "Light",
                }
            },
            arbitration_response={"question": "你要打开还是关闭？"},
        )
        spec_index = {
            "p1": [
                CapabilityDoc(id="cap-on", description="打开"),
                CapabilityDoc(id="cap-off", description="关闭"),
            ]
        }
        vector = StubVectorSearcher(
            stub_results={
                "打开": [
                    ("d1", "cap-on", 0.90),
                    ("d2", "cap-off", 0.89),
                ]
            },
            spec_index=spec_index,
        )

        with mock.patch.dict(os.environ, {"ENABLE_BULK_ARBITRATION_LLM": "1"}):
            result = retrieve(
                text="打开所有灯",
                devices=devices,
                llm=llm,
                state=ConversationState(),
                vector_searcher=vector,
            )

        self.assertEqual(result.hint, "need_clarification")
        self.assertEqual(result.question, "你要打开还是关闭？")
        self.assertEqual(result.candidates, [])

    def test_group_compatibility_splits_by_signature(self):
        devices = [_device("d1", "p1"), _device("d2", "p2")]
        llm = FakeLLM(
            {
                "把所有灯调到50": {
                    "action": "调到50",
                    "quantifier": "all",
                    "type_hint": "Light",
                }
            }
        )
        spec_index = {
            "p1": [
                CapabilityDoc(
                    id="cap-level",
                    description="调亮度",
                    type="number",
                    value_range=ValueRange(minimum=0, maximum=100, unit="%"),
                )
            ],
            "p2": [
                CapabilityDoc(
                    id="cap-level",
                    description="调亮度",
                    type="number",
                    value_range=ValueRange(minimum=0, maximum=1, unit="%"),
                )
            ],
        }
        vector = StubVectorSearcher(
            stub_results={
                "调到50": [
                    ("d1", "cap-level", 0.95),
                    ("d2", "cap-level", 0.94),
                    ("d1", "cap-off", 0.10),
                ]
            },
            spec_index=spec_index,
        )

        result = retrieve(
            text="把所有灯调到50",
            devices=devices,
            llm=llm,
            state=ConversationState(),
            vector_searcher=vector,
        )

        self.assertEqual(result.selected_capability_id, "cap-level")
        self.assertEqual(len(result.groups), 2)
        seen = {tuple(sorted(group.device_ids)) for group in result.groups}
        self.assertEqual(seen, {("d1",), ("d2",)})

    def test_batch_split(self):
        devices = [_device(f"d{i}", "p1") for i in range(45)]
        llm = FakeLLM(
            {
                "打开所有灯": {
                    "action": "打开",
                    "quantifier": "all",
                    "type_hint": "Light",
                }
            }
        )
        spec_index = {"p1": [CapabilityDoc(id="cap-on", description="打开")]}
        vector = StubVectorSearcher(
            stub_results={
                "打开": [(devices[0].id, "cap-on", 0.99)]
            },
            spec_index=spec_index,
        )

        result = retrieve(
            text="打开所有灯",
            devices=devices,
            llm=llm,
            state=ConversationState(),
            vector_searcher=vector,
        )

        self.assertEqual(len(result.groups), 1)
        group_id = result.groups[0].id
        batches = result.batches[group_id]
        self.assertEqual([len(batch) for batch in batches], [20, 20, 5])

    def test_too_many_targets_returns_hint(self):
        devices = [_device(f"d{i}", "p1") for i in range(201)]
        llm = FakeLLM(
            {
                "打开所有灯": {
                    "action": "打开",
                    "quantifier": "all",
                    "type_hint": "Light",
                }
            }
        )
        spec_index = {"p1": [CapabilityDoc(id="cap-on", description="打开")]}
        vector = StubVectorSearcher(
            stub_results={
                "打开": [(devices[0].id, "cap-on", 0.99)]
            },
            spec_index=spec_index,
        )

        result = retrieve(
            text="打开所有灯",
            devices=devices,
            llm=llm,
            state=ConversationState(),
            vector_searcher=vector,
        )

        self.assertEqual(result.hint, "too_many_targets")
        self.assertEqual(result.candidates, [])
        self.assertEqual(result.groups, [])


if __name__ == "__main__":
    unittest.main()

