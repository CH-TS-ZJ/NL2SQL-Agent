"""
问数接口请求体定义

集中声明 API 层输入输出的数据结构，让路由函数只处理业务流程，
字段校验和 OpenAPI 文档生成交给 Pydantic 与 FastAPI 完成。
"""

from pydantic import BaseModel


class QuerySchema(BaseModel):
    """`/api/query` 请求体，承载用户输入的自然语言问题和所属会话"""

    # 前端请求体中的 query 字段，例如 {"query": "统计华北地区销售额"}
    query: str
    # 会话编号由前端生成并随请求传入；为空时后端兜底新建一个会话
    session_id: str | None = None
