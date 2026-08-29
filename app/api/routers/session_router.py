"""
会话查询接口路由

负责定义 `/api/sessions/{session_id}` 接口，把持久化的会话历史返回给前端，
用于页面刷新后恢复之前的对话。路由只做参数解析和依赖声明，不直接访问仓储。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_session_service
from app.services.session_service import SessionService

# 会话接口和问数接口分开维护，避免查询历史逻辑挤进 query_router
session_router = APIRouter()


@session_router.get("/api/sessions/{session_id}")
async def get_session_handler(
    session_id: str,
    session_service: Annotated[SessionService, Depends(get_session_service)],
):
    """返回指定会话的历史消息，供前端恢复对话"""

    session = await session_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session
