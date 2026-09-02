"""
LLM-as-judge 评测

用大模型对「生成 SQL 是否语义正确」做自动评分，作为执行准确率(EA)之外的
定性补充。复用 app.agent.llm.llm 与 prompts/sql_judge.prompt，输出
{"correct", "score", "reason"}。judge 失败时降级为安全值，不阻断评测主流程。
"""

from __future__ import annotations

import json

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate

from app.agent.llm import llm
from app.prompt.prompt_loader import load_prompt

# 结果集进提示词前截断的行数，控制 token 与 judge 聚焦度
_RESULT_ROW_LIMIT = 20


def _dump_result(result) -> str:
    """把结果集序列化成提示词可读文本，空结果与超长结果特殊处理"""
    if result is None:
        return "（无结果）"
    rows = result if isinstance(result, list) else list(result)
    shown = rows[:_RESULT_ROW_LIMIT]
    text = json.dumps(shown, ensure_ascii=False, default=str)
    if len(rows) > _RESULT_ROW_LIMIT:
        text += f"\n...（共 {len(rows)} 行，已截断）"
    return text


async def judge_sql(
    query: str,
    gold_sql: str,
    gen_sql: str | None,
    gold_result,
    gen_result,
) -> dict:
    """对一条生成 SQL 做语义正确性评分，返回 {"correct", "score", "reason"}"""
    # 未生成 SQL，直接判 0，不额外调用 judge LLM
    if not gen_sql:
        return {"correct": False, "score": 0.0, "reason": "未生成可执行 SQL"}

    prompt = PromptTemplate(
        template=load_prompt("sql_judge"),
        input_variables=["query", "gold_sql", "gen_sql", "gold_result", "gen_result"],
    )
    chain = prompt | llm | JsonOutputParser()

    try:
        result = await chain.ainvoke(
            {
                "query": query,
                "gold_sql": gold_sql,
                "gen_sql": gen_sql,
                "gold_result": _dump_result(gold_result),
                "gen_result": _dump_result(gen_result),
            }
        )
    except Exception as e:
        # judge 调用失败降级：不给分也不阻断评测主流程
        return {"correct": False, "score": 0.0, "reason": f"judge 调用失败: {e}"}

    # 归一化输出，容忍 judge 偶尔返回结构不完全符合预期
    try:
        correct = bool(result.get("correct", False))
        score = max(0.0, min(1.0, float(result.get("score", 0.0))))
        reason = str(result.get("reason", "")).strip()
    except (AttributeError, TypeError, ValueError):
        return {"correct": False, "score": 0.0, "reason": "judge 输出解析失败"}

    return {"correct": correct, "score": score, "reason": reason}
