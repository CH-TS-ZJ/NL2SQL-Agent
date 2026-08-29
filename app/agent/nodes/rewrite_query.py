"""
指代消解节点

负责把用户在多轮对话中的不完整追问，改写成一句自包含的完整问数需求。
首轮问题没有历史上下文，直接透传；有历史时，把历史对话拼进提示词，
让大模型补齐被省略的维度、指标、时间范围等，并消除"它""这个"等指代。
"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import ChatTurn, DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


def _format_history(history: list[ChatTurn]) -> str:
    """把历史对话拼成模型易读的纯文本，SQL 帮助补齐上一轮的表/字段信息"""

    lines = []
    for turn in history:
        if turn["role"] == "user":
            lines.append(f"用户：{turn['content']}")
        else:
            # 助手轮优先展示上一轮消解后的完整问题，再附 SQL，方便还原真实意图
            resolved = turn.get("query") or turn["content"]
            line = f"助手：{resolved}"
            if turn.get("sql"):
                line += f"（SQL：{turn['sql']}）"
            lines.append(line)
    # 只保留最近几轮，避免历史过长挤占上下文
    return "\n".join(lines[-12:])


async def rewrite_query(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """结合历史对话把当前问题改写成自包含的完整问数需求"""

    writer = runtime.stream_writer
    step = "改写问题"
    writer({"type": "progress", "step": step, "status": "running"})

    query = state["query"]
    history = state.get("history") or []

    try:
        # 首轮没有历史，无需改写，直接透传原始问题
        if not history:
            writer({"type": "progress", "step": step, "status": "success"})
            return {"query": query}

        prompt = PromptTemplate(
            template=load_prompt("rewrite_query"),
            input_variables=["history", "query"],
        )
        output_parser = StrOutputParser()
        chain = prompt | llm | output_parser

        result = await chain.ainvoke(
            {"history": _format_history(history), "query": query}
        )

        # 模型偶尔会多输出空白或空串，此时回退为原始问题，不阻断后续链路
        resolved = (result or "").strip()
        if not resolved:
            resolved = query

        logger.info(f"指代消解：{query} -> {resolved}")
        writer({"type": "progress", "step": step, "status": "success"})
        return {"query": resolved}
    except Exception as e:
        # 改写是增强步骤，失败时降级为原始问题继续跑，避免多轮追问被整体阻断
        logger.warning(f"指代消解失败，回退为原始问题：{e}")
        writer({"type": "progress", "step": step, "status": "success"})
        return {"query": query}
