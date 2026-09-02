"""
端到端评测 harness

逐条执行评测集：跑 LangGraph 全链路 -> 采集最终状态/逐节点耗时/异常 ->
用金标准 SQL 执行结果算执行准确率（EA）与失败模式分类 -> 写 results.jsonl。

复用 app/agent/graph.py 的 graph 与客户端初始化，复用 app/services/query_service.py
的 stream_mode=["custom","values"] 消费方式。金标准结果与 Agent 结果都通过
DWMySQLRepository.run 执行，走同一 DB、同一序列化路径，保证可比。

特性：
- 断点续跑：默认跳过 results.jsonl 中已有的 id，追加写入（--fresh 从头重跑）
- 连接类瞬时故障自动重试（--max-attempts 控制），避免临时断连污染结果

用法（项目根目录）：
    uv run python -m eval.run_eval                    # 全量（自动续跑）
    uv run python -m eval.run_eval --limit 20         # 抽样冒烟
    uv run python -m eval.run_eval --ids R001 R002    # 只跑指定 id
    uv run python -m eval.run_eval --judge            # 追加 LLM-as-judge 语义评分
    uv run python -m eval.run_eval --fresh            # 从头重跑（清空旧结果）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import yaml

from app.agent.context import DataAgentContext
from app.agent.graph import graph
from app.agent.state import DataAgentState
from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import (
    dw_mysql_client_manager,
    meta_mysql_client_manager,
)
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.core.langfuse import build_handler, flush, get_client
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository
from eval.llm_judge import judge_sql
from eval.metrics import classify_outcome, execution_accuracy

DATASET_PATH = Path(__file__).parent / "dataset.yaml"
RESULTS_DIR = Path(__file__).parent / "results"
DEFAULT_OUT = RESULTS_DIR / "results.jsonl"

# 瞬时连接类错误关键字：命中则重试，其余错误直接记录
# 注意：timeout 不在此列——LLM 挂起（连接建立但无响应）时重试只会再等一轮超时
_TRANSIENT_HINTS = ("connection", "reset by peer", "refused")

# 单条查询的图执行超时（秒）：正常 30~90s，留足余量；超过即判定为 LLM 挂起
PER_QUERY_TIMEOUT_S = 180


def load_dataset() -> list[dict]:
    with DATASET_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _filter_dataset(dataset: list[dict], ids: list[str] | None, limit: int | None) -> list[dict]:
    if ids:
        wanted = set(ids)
        dataset = [d for d in dataset if d["id"] in wanted]
    if limit:
        dataset = dataset[:limit]
    return dataset


def _is_transient_error(exc: str | None) -> bool:
    if not exc:
        return False
    low = exc.lower()
    return any(h in low for h in _TRANSIENT_HINTS)


def _langfuse_config(handler, item: dict) -> dict | None:
    """Langfuse 启用时，为一次图执行组装 trace 元数据（名称=id、标签=类别/难度/id）"""
    if handler is None:
        return None
    return {
        "callbacks": [handler],
        "metadata": {
            "langfuse_trace_name": item["id"],
            "langfuse_tags": [
                item.get("category", ""),
                item.get("difficulty", ""),
                item["id"],
            ],
        },
    }


def _score_trace(client, trace_id: str, ea: bool, outcome: str, e2e_ms: float, judge: dict | None):
    """把评测结果作为 score 写到对应 trace 上（EA / outcome / 延迟 / LLM-judge）"""
    client.create_score(
        trace_id=trace_id, name="execution_accuracy", value=1 if ea else 0, data_type="BOOLEAN"
    )
    client.create_score(
        trace_id=trace_id, name="outcome", value=outcome, data_type="CATEGORICAL"
    )
    client.create_score(
        trace_id=trace_id, name="latency_ms", value=e2e_ms, data_type="NUMERIC"
    )
    if judge is not None:
        client.create_score(
            trace_id=trace_id,
            name="llm_judge",
            value=judge["score"],
            data_type="NUMERIC",
            comment=judge["reason"],
        )


async def _validate_gold_sql(dw_repo: DWMySQLRepository, dataset: list[dict]) -> bool:
    """启动前全量校验 gold_sql，任一报错立即失败，保证 ground-truth 可信"""
    ok = True
    for item in dataset:
        try:
            await dw_repo.run(item["gold_sql"])
        except Exception as e:
            ok = False
            print(f"[gold_sql 校验失败] {item['id']}: {item['gold_sql']}\n  -> {e}", flush=True)
    return ok


async def _run_graph(
    state: DataAgentState, context: DataAgentContext, item: dict
) -> tuple[dict, dict, str | None, str | None, str | None]:
    """执行一次图，返回 (final_state, node_times, last_node, exception, trace_id)"""
    final_state: dict = {}
    node_start: dict[str, float] = {}
    node_times: dict[str, float] = {}
    last_node: str | None = None
    exception: str | None = None

    handler = build_handler()
    config = _langfuse_config(handler, item)

    try:
        async with asyncio.timeout(PER_QUERY_TIMEOUT_S):
            async for chunk in graph.astream(
                input=state, context=context, stream_mode=["custom", "values"], config=config
            ):
                mode, data = chunk
                now = time.perf_counter()
                if mode == "custom" and isinstance(data, dict):
                    step = data.get("step")
                    status = data.get("status")
                    if step:
                        last_node = step
                        if status == "running":
                            node_start[step] = now
                        elif status in ("success", "error"):
                            if step in node_start:
                                node_times[step] = now - node_start.pop(step)
                else:
                    final_state = data
    except TimeoutError:
        exception = f"图执行超时(>{PER_QUERY_TIMEOUT_S}s)"
    except Exception as e:
        exception = str(e)

    trace_id = handler.last_trace_id if handler is not None else None
    return final_state, node_times, last_node, exception, trace_id


async def _run_one(
    item: dict,
    context: DataAgentContext,
    dw_repo: DWMySQLRepository,
    max_attempts: int,
    judge: bool,
) -> dict:
    """跑一条评测，返回一条 results 记录（含重试）"""
    state = DataAgentState(query=item["query"], original_query=item["query"], history=[])

    # 金标准结果：与 Agent 结果走同一 DW 仓储，序列化路径一致（带重试）
    gold_result = None
    gold_exception: str | None = None
    for attempt in range(max_attempts):
        try:
            gold_result = await dw_repo.run(item["gold_sql"])
            gold_exception = None
            break
        except Exception as e:
            gold_exception = str(e)
            if not _is_transient_error(gold_exception) or attempt == max_attempts - 1:
                break
            await asyncio.sleep(5 * (attempt + 1))

    t0 = time.perf_counter()
    final_state, node_times, last_node, exception, trace_id = await _run_graph(
        state, context, item
    )

    # 图执行若遇到瞬时连接错误，重试整条链路
    for attempt in range(1, max_attempts):
        if not _is_transient_error(exception):
            break
        await asyncio.sleep(5 * attempt)
        final_state, node_times, last_node, exception, trace_id = await _run_graph(
            state, context, item
        )
    t1 = time.perf_counter()
    e2e_ms = round((t1 - t0) * 1000, 2)

    if gold_exception is not None:
        # 金标准 SQL 都执行不了，这条无法判定，标记为 graph_error 并附因
        record = {
            "id": item["id"],
            "category": item["category"],
            "difficulty": item["difficulty"],
            "query": item["query"],
            "gold_sql": item["gold_sql"],
            "gen_sql": final_state.get("sql"),
            "retry_count": final_state.get("retry_count", 0),
            "fail_message": final_state.get("fail_message"),
            "error": final_state.get("error"),
            "e2e_ms": e2e_ms,
            "node_times_ms": {k: round(v * 1000, 2) for k, v in node_times.items()},
            "exception": f"gold_sql 执行失败: {gold_exception}",
            "last_node": last_node,
            "gen_result": None,
            "gold_result": None,
            "ea": False,
            "outcome": "graph_error",
            "trace_id": trace_id,
            "llm_judge": None,
            "llm_judge_correct": None,
            "llm_judge_reason": None,
        }
        client = get_client()
        if client is not None and trace_id is not None:
            _score_trace(client, trace_id, False, "graph_error", e2e_ms, None)
        return record

    gen_result = final_state.get("result")
    ea = execution_accuracy(gen_result, gold_result)
    outcome = classify_outcome(
        ea=ea,
        gen_result=gen_result,
        gold_result=gold_result,
        fail_message=final_state.get("fail_message"),
        exception=exception,
        last_node=last_node,
    )

    # LLM-as-judge：可选，开启时对生成 SQL 做语义正确性评分
    judge_result = None
    if judge:
        judge_result = await judge_sql(
            query=item["query"],
            gold_sql=item["gold_sql"],
            gen_sql=final_state.get("sql"),
            gold_result=gold_result,
            gen_result=gen_result,
        )

    record = {
        "id": item["id"],
        "category": item["category"],
        "difficulty": item["difficulty"],
        "query": item["query"],
        "gold_sql": item["gold_sql"],
        "gen_sql": final_state.get("sql"),
        "retry_count": final_state.get("retry_count", 0),
        "fail_message": final_state.get("fail_message"),
        "error": final_state.get("error"),
        "e2e_ms": e2e_ms,
        "node_times_ms": {k: round(v * 1000, 2) for k, v in node_times.items()},
        "exception": exception,
        "last_node": last_node,
        "gen_result": gen_result,
        "gold_result": gold_result,
        "ea": ea,
        "outcome": outcome,
        "trace_id": trace_id,
        "llm_judge": judge_result["score"] if judge_result else None,
        "llm_judge_correct": judge_result["correct"] if judge_result else None,
        "llm_judge_reason": judge_result["reason"] if judge_result else None,
    }

    client = get_client()
    if client is not None and trace_id is not None:
        _score_trace(client, trace_id, ea, outcome, e2e_ms, judge_result)

    return record


async def run(dataset: list[dict], out_path: Path, fresh: bool, max_attempts: int, judge: bool):
    # 断点续跑：加载已有结果，跳过已完成的 id
    done_ids: set[str] = set()
    if out_path.exists() and not fresh:
        with out_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        done_ids.add(json.loads(line)["id"])
                    except json.JSONDecodeError:
                        pass
    todo = [d for d in dataset if d["id"] not in done_ids]
    print(f"总 {len(dataset)} 条，已完成 {len(done_ids)} 条，本轮执行 {len(todo)} 条。", flush=True)

    qdrant_client_manager.init()
    embedding_client_manager.init()
    es_client_manager.init()
    meta_mysql_client_manager.init()
    dw_mysql_client_manager.init()

    try:
        async with (
            meta_mysql_client_manager.session_factory() as meta_session,
            dw_mysql_client_manager.session_factory() as dw_session,
        ):
            meta_repo = MetaMySQLRepository(meta_session)
            dw_repo = DWMySQLRepository(dw_session)
            context = DataAgentContext(
                column_qdrant_repository=ColumnQdrantRepository(qdrant_client_manager.client),
                embedding_client=embedding_client_manager.client,
                metric_qdrant_repository=MetricQdrantRepository(qdrant_client_manager.client),
                value_es_repository=ValueESRepository(es_client_manager.client),
                meta_mysql_repository=meta_repo,
                dw_mysql_repository=dw_repo,
            )

            if not await _validate_gold_sql(dw_repo, todo):
                print("gold_sql 校验未通过，终止评测。", flush=True)
                sys.exit(1)

            RESULTS_DIR.mkdir(parents=True, exist_ok=True)
            mode = "w" if fresh else "a"
            with out_path.open(mode, encoding="utf-8") as f:
                for i, item in enumerate(todo, 1):
                    try:
                        record = await _run_one(item, context, dw_repo, max_attempts, judge)
                    except Exception as e:
                        # 单条兜底：任何未预期异常都不应中断整轮
                        record = {
                            "id": item["id"],
                            "category": item["category"],
                            "difficulty": item["difficulty"],
                            "query": item["query"],
                            "gold_sql": item["gold_sql"],
                            "gen_sql": None,
                            "retry_count": 0,
                            "fail_message": None,
                            "error": None,
                            "e2e_ms": 0.0,
                            "node_times_ms": {},
                            "exception": f"harness 未预期异常: {e}",
                            "last_node": None,
                            "gen_result": None,
                            "gold_result": None,
                            "ea": False,
                            "outcome": "graph_error",
                            "trace_id": None,
                            "llm_judge": None,
                            "llm_judge_correct": None,
                            "llm_judge_reason": None,
                        }
                    f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                    f.flush()
                    print(
                        f"[{i}/{len(todo)}] {record['id']} {record['outcome']} "
                        f"ea={record['ea']} e2e={record['e2e_ms']}ms",
                        flush=True,
                    )
    finally:
        for closer in (
            qdrant_client_manager.close,
            es_client_manager.close,
            meta_mysql_client_manager.close,
            dw_mysql_client_manager.close,
        ):
            try:
                await closer()
            except Exception:
                pass
        # 把 Langfuse traces 与 scores 落盘（未启用时为 no-op）
        flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="*", default=None, help="只跑指定 id")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 条")
    parser.add_argument("--out", default=None, help="输出 JSONL 路径")
    parser.add_argument("--fresh", action="store_true", help="从头重跑（清空旧结果）")
    parser.add_argument("--max-attempts", type=int, default=3, help="单条最大尝试次数")
    parser.add_argument(
        "--judge",
        action="store_true",
        help="开启 LLM-as-judge 对生成 SQL 做语义正确性评分（额外调用 LLM，逐条更慢）",
    )
    args = parser.parse_args()

    dataset = _filter_dataset(load_dataset(), args.ids, args.limit)
    if not dataset:
        print("评测集为空。", flush=True)
        sys.exit(1)

    out_path = Path(args.out) if args.out else DEFAULT_OUT
    asyncio.run(run(dataset, out_path, args.fresh, args.max_attempts, args.judge))


if __name__ == "__main__":
    main()
