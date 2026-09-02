"""
评测结果分析

读取 run_eval.py 产出的 results.jsonl，生成 report.md：
1. 执行准确率（EA）：总览 + 按难度 + 按类别
2. 延迟分布：端到端分位数 + 逐节点耗时 + 最慢样本
3. 失败模式：各 outcome 计数 + 代表性样本

用法（项目根目录）：
    uv run python -m eval.analyze [--in eval/results/results.jsonl] [--out eval/results/report.md]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from eval.metrics import percentile

RESULTS_DIR = Path(__file__).parent / "results"


def _load(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _ea_by_group(records: list[dict], key: str) -> list[tuple[str, int, int, float]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        groups[r.get(key, "?")].append(r)
    rows = []
    for name in sorted(groups):
        rs = groups[name]
        correct = sum(1 for r in rs if r["ea"])
        rows.append((name, correct, len(rs), correct / len(rs) * 100))
    return rows


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def _pct(v: float) -> str:
    return f"{v:.1f}%"


def _ms(v: float) -> str:
    return f"{v:.1f}"


def _node_stats(records: list[dict]) -> list[tuple[str, int, float, float]]:
    """逐节点耗时：样本数 / 均值 / p90"""
    agg: dict[str, list[float]] = defaultdict(list)
    for r in records:
        for node, ms in (r.get("node_times_ms") or {}).items():
            agg[node].append(ms)
    rows = []
    for node in sorted(agg, key=lambda n: -sum(agg[n]) / len(agg[n])):
        vals = agg[node]
        rows.append((node, len(vals), sum(vals) / len(vals), percentile(vals, 90)))
    return rows


_OUTCOME_LABEL = {
    "correct": "结果正确",
    "wrong_result": "结果错误（有结果但与金标准不一致）",
    "wrong_empty": "结果为空（金标准非空）",
    "validation_failed": "SQL 校验失败（自愈 3 次仍失败，未执行）",
    "execution_error": "执行报错（过 EXPLAIN 仍执行失败）",
    "graph_error": "图执行异常",
}


def _sample_block(r: dict) -> str:
    lines = [
        f"- **问句**：{r['query']}",
        f"  - 生成 SQL：`{r.get('gen_sql') or '-'}`",
        f"  - 金标准 SQL：`{r.get('gold_sql') or '-'}`",
    ]
    if r.get("fail_message"):
        lines.append(f"  - 失败信息：{r['fail_message']} / {r.get('error') or '-'}")
    elif r.get("exception"):
        lines.append(f"  - 异常：{r['exception']}")
    lines.append(f"  - 重试次数：{r.get('retry_count', 0)}")
    return "\n".join(lines)


def _build_report(records: list[dict]) -> str:
    total = len(records)
    correct = sum(1 for r in records if r["ea"])
    ea_overall = correct / total * 100 if total else 0.0

    # 延迟
    e2e = sorted(r["e2e_ms"] for r in records)
    retry_dist = defaultdict(int)
    for r in records:
        retry_dist[r.get("retry_count", 0)] += 1

    # 失败模式
    outcome_counts = defaultdict(int)
    by_outcome: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        outcome_counts[r["outcome"]] += 1
        by_outcome[r["outcome"]].append(r)

    out: list[str] = []
    out.append("# Text-to-SQL 端到端评测报告\n")
    out.append(f"- 评测条数：{total}")
    out.append(f"- 执行准确率（EA）：{correct}/{total} = {ea_overall:.1f}%\n")

    out.append("## 1. 执行准确率\n")
    out.append("### 按难度\n")
    out.append(_markdown_table(
        ["难度", "正确", "总数", "EA"],
        [[d, str(c), str(n), _pct(c / n * 100)] for d, c, n, _ in _ea_by_group(records, "difficulty")],
    ))
    out.append("\n### 按类别\n")
    out.append(_markdown_table(
        ["类别", "正确", "总数", "EA"],
        [[d, str(c), str(n), _pct(c / n * 100)] for d, c, n, _ in _ea_by_group(records, "category")],
    ))

    out.append("\n## 2. 延迟分布（端到端）\n")
    out.append(_markdown_table(
        ["指标", "均值", "p50", "p90", "p95", "p99", "max"],
        [[
            "端到端(ms)",
            _ms(sum(e2e) / total),
            _ms(percentile(e2e, 50)),
            _ms(percentile(e2e, 90)),
            _ms(percentile(e2e, 95)),
            _ms(percentile(e2e, 99)),
            _ms(max(e2e)),
        ]],
    ))
    out.append("\n### 逐节点耗时（按均值降序）\n")
    out.append(_markdown_table(
        ["节点", "样本数", "均值(ms)", "p90(ms)"],
        [[n, str(c), _ms(m), _ms(p)] for n, c, m, p in _node_stats(records)],
    ))
    out.append("\n### SQL 自愈重试分布\n")
    out.append(_markdown_table(
        ["重试次数", "条数"],
        [[str(k), str(v)] for k, v in sorted(retry_dist.items())],
    ))
    out.append("\n### 最慢的 10 条\n")
    slowest = sorted(records, key=lambda r: -r["e2e_ms"])[:10]
    out.append(_markdown_table(
        ["id", "outcome", "e2e(ms)", "问句"],
        [[r["id"], r["outcome"], _ms(r["e2e_ms"]), r["query"][:40]] for r in slowest],
    ))

    out.append("\n## 3. 失败模式分析\n")
    out.append(_markdown_table(
        ["outcome", "含义", "条数", "占比"],
        [
            [k, _OUTCOME_LABEL.get(k, k), str(outcome_counts.get(k, 0)),
             _pct(outcome_counts.get(k, 0) / total * 100)]
            for k in sorted(outcome_counts, key=lambda k: -outcome_counts[k])
        ],
    ))
    for outcome in sorted(by_outcome, key=lambda k: -outcome_counts[k]):
        if outcome == "correct":
            continue
        rs = by_outcome[outcome][:4]
        out.append(f"\n### {outcome}（{_OUTCOME_LABEL.get(outcome, outcome)}）\n")
        for r in rs:
            out.append(_sample_block(r))

    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_path", default=None)
    parser.add_argument("--out", dest="out_path", default=None)
    args = parser.parse_args()

    in_path = Path(args.in_path) if args.in_path else RESULTS_DIR / "results.jsonl"
    out_path = Path(args.out_path) if args.out_path else RESULTS_DIR / "report.md"

    records = _load(in_path)
    if not records:
        print(f"{in_path} 为空。", flush=True)
        return

    report = _build_report(records)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"报告已生成：{out_path}", flush=True)
    print(report)


if __name__ == "__main__":
    main()
