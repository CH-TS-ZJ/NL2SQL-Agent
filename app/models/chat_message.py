"""
`chat_message` ORM 模型

定义会话内单条消息的持久化结构。用户消息保存原始问题，
助手消息保存结果摘要、指代消解后的完整问题、生成的 SQL、查询结果和错误信息，
这些字段既用于前端恢复历史，也用于下一轮追问的指代消解。
"""

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base


class ChatMessage(Base):
    """会话消息表对应的 ORM 模型"""

    __tablename__ = "chat_message"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="消息编号")
    session_id: Mapped[str] = mapped_column(
        String(64), index=True, comment="所属会话编号"
    )
    role: Mapped[str] = mapped_column(String(16), comment="角色(user/assistant)")
    content: Mapped[str | None] = mapped_column(Text, comment="消息文本")
    query: Mapped[str | None] = mapped_column(Text, comment="指代消解后的完整问题")
    # sql 是 MySQL 8.0.46 的保留字，需要 quote 让 SQLAlchemy 生成反引号包裹的列名
    sql: Mapped[str | None] = mapped_column("sql", Text, quote=True, comment="生成的SQL")
    result: Mapped[dict | list | None] = mapped_column(JSON, comment="查询结果")
    error: Mapped[str | None] = mapped_column(Text, comment="错误信息")
    detail: Mapped[str | None] = mapped_column(Text, comment="错误详情(校验错误)")
    created_at: Mapped[datetime] = mapped_column(DateTime, comment="创建时间")
