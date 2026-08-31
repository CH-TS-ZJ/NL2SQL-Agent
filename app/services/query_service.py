"""
问数查询服务

负责把 API 层传入的自然语言问题转换成一次 LangGraph 工作流执行：
创建初始 State、组装 Runtime Context、消费 graph.astream 的流式输出，
并统一包装成 SSE 文本返回给路由层。

同时承担会话持久化编排：进入图前落库用户消息并加载历史对话，
图执行结束后从最终状态落库助手消息，为下一轮指代消解提供上下文。
"""

import json
import uuid

from langchain_huggingface import HuggingFaceEndpointEmbeddings

from app.agent.context import DataAgentContext
from app.agent.graph import graph
from app.agent.state import ChatTurn, DataAgentState
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.mysql.session.chat_session_repository import (
    ChatSessionRepository,
)
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository


def _build_history(messages) -> list[ChatTurn]:
    """把持久化的历史消息转成指代消解节点可消费的对话轮次"""

    return [
        {
            "role": message.role,
            "content": message.content or "",
            "query": message.query,
            "sql": message.sql,
        }
        for message in messages
    ]


class QueryService:
    """封装一次问数查询所需的业务编排逻辑"""

    def __init__(
        self,
        meta_mysql_repository: MetaMySQLRepository,
        embedding_client: HuggingFaceEndpointEmbeddings,
        dw_mysql_repository: DWMySQLRepository,
        column_qdrant_repository: ColumnQdrantRepository,
        metric_qdrant_repository: MetricQdrantRepository,
        value_es_repository: ValueESRepository,
        session_repository: ChatSessionRepository,
    ):
        # MySQL 仓储分别负责元数据补全和真实数仓环境信息读取
        self.meta_mysql_repository = meta_mysql_repository
        self.dw_mysql_repository = dw_mysql_repository

        # 召回链路依赖的向量检索、Embedding 和全文检索能力由依赖层注入
        self.embedding_client = embedding_client
        self.column_qdrant_repository = column_qdrant_repository
        self.metric_qdrant_repository = metric_qdrant_repository
        self.value_es_repository = value_es_repository

        # 会话持久化仓储，负责在流式链路前后落库用户和助手消息
        self.session_repository = session_repository

    async def query(
        self, query: str, session_id: str | None = None, user_id: str | None = None
    ):
        """执行一次问数工作流，并逐段产出 SSE 消息"""

        # 会话由前端生成并随请求传入；缺失时后端兜底生成一个
        session_id = session_id or uuid.uuid4().hex

        # 先校验会话归属，再加载历史对话，保证用户不能读写他人会话
        try:
            await self.session_repository.ensure_session(
                session_id, title=query[:50], user_id=user_id
            )
        except PermissionError as e:
            # 流式响应已开始后不能再改 HTTP 状态码，因此把越权包装成 SSE 错误消息
            error = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"
            return

        prior_messages = await self.session_repository.list_messages(session_id)
        history = _build_history(prior_messages)

        await self.session_repository.add_message(
            session_id, role="user", content=query, query=query
        )
        await self.session_repository.commit()

        # State 只放会被图节点读写和合并的业务数据，外部工具对象不塞进 State
        state = DataAgentState(query=query, original_query=query, history=history)
        # Context 保存本次图执行需要复用的外部依赖，节点通过 runtime.context 读取
        context = DataAgentContext(
            column_qdrant_repository=self.column_qdrant_repository,
            embedding_client=self.embedding_client,
            metric_qdrant_repository=self.metric_qdrant_repository,
            value_es_repository=self.value_es_repository,
            meta_mysql_repository=self.meta_mysql_repository,
            dw_mysql_repository=self.dw_mysql_repository,
        )

        # 首条 SSE 告诉前端当前会话编号，供前端同步到本地状态
        yield f"data: {json.dumps({'type': 'session', 'sessionId': session_id}, ensure_ascii=False)}\n\n"

        final_state: dict = {}
        try:
            # stream_mode 同时用 custom（进度消息）和 values（最终状态）
            # 多模式时 astream 逐项产出 (mode, data) 元组
            async for chunk in graph.astream(
                input=state, context=context, stream_mode=["custom", "values"]
            ):
                mode, data = chunk
                if mode == "custom":
                    # SSE 要求每条消息以 data: 开头，并以两个换行符结束
                    yield f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
                else:
                    # values 模式返回整份状态，只记录最终值用于落库，不下发
                    final_state = data
        except Exception as e:
            # 流式接口已经开始返回后不能再改 HTTP 状态码，因此把异常也包装成一条 SSE 消息
            error = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(error, ensure_ascii=False, default=str)}\n\n"
            await self._persist_assistant_message(session_id, error_message=str(e))
            return

        await self._persist_assistant_message(session_id, final_state=final_state)

    async def _persist_assistant_message(
        self,
        session_id: str,
        final_state: dict | None = None,
        error_message: str | None = None,
    ):
        """图执行结束后，把助手消息（结果或错误）落库，供恢复和下一轮追问使用"""

        final_state = final_state or {}
        sql = final_state.get("sql")

        if error_message is not None:
            content = "这次查询没有成功。"
            result = None
            error = error_message
            detail = None
        else:
            result = final_state.get("result")
            fail_message = final_state.get("fail_message")
            if result is not None:
                content = (
                    f"查询完成，共 {len(result)} 行结果。"
                    if result
                    else "查询完成，结果为空。"
                )
                error = None
                detail = None
            elif fail_message:
                content = "这次查询没有成功。"
                error = fail_message
                detail = final_state.get("error")
            else:
                content = "查询完成。"
                error = None
                detail = None

        # 查询结果可能含 Decimal/datetime 等非 JSON 类型，落库前先归一化为 JSON 安全结构
        json_safe_result = (
            json.loads(json.dumps(result, ensure_ascii=False, default=str))
            if result is not None
            else None
        )

        await self.session_repository.add_message(
            session_id,
            role="assistant",
            content=content,
            query=final_state.get("query"),
            sql=sql,
            result=json_safe_result,
            error=error,
            detail=detail,
        )
        await self.session_repository.commit()
