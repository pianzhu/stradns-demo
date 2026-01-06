"""Pipeline 组装测试。"""

import unittest
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


if __name__ == "__main__":
    unittest.main()
