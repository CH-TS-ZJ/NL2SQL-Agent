"""
SQL 修正失败节点

负责在 SQL 自愈循环重试次数耗尽后，把最后的 SQL 和校验错误结构化地返回给前端，
而不是继续执行一条几乎必然失败的 SQL。
"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger


async def fail_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """自愈循环重试耗尽后，结构化输出最终错误并结束流程"""

    writer = runtime.stream_writer
    step = "SQL修正失败"
    writer({"type": "progress", "step": step, "status": "error"})

    sql = state.get("sql")
    error = state.get("error")
    retry_count = state.get("retry_count", 0)

    logger.error(f"SQL 修正 {retry_count} 次后仍未通过校验，最后错误：{error}")

    # 结构化错误事件：前端可展示最后的 SQL 与校验错误详情，而非执行一条注定失败的 SQL
    writer(
        {
            "type": "error",
            "message": f"SQL 修正 {retry_count} 次后仍未通过校验，请检查问题或联系管理员。",
            "sql": sql,
            "detail": error,
            "retryCount": retry_count,
        }
    )
