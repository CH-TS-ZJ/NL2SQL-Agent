"""
`user` ORM 模型

定义用户表结构，保存用户名与密码哈希。用户表复用 meta MySQL，
和会话表一起承担用户体系与归属隔离，元数据重建脚本不会清空它。
"""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    """用户表对应的 ORM 模型"""

    __tablename__ = "user"

    # 用户编号由后端生成（uuid4().hex），避免暴露自增主键
    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="用户编号")
    username: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, comment="用户名"
    )
    # 密码只存哈希，格式 pbkdf2_sha256$iterations$salt$hash，不存明文
    password_hash: Mapped[str] = mapped_column(String(255), comment="密码哈希")
    created_at: Mapped[datetime] = mapped_column(DateTime, comment="创建时间")
