"""Pipeline 组装测试。"""

import logging
import unittest
from unittest import mock
from context_retrieval.pipeline import retrieve
from context_retrieval.models import Device, CommandSpec, RetrievalResult
from context_retrieval.ir_compiler import FakeLLM
from context_retrieval.state import ConversationState
from context_retrieval.vector_search import StubVectorSearcher


class TestRetrieve(unittest.TestCase):
    """测试 retrieve 函数。"""

    def setUp(self):
        """设置测试数据。"""
        self.lamp = Device(
            id="lamp-1",
            name="老伙计",
            room="客厅",
            type="light",
            commands=[
                CommandSpec(id="on", description="打开设备"),
                CommandSpec(id="off", description="关闭设备"),
            ],
        )
        self.bedroom_lamp = Device(
            id="lamp-2",
            name="卧室灯",
            room="卧室",
            type="light",
            commands=[
                CommandSpec(id="on", description="打开设备"),
            ],
        )
        self.devices = [self.lamp, self.bedroom_lamp]

        self.llm = FakeLLM({
            "打开老伙计": {
                "action": "打开",
                "name_hint": "老伙计",
            },
            "关闭卧室的灯": {
                "action": "关闭",
                "scope_include": ["卧室"],
            },
        })
        self.state = ConversationState()

    def test_retrieve_returns_result(self):
        """retrieve 返回 RetrievalResult。"""
        result = retrieve(
            text="打开老伙计",
            devices=self.devices,
            llm=self.llm,
            state=self.state,
        )
        self.assertIsInstance(result, RetrievalResult)

    def test_retrieve_finds_device_by_name(self):
        """根据名称找到设备。"""
        result = retrieve(
            text="打开老伙计",
            devices=self.devices,
            llm=self.llm,
            state=self.state,
        )
        candidate_ids = {c.entity_id for c in result.candidates}
        self.assertIn("lamp-1", candidate_ids)

    def test_retrieve_with_room_scope(self):
        """Scope include should not filter candidates."""
        result = retrieve(
            text="关闭卧室的灯",
            devices=self.devices,
            llm=self.llm,
            state=self.state,
        )
        candidate_ids = {c.entity_id for c in result.candidates}
        self.assertIn("lamp-2", candidate_ids)
        self.assertIn("lamp-1", candidate_ids)

    def test_retrieve_does_not_drop_scope_include_devices(self):
        """Scope include should not filter candidates."""
        scope_text = next(
            key for key, value in self.llm._presets.items()
            if "scope_include" in value
        )
        result = retrieve(
            text=scope_text,
            devices=self.devices,
            llm=self.llm,
            state=self.state,
        )
        candidate_ids = {c.entity_id for c in result.candidates}
        self.assertIn("lamp-1", candidate_ids)
        self.assertIn("lamp-2", candidate_ids)

    def test_retrieve_updates_state(self):
        """检索后更新会话状态。"""
        result = retrieve(
            text="打开老伙计",
            devices=self.devices,
            llm=self.llm,
            state=self.state,
        )
        # 如果有候选，应更新 last-mentioned
        if result.candidates:
            self.assertIsNotNone(self.state.resolve_reference("last-mentioned"))

    def test_retrieve_with_vector_searcher(self):
        """提供向量检索器时也能返回候选。"""
        stub_vector = StubVectorSearcher(
            stub_results={"用向量检索": [("lamp-2", 0.9)]}
        )
        result = retrieve(
            text="用向量检索",
            devices=self.devices,
            llm=self.llm,
            state=self.state,
            vector_searcher=stub_vector,
        )

        ids = {c.entity_id for c in result.candidates}
        self.assertIn("lamp-2", ids)

    def test_retrieve_applies_category_gating(self):
        """Applies category gating before vector indexing."""
        devices = [
            Device(id="lamp-1", name="Lamp", room="Living", type="light"),
            Device(id="ac-1", name="AC", room="Living", type="airConditioner"),
        ]
        llm = FakeLLM({"turn on light": {"action": "turn on", "type_hint": "Light"}})
        recorder = StubVectorSearcher()

        result = retrieve(
            text="turn on light",
            devices=devices,
            llm=llm,
            state=ConversationState(),
            vector_searcher=recorder,
        )

        self.assertEqual(recorder.indexed_ids, ["lamp-1"])
        self.assertTrue(all(c.entity_id == "lamp-1" for c in result.candidates))

    def test_retrieve_skips_category_gating_for_unknown(self):
        """Skips category gating when type_hint is Unknown."""
        devices = [
            Device(id="lamp-1", name="Lamp", room="Living", type="light"),
            Device(id="ac-1", name="AC", room="Living", type="airConditioner"),
        ]
        llm = FakeLLM(
            {"turn on device": {"action": "turn on", "type_hint": "Unknown"}}
        )
        recorder = StubVectorSearcher()

        retrieve(
            text="turn on device",
            devices=devices,
            llm=llm,
            state=ConversationState(),
            vector_searcher=recorder,
        )

        self.assertEqual(recorder.indexed_ids, ["lamp-1", "ac-1"])

    def test_retrieve_fallback_weights_without_type_hint(self):
        """Falls back to keyword-heavy weights without type hints."""
        llm = FakeLLM({"turn on device": {"action": "turn on"}})
        with mock.patch("context_retrieval.pipeline.merge_and_score") as merge_mock:
            merge_mock.return_value = []
            retrieve(
                text="turn on device",
                devices=self.devices,
                llm=llm,
                state=self.state,
            )
            _, kwargs = merge_mock.call_args
            self.assertEqual(kwargs["w_keyword"], 1.2)
            self.assertEqual(kwargs["w_vector"], 0.2)

    def test_pipeline_logs_gating_and_scores(self):
        """Logs gating details for debugging."""
        llm = FakeLLM({"turn on light": {"action": "turn on", "type_hint": "Light"}})
        with self.assertLogs("context_retrieval.pipeline", level=logging.INFO) as ctx:
            retrieve(
                text="turn on light",
                devices=self.devices,
                llm=llm,
                state=self.state,
            )
        joined = "\n".join(ctx.output)
        self.assertIn("mapped_category=Light", joined)
        self.assertIn("gating_before=", joined)
        self.assertIn("gating_after=", joined)


if __name__ == "__main__":
    unittest.main()
