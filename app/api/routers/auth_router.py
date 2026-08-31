"""
认证接口路由

负责定义用户注册与登录接口。注册时做用户名查重，登录时校验密码，
成功都返回一个 Bearer JWT，前端保存后随请求带上以标识身份。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_user_repository
from app.api.schemas.auth_schema import LoginSchema, RegisterSchema, TokenResponse
from app.core.security import create_access_token, hash_password, verify_password
from app.repositories.mysql.auth.user_repository import UserRepository

auth_router = APIRouter()


@auth_router.post("/api/auth/register", response_model=TokenResponse)
async def register_handler(
    payload: RegisterSchema,
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
):
    """注册新用户，用户名重复时返回 409"""

    existing = await user_repository.get_by_username(payload.username)
    if existing is not None:
        raise HTTPException(status_code=409, detail="用户名已存在")

    user = await user_repository.create(
        username=payload.username,
        password_hash=hash_password(payload.password),
    )
    await user_repository.commit()

    return TokenResponse(
        access_token=create_access_token(user.id),
        user_id=user.id,
        username=user.username,
    )


@auth_router.post("/api/auth/login", response_model=TokenResponse)
async def login_handler(
    payload: LoginSchema,
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
):
    """校验用户名密码，通过后签发 JWT，失败返回 401"""

    user = await user_repository.get_by_username(payload.username)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    return TokenResponse(
        access_token=create_access_token(user.id),
        user_id=user.id,
        username=user.username,
    )
