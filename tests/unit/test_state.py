"""会话状态接口测试（mock）。"""

import unittest
from context_retrieval.state import ConversationState


class TestConversationStateInterface(unittest.TestCase):
    """测试 ConversationState 接口。"""

    def test_interface_exists(self):
        """接口存在且可实例化。"""
        state = ConversationState()
        self.assertIsNotNone(state)

    def test_has_resolve_method(self):
        """有 resolve_reference 方法。"""
        state = ConversationState()
        self.assertTrue(callable(getattr(state, "resolve_reference", None)))

    def test_has_update_method(self):
        """有 update_mentioned 方法。"""
        state = ConversationState()
        self.assertTrue(callable(getattr(state, "update_mentioned", None)))


if __name__ == "__main__":
    unittest.main()
