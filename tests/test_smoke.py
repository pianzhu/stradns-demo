"""冒烟测试：验证测试脚手架正常工作。"""

import unittest


class SmokeTest(unittest.TestCase):
    """基本的冒烟测试。"""

    def test_true(self):
        """验证测试框架可以运行。"""
        self.assertTrue(True)

    def test_import(self):
        """验证 context_retrieval 包可以导入。"""
        import context_retrieval
        self.assertIsNotNone(context_retrieval)


if __name__ == "__main__":
    unittest.main()
