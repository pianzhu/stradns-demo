"""Pipeline 组装测试。"""

import logging
import unittest
from unittest import mock
from context_retrieval.pipeline import retrieve, retrieve_single
from context_retrieval.models import Device, CommandSpec, RetrievalResult
from context_retrieval.doc_enrichment import CapabilityDoc
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
            category="light",
            commands=[
                CommandSpec(id="on", description="打开设备"),
                CommandSpec(id="off", description="关闭设备"),
            ],
        )
        self.bedroom_lamp = Device(
            id="lamp-2",
            name="卧室灯",
            room="卧室",
            category="light",
            commands=[
                CommandSpec(id="on", description="打开设备"),
            ],
        )
        self.devices = [self.lamp, self.bedroom_lamp]

        self.llm = FakeLLM({
            "打开老伙计": [
                {"a": "打开", "s": "*", "n": "老伙计", "t": "Light", "q": "one"}
            ],
            "关闭卧室的灯": [
                {"a": "关闭", "s": "卧室", "n": "灯", "t": "Light", "q": "all"}
            ],
        })
        self.state = ConversationState()

    def test_retrieve_returns_multi_result(self):
        """retrieve 返回 MultiRetrievalResult。"""
        result = retrieve(
            text="打开老伙计",
            devices=self.devices,
            llm=self.llm,
            state=self.state,
        )
        self.assertEqual(len(result.commands), 1)
        self.assertIsInstance(result.commands[0].result, RetrievalResult)

    def test_retrieve_multi_command_order(self):
        """多命令保持顺序输出。"""
        llm = FakeLLM(
            {
                "打开老伙计并关闭卧室灯": [
                    {"a": "打开", "s": "客厅", "n": "老伙计", "t": "Light", "q": "one"},
                    {"a": "关闭", "s": "卧室", "n": "灯", "t": "Light", "q": "all"},
                ]
            }
        )
        result = retrieve(
            text="打开老伙计并关闭卧室灯",
            devices=self.devices,
            llm=llm,
            state=ConversationState(),
        )
        self.assertEqual([cmd.command.action for cmd in result.commands], ["打开", "关闭"])

    def test_retrieve_finds_device_by_name(self):
        """根据名称找到设备。"""
        result = retrieve_single(
            text="打开老伙计",
            devices=self.devices,
            llm=self.llm,
            state=self.state,
        )
        candidate_ids = {c.entity_id for c in result.candidates}
        self.assertIn("lamp-1", candidate_ids)

    def test_retrieve_with_room_scope(self):
        """Scope include should not filter candidates."""
        result = retrieve_single(
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
        scope_text = "关闭卧室的灯"
        result = retrieve_single(
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
        result = retrieve_single(
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
        llm = FakeLLM(
            {
                "用向量检索": [
                    {"a": "打开", "s": "*", "n": "灯", "t": "Light", "q": "all"}
                ]
            }
        )
        result = retrieve_single(
            text="用向量检索",
            devices=self.devices,
            llm=llm,
            state=self.state,
            vector_searcher=stub_vector,
        )

        ids = {c.entity_id for c in result.candidates}
        self.assertIn("lamp-2", ids)

    def test_vector_search_falls_back_to_raw_when_action_has_latin(self):
        """当 action 包含英文字母时，向量检索降级为使用 raw query。"""
        devices = [
            Device(id="lamp-1", name="Lamp", room="Living", category="light"),
            Device(id="lamp-2", name="Lamp2", room="Living", category="light"),
        ]
        llm = FakeLLM(
            {
                "打开客厅的灯": [
                    {"a": "turn on", "s": "客厅", "n": "灯", "t": "Light", "q": "all"}
                ]
            }
        )
        stub_vector = StubVectorSearcher(
            stub_results={
                # 若错误使用 action，会命中 lamp-1
                "turn on": [("lamp-1", 0.9)],
                # 正确降级使用 raw，应命中 lamp-2
                "打开客厅的灯": [("lamp-2", 0.9)],
            }
        )

        result = retrieve_single(
            text="打开客厅的灯",
            devices=devices,
            llm=llm,
            state=ConversationState(),
            vector_searcher=stub_vector,
        )

        ids = {c.entity_id for c in result.candidates}
        self.assertIn("lamp-2", ids)
        self.assertNotIn("lamp-1", ids)

    def test_retrieve_applies_category_gating(self):
        """Applies category gating before vector search."""
        devices = [
            Device(id="lamp-1", name="Lamp", room="Living", category="light"),
            Device(id="ac-1", name="AC", room="Living", category="airConditioner"),
        ]
        llm = FakeLLM(
            {"turn on light": [{"a": "turn on", "s": "*", "n": "灯", "t": "Light", "q": "all"}]}
        )
        recorder = StubVectorSearcher()

        result = retrieve_single(
            text="turn on light",
            devices=devices,
            llm=llm,
            state=ConversationState(),
            vector_searcher=recorder,
        )

        self.assertEqual(recorder.last_device_ids, {"lamp-1"})
        self.assertTrue(all(c.entity_id == "lamp-1" for c in result.candidates))

    def test_retrieve_skips_category_gating_for_unknown(self):
        """Skips category gating when type_hint is Unknown."""
        devices = [
            Device(id="lamp-1", name="Lamp", room="Living", category="light"),
            Device(id="ac-1", name="AC", room="Living", category="airConditioner"),
        ]
        llm = FakeLLM(
            {"turn on device": [{"a": "turn on", "s": "*", "n": "设备", "t": "Unknown", "q": "all"}]}
        )
        recorder = StubVectorSearcher()

        retrieve_single(
            text="turn on device",
            devices=devices,
            llm=llm,
            state=ConversationState(),
            vector_searcher=recorder,
        )

        self.assertEqual(recorder.last_device_ids, {"lamp-1", "ac-1"})

    def test_retrieve_fallback_weights_without_type_hint(self):
        """Falls back to keyword-heavy weights without type hints."""
        llm = FakeLLM(
            {"turn on device": [{"a": "turn on", "s": "*", "n": "设备", "t": "Unknown", "q": "all"}]}
        )
        with mock.patch("context_retrieval.pipeline.merge_and_score") as merge_mock:
            merge_mock.return_value = []
            retrieve_single(
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
        llm = FakeLLM(
            {"turn on light": [{"a": "turn on", "s": "*", "n": "灯", "t": "Light", "q": "all"}]}
        )
        with self.assertLogs("context_retrieval.pipeline", level=logging.INFO) as ctx:
            retrieve_single(
                text="turn on light",
                devices=self.devices,
                llm=llm,
                state=self.state,
            )
        joined = "\n".join(ctx.output)
        self.assertIn("mapped_category=Light", joined)
        self.assertIn("gating_before=", joined)
        self.assertIn("gating_after=", joined)

    def test_retrieve_infers_name_hint_and_capability(self):
        """Infers name_hint from raw query and assigns capability for keyword-only candidates."""
        charger = Device(id="charger-1", name="Charger", room="Bedroom", category="Charger")
        setattr(charger, "profile_id", "profile-charger")

        light = Device(id="lamp-1", name="Lamp", room="Bedroom", category="Light")
        setattr(light, "profile_id", "profile-light")

        llm = FakeLLM(
            {
                "turn on Charger": [
                    {
                        "a": "turn on",
                        "s": "*",
                        "n": "Charger",
                        "t": "Unknown",
                        "q": "one",
                    }
                ]
            }
        )

        spec_index = {
            "profile-charger": [
                CapabilityDoc(id="main-switch-on", description="turn on"),
                CapabilityDoc(id="main-switch-off", description="turn off"),
            ]
        }
        vector_searcher = StubVectorSearcher(
            stub_results={},
            spec_index=spec_index,
        )

        result = retrieve_single(
            text="turn on Charger",
            devices=[charger, light],
            llm=llm,
            state=ConversationState(),
            vector_searcher=vector_searcher,
        )

        self.assertTrue(result.candidates)
        self.assertEqual(result.candidates[0].entity_id, "charger-1")
        self.assertEqual(result.candidates[0].capability_id, "main-switch-on")

    def test_retrieve_forces_capability_guess_for_numeric_queries(self):
        """For numeric commands, prefer spec-based capability guessing over vector-picked capability ids."""
        fan = Device(id="fan-1", name="风扇", room="客厅", category="Fan")
        fan.profile_id = "profile-fan"  # type: ignore[attr-defined]

        query = "把客厅风扇风速调到40%"
        llm = FakeLLM(
            {
                query: [
                    {"a": "设置风速=40%", "s": "客厅", "n": "风扇", "t": "Unknown", "q": "one"}
                ]
            }
        )

        spec_index = {
            "profile-fan": [
                CapabilityDoc(id="cap-speed", description="风扇速度"),
                CapabilityDoc(id="cap-osc", description="风扇摆动模式"),
            ]
        }
        vector_searcher = StubVectorSearcher(
            stub_results={
                query: [
                    ("fan-1", "cap-osc", 0.99),
                ]
            },
            spec_index=spec_index,
        )

        result = retrieve_single(
            text=query,
            devices=[fan],
            llm=llm,
            state=ConversationState(),
            vector_searcher=vector_searcher,
        )

        self.assertTrue(result.candidates)
        self.assertEqual(result.candidates[0].entity_id, "fan-1")
        self.assertEqual(result.candidates[0].capability_id, "cap-speed")


if __name__ == "__main__":
    unittest.main()
