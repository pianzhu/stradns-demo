"""会话状态接口。

管理对话上下文，支持指代消解。具体实现待整合到完整系统。
"""

from context_retrieval.models import Device


class ConversationState:
    """会话状态（接口定义）。"""

    def __init__(self):
        self._last_mentioned: Device | None = None

    def resolve_reference(self, ref: str) -> Device | None:
        """解析指代引用。

        Args:
            ref: 引用类型，如 "last-mentioned"

        Returns:
            解析到的设备，或 None
        """
        if ref == "last-mentioned":
            return self._last_mentioned
        return None

    def update_mentioned(self, device: Device) -> None:
        """更新最近提及的设备。

        Args:
            device: 被提及的设备
        """
        self._last_mentioned = device
