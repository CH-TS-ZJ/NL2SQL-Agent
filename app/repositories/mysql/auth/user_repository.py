"""
用户持久化仓储

负责用户表的建表、按用户名查找和新增用户，复用 meta MySQL 的连接与请求级 Session。
建表 DDL 与 docker/mysql/meta.sql 保持一致，应用启动时通过 ensure_tables 幂等建表。
"""

import uuid
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

# 用户表 DDL，和 docker/mysql/meta.sql 保持一致
USER_DDL = """
CREATE TABLE IF NOT EXISTS user (
    id            VARCHAR(64) PRIMARY KEY COMMENT '用户编号',
    username      VARCHAR(64) NOT NULL COMMENT '用户名',
    password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希',
    created_at    DATETIME COMMENT '创建时间',
    UNIQUE KEY uk_username (username),
    KEY idx_username (username)
)
"""


class UserRepository:
    """负责用户的持久化，复用 meta MySQL 的连接"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def ensure_tables(self):
        """幂等创建用户表，供应用启动时调用"""
        await self.session.execute(text(USER_DDL))

    async def get_by_username(self, username: str) -> User | None:
        """按用户名查询用户，供登录校验和注册查重使用"""
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        return result.scalars().first()

    async def create(self, username: str, password_hash: str) -> User:
        """新增一个用户，返回持久化后的用户对象"""
        user = User(
            id=uuid.uuid4().hex,
            username=username,
            password_hash=password_hash,
            created_at=datetime.now(),
        )
        self.session.add(user)
        return user

    async def commit(self):
        """提交用户变更"""
        await self.session.commit()
