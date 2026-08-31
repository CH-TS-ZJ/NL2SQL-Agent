"""
认证接口请求与响应体定义

承载用户注册 / 登录的输入，以及签发 token 后的响应结构。
字段校验交给 Pydantic，密码最小长度在注册入口约束。
"""

from pydantic import BaseModel, Field


class RegisterSchema(BaseModel):
    """`/api/auth/register` 请求体"""

    username: str = Field(min_length=3, max_length=64, description="用户名")
    password: str = Field(min_length=6, max_length=128, description="密码")


class LoginSchema(BaseModel):
    """`/api/auth/login` 请求体"""

    username: str = Field(min_length=1, max_length=64, description="用户名")
    password: str = Field(min_length=1, max_length=128, description="密码")


class TokenResponse(BaseModel):
    """登录 / 注册成功后的响应体"""

    access_token: str = Field(description="JWT 访问令牌")
    token_type: str = "bearer"
    user_id: str = Field(description="用户编号")
    username: str = Field(description="用户名")
