# 评测集与端到端评测

对 `shopkeeper-agent` 的 Text-to-SQL 全链路做量化评测：执行准确率（EA）、延迟分布、失败模式。

## 前置条件

1. Docker Desktop 已启动，且 `docker compose up -d`（MySQL / ES / Qdrant / TEI）四件套就绪。
2. 元数据知识库已构建：`uv run python -m app.scripts.build_meta_knowledge -c conf/meta_config.yaml`。
3. `.env` 里已配置 `LLM_API_KEY`。

## 运行

```bash
# 全量评测（约 250 条，逐条串行）
uv run python -m eval.run_eval

# 抽样冒烟（前 20 条）
uv run python -m eval.run_eval --limit 20

# 只跑指定 id
uv run python -m eval.run_eval --ids R001 R002

# 抽样冒烟 + 开启 LLM-as-judge（每条额外调用一次 LLM 做语义正确性评分）
uv run python -m eval.run_eval --limit 20 --judge

# 生成分析报告
uv run python -m eval.analyze
```

产物落在 `eval/results/`：
- `results.jsonl`：每条一条记录（问句 / 金标准 SQL / 生成 SQL / 结果集 / 耗时 / 结果类别 / EA，开启 Langfuse 或 `--judge` 后额外含 `trace_id` / `llm_judge` / `llm_judge_correct` / `llm_judge_reason`）
- `report.md`：准确率 + 延迟分布 + 失败模式分析（含 LLM-judge 与 EA 一致性）

## 评测集说明（`dataset.yaml`）

- 规模约 255 条，覆盖地区/时间/商品/客户四维、GMV·销售额·销量·订单数·客单价等指标、排序 TOP N、过滤、HAVING、多表 JOIN、交叉维度与边界场景；难度分 easy/medium/hard。
- 数仓数据只覆盖 2025-01-01 ~ 2025-03-31，时间问句统一**锚定 2025Q1**。
- `run_eval.py` 启动时会**全量校验 gold_sql**，任一报错立即终止，保证 ground-truth 可信。

## 指标定义

- **执行准确率（EA）**：生成 SQL 的结果集与金标准 SQL 结果集一致才判对。判定前把结果归一化（见 `metrics.py`）：Decimal→float、float 保留 6 位小数、日期转字符串；每行按 value 排序、行集合再排序，消除列名/列序/行序影响。
- **失败模式分类（outcome）**：
  - `correct`：EA=True
  - `wrong_result`：有结果、非空，但与金标准不一致
  - `wrong_empty`：Agent 返回空，金标准非空（召回/过滤/时间锚定导致）
  - `validation_failed`：`fail_sql` 命中，EXPLAIN 校验自愈 3 次仍失败，未执行
  - `execution_error`：`run_sql` 抛异常（过 EXPLAIN 仍执行失败）
  - `graph_error`：图执行未正常结束

## Langfuse 轨迹评估

开启 Langfuse 后，每条评测会自动产生一条 trace（节点=span、LLM 调用=generation），并把评测结果作为 score 写到对应 trace 上，便于在 Langfuse UI 里按类别/难度聚合回看。

**开启方式**：

1. `.env` 配置 `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`（自建时另设 `LANGFUSE_HOST`）。
2. `conf/app_config.yaml` 中 `langfuse.enabled: true`。
3. 直接跑 `uv run python -m eval.run_eval`，trace 与 score 会随评测同步上报。

**写入的 score**：

| score 名 | 类型 | 含义 |
|---|---|---|
| `execution_accuracy` | BOOLEAN | 执行准确率（EA），1/0 |
| `outcome` | CATEGORICAL | 失败模式分类（correct / wrong_result / ...） |
| `latency_ms` | NUMERIC | 端到端耗时（毫秒） |
| `llm_judge` | NUMERIC | LLM-as-judge 语义正确性评分 0~1（仅 `--judge` 开启时） |

**LLM-as-judge（`--judge`）**：额外用大模型对「生成 SQL 是否语义等价于金标准」打分（`correct` + `score` 0~1 + `reason`），结果同时写入 `results.jsonl` 与 `llm_judge` score。judge 提示词见 `prompts/sql_judge.prompt`。开启后每条多一次 LLM 调用，全量 255 条会更慢。
