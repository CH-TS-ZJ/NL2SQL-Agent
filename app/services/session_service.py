"""
会话查询服务

负责把持久化的会话与消息还原成前端可消费的结构，用于刷新页面后恢复历史。
只读服务，不参与问数链路，也不负责消息写入。
"""

from app.models.chat_message import ChatMessage
from app.repositories.mysql.session.chat_session_repository import (
    ChatSessionRepository,
)


def _to_message_dict(message: ChatMessage) -> dict:
    """把会话消息 ORM 转成前端友好的字典，时间统一用 epoch 毫秒"""

    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "createdAt": int(message.created_at.timestamp() * 1000),
        "query": message.query,
        "sql": message.sql,
        "result": message.result,
        "error": message.error,
        "detail": message.detail,
    }


class SessionService:
    """会话历史读取服务"""

    def __init__(self, session_repository: ChatSessionRepository):
        self.session_repository = session_repository

    async def get_session(self, session_id: str) -> dict | None:
        """返回单个会话及其消息列表；会话不存在时返回 None"""

        session = await self.session_repository.get_session(session_id)
        if session is None:
            return None

        messages = await self.session_repository.list_messages(session_id)
        return {
            "id": session_id,
            "title": session.title,
            "messages": [_to_message_dict(message) for message in messages],
        }
