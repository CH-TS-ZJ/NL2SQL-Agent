"""
会话持久化仓储

负责会话和会话消息的增删查，复用 meta MySQL 的连接与请求级 Session。
建表 DDL 集中在这里，应用启动时通过 ensure_tables 幂等建表，
保证既有的 mysql 数据卷不需要重建也能获得会话表。
"""

import uuid
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession

# 会话表与消息表 DDL，和 docker/mysql/meta.sql 保持一致
CHAT_SESSION_DDL = """
CREATE TABLE IF NOT EXISTS chat_session (
    id          VARCHAR(64) PRIMARY KEY COMMENT '会话编号',
    user_id     VARCHAR(64) COMMENT '所属用户编号',
    title       VARCHAR(255) COMMENT '会话标题(取首个问题)',
    created_at  DATETIME COMMENT '创建时间',
    updated_at  DATETIME COMMENT '最近更新时间',
    KEY idx_user_id (user_id)
)
"""

CHAT_MESSAGE_DDL = """
CREATE TABLE IF NOT EXISTS chat_message (
    id          VARCHAR(64) PRIMARY KEY COMMENT '消息编号',
    session_id  VARCHAR(64) NOT NULL COMMENT '所属会话编号',
    role        VARCHAR(16) NOT NULL COMMENT '角色 user/assistant',
    content     TEXT COMMENT '消息文本',
    query       TEXT COMMENT '指代消解后的完整问题',
    `sql`       TEXT COMMENT '生成的SQL',
    result      JSON COMMENT '查询结果',
    error       TEXT COMMENT '错误信息',
    detail      TEXT COMMENT '错误详情(校验错误)',
    created_at  DATETIME COMMENT '创建时间',
    KEY idx_session_id (session_id)
)
"""


class ChatSessionRepository:
    """负责会话与消息的持久化，复用 meta MySQL 的连接"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def ensure_tables(self):
        """幂等创建会话与消息表，并补齐既有数据卷的用户归属列"""
        await self.session.execute(text(CHAT_SESSION_DDL))
        await self.session.execute(text(CHAT_MESSAGE_DDL))
        await self._ensure_user_id_column()

    async def _ensure_user_id_column(self):
        """对既有数据卷幂等补齐 chat_session.user_id 列与索引

        MySQL 8 不支持 ADD COLUMN IF NOT EXISTS，因此先查 information_schema 判断
        列是否已存在，缺失时才执行 ALTER，保证旧数据卷升级后也能获得用户归属能力。
        """
        result = await self.session.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'chat_session' "
                "AND COLUMN_NAME = 'user_id'"
            )
        )
        if result.scalar() == 0:
            await self.session.execute(
                text(
                    "ALTER TABLE chat_session "
                    "ADD COLUMN user_id VARCHAR(64) COMMENT '所属用户编号', "
                    "ADD KEY idx_user_id (user_id)"
                )
            )

    async def ensure_session(
        self, session_id: str, title: str | None = None, user_id: str | None = None
    ):
        """会话不存在则创建；标题只在首次创建时写入，避免被后续追问覆盖。

        user_id 用于会话归属：新建会话时写入归属用户；已存在会话若归属他人则拒绝。
        """
        session = await self.session.get(ChatSession, session_id)
        now = datetime.now()
        if session:
            if session.user_id and session.user_id != user_id:
                raise PermissionError("会话不属于当前用户")
            if not session.title and title:
                session.title = title
            session.updated_at = now
        else:
            self.session.add(
                ChatSession(
                    id=session_id,
                    user_id=user_id,
                    title=title,
                    created_at=now,
                    updated_at=now,
                )
            )

    async def get_session(self, session_id: str) -> ChatSession | None:
        """按编号查询会话，供历史读取服务判断会话是否存在并取标题"""

        return await self.session.get(ChatSession, session_id)

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str | None = None,
        query: str | None = None,
        sql: str | None = None,
        result: dict | list | None = None,
        error: str | None = None,
        detail: str | None = None,
    ) -> ChatMessage:
        """新增一条会话消息，并顺带刷新所属会话的最近更新时间"""
        message = ChatMessage(
            id=uuid.uuid4().hex,
            session_id=session_id,
            role=role,
            content=content,
            query=query,
            sql=sql,
            result=result,
            error=error,
            detail=detail,
            created_at=datetime.now(),
        )
        self.session.add(message)

        session = await self.session.get(ChatSession, session_id)
        if session:
            session.updated_at = datetime.now()

        return message

    async def list_messages(self, session_id: str) -> list[ChatMessage]:
        """按创建时间升序返回会话内的全部消息"""
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
        return list(result.scalars().all())

    async def commit(self):
        """提交会话与消息的变更"""
        await self.session.commit()
