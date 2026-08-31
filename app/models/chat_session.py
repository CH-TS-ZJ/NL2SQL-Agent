"""
`chat_session` ORM 模型

定义会话持久化表结构，保存会话编号、标题和创建/更新时间。
会话表复用 meta MySQL，但和元数据表职责隔离，元数据重建脚本不会清空它。
"""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ChatSession(Base):
    """会话表对应的 ORM 模型"""

    __tablename__ = "chat_session"

    # 会话编号由前端生成并随每次请求传入，后端负责按需创建
    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="会话编号")
    # 归属用户编号，用于后端会话隔离；旧数据允许为空（未归属，读取时按不存在处理）
    user_id: Mapped[str | None] = mapped_column(
        String(64), index=True, comment="所属用户编号"
    )
    title: Mapped[str | None] = mapped_column(String(255), comment="会话标题(取首个问题)")
    created_at: Mapped[datetime] = mapped_column(DateTime, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, comment="最近更新时间")
