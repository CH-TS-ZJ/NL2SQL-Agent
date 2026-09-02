"""
评测指标与结果归一化

包含三块纯函数逻辑，不依赖基础设施，便于单测：
1. 结果集归一化：把 list[dict] 转成"与列名/行序无关"的可比较结构
2. 执行准确率（EA）：归一化后两结果集相等即判对
3. 失败模式分类：根据最终状态把每条评测归入一种失败/成功类别
"""

from __future__ import annotations

import math
from datetime import date, datetime, time
from decimal import Decimal


def normalize_value(value):
    """把单值归一化成可比较的 Python 基本类型

    - Decimal/float 统一成 float 并保留 6 位小数（消除 -0.0 / 极小浮点噪声）
    - 日期时间统一成 ISO 字符串，保证跨序列化方式可比
    - None 原样保留，用于区分 NULL 与空字符串
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return str(value)
        return round(value, 6)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def normalize_result(result) -> list[tuple]:
    """把查询结果归一化成可比较的"行多集"

    - 每行 dict 按 key 排序后取 value 元组，消除列名与列序影响
    - 每行内 value 再做一次排序，消除"同一信息不同列序"的影响
    - 行集合按元组排序，消除行序影响

    result 为 None（未执行）时返回 None，与空结果 [] 区分开。
    """
    if result is None:
        return None
    rows = []
    for row in result:
        if isinstance(row, dict):
            values = [normalize_value(v) for v in row.values()]
        else:
            values = [normalize_value(v) for v in row]
        # 对行内 value 排序，前提是 value 可比较（int/float/str 混合时兜底转 str）
        try:
            values = sorted(values, key=_sort_key)
        except TypeError:
            values = sorted(values, key=lambda v: (type(v).__name__, str(v)))
        rows.append(tuple(values))
    return sorted(rows, key=_sort_key)


def _sort_key(value):
    """排序 key，混合类型时按 (类型名, 字符串) 兜底，保证可比"""
    return (type(value).__name__, str(value))


def execution_accuracy(gen_result, gold_result) -> bool:
    """执行准确率：生成结果与金标准结果归一化后相等"""
    if gen_result is None or gold_result is None:
        return False
    return normalize_result(gen_result) == normalize_result(gold_result)


def classify_outcome(
    *,
    ea: bool,
    gen_result,
    gold_result,
    fail_message: str | None,
    exception: str | None,
    last_node: str | None,
) -> str:
    """把一条评测归入失败/成功类别

    优先级：异常 > 校验耗尽 > 结果对比，具体见 eval/README.md。
    """
    if exception is not None:
        # run_sql 抛异常（过了 EXPLAIN 仍执行失败）与其它节点异常分开标记
        return "execution_error" if last_node == "执行SQL" else "graph_error"

    if fail_message:
        # fail_sql 节点命中：EXPLAIN 校验 3 次仍失败，未执行
        return "validation_failed"

    if gen_result is None:
        return "graph_error"

    if ea:
        return "correct"

    gen_empty = len(gen_result) == 0
    gold_empty = len(gold_result or []) == 0
    if gen_empty and not gold_empty:
        return "wrong_empty"
    return "wrong_result"


def percentile(sorted_values: list[float], p: float) -> float:
    """线性插值分位数，p 取值 [0, 100]"""
    if not sorted_values:
        return 0.0
    values = sorted(sorted_values)
    k = (len(values) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return values[int(k)]
    d0 = values[int(f)] * (c - k)
    d1 = values[int(c)] * (k - f)
    return d0 + d1
