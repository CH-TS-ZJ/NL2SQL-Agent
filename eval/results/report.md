# Text-to-SQL 端到端评测报告

- 评测条数：255
- 执行准确率（EA）：215/255 = 84.3%

## 1. 执行准确率

### 按难度

| 难度 | 正确 | 总数 | EA |
|---|---|---|---|
| easy | 56 | 58 | 96.6% |
| hard | 45 | 62 | 72.6% |
| medium | 114 | 135 | 84.4% |

### 按类别

| 类别 | 正确 | 总数 | EA |
|---|---|---|---|
| HAVING | 11 | 15 | 73.3% |
| 交叉维度 | 13 | 15 | 86.7% |
| 单指标聚合 | 24 | 25 | 96.0% |
| 商品维度 | 26 | 30 | 86.7% |
| 地区维度 | 19 | 20 | 95.0% |
| 多指标计算 | 17 | 25 | 68.0% |
| 多表JOIN | 15 | 15 | 100.0% |
| 客户维度 | 24 | 25 | 96.0% |
| 排序TOP N | 17 | 20 | 85.0% |
| 时间维度 | 21 | 30 | 70.0% |
| 边界 | 13 | 15 | 86.7% |
| 过滤条件 | 15 | 20 | 75.0% |

## 2. 延迟分布（端到端）

| 指标 | 均值 | p50 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|---|
| 端到端(ms) | 43494.4 | 36384.3 | 62593.6 | 73471.7 | 180011.5 | 180016.8 |

### 逐节点耗时（按均值降序）

| 节点 | 样本数 | 均值(ms) | p90(ms) |
|---|---|---|---|
| 召回字段取值 | 252 | 19970.2 | 31323.0 |
| 召回指标信息 | 255 | 16378.4 | 20037.3 |
| 召回字段信息 | 253 | 10460.2 | 15925.8 |
| 生成SQL | 248 | 8939.2 | 13174.0 |
| 过滤指标信息 | 250 | 6766.1 | 11167.0 |
| 过滤表信息 | 249 | 6381.0 | 9339.0 |
| 合并召回信息 | 250 | 7.2 | 10.9 |
| 校验SQL | 248 | 2.1 | 2.6 |
| 添加额外上下文 | 249 | 1.2 | 1.5 |
| 执行SQL | 248 | 1.1 | 1.4 |
| 抽取关键词 | 255 | 0.0 | 0.0 |
| 改写问题 | 255 | 0.0 | 0.0 |

### SQL 自愈重试分布

| 重试次数 | 条数 |
|---|---|
| 0 | 255 |

### 最慢的 10 条

| id | outcome | e2e(ms) | 问句 |
|---|---|---|---|
| X010 | graph_error | 180016.8 | 统计各品类各性别的订单数 |
| T013 | graph_error | 180015.9 | 3 月各周的销售额（按日期分组） |
| M013 | graph_error | 180015.1 | 各品类的平均客单价 |
| M022 | graph_error | 180008.4 | 平均客单价最高的品类 |
| X004 | graph_error | 180006.9 | 统计各性别各品牌的销售额 |
| P029 | graph_error | 180005.8 | 各品类的订单数量 |
| M024 | graph_error | 180005.8 | 总销量、总销售额和客单价三个指标 |
| X008 | correct | 102239.3 | 统计各性别各月份的销售额 |
| N010 | wrong_result | 90952.9 | 客单价最高的前 3 个大区 |
| X015 | correct | 85069.2 | 统计各性别各地区的订单数 |

## 3. 失败模式分析

| outcome | 含义 | 条数 | 占比 |
|---|---|---|---|
| correct | 结果正确 | 215 | 84.3% |
| wrong_result | 结果错误（有结果但与金标准不一致） | 30 | 11.8% |
| graph_error | 图执行异常 | 7 | 2.7% |
| wrong_empty | 结果为空（金标准非空） | 3 | 1.2% |

### wrong_result（结果错误（有结果但与金标准不一致））

- **问句**：销售额排名第二的大区是哪个
  - 生成 SQL：`SELECT dim_region.region_name AS 大区 FROM fact_order JOIN dim_region ON fact_order.region_id = dim_region.region_id GROUP BY dim_region.region_name ORDER BY SUM(fact_order.order_amount) DESC LIMIT 1 OFFSET 1`
  - 金标准 SQL：`SELECT r.region_name AS 大区, SUM(f.order_amount) AS 销售额 FROM fact_order f JOIN dim_region r ON f.region_id = r.region_id GROUP BY r.region_name ORDER BY 销售额 DESC LIMIT 1 OFFSET 1`
  - 重试次数：0
- **问句**：按日统计 2025 年 1 月 1 日到 1 月 5 日的销售额
  - 生成 SQL：`SELECT date_id AS 日期, SUM(order_amount) AS 销售额 FROM fact_order WHERE date_id BETWEEN 20250101 AND 20250105 GROUP BY date_id ORDER BY date_id`
  - 金标准 SQL：`SELECT d.day AS 日, SUM(f.order_amount) AS 销售额 FROM fact_order f JOIN dim_date d ON f.date_id = d.date_id WHERE d.month = 1 AND d.day BETWEEN 1 AND 5 GROUP BY d.day ORDER BY d.day`
  - 重试次数：0
- **问句**：哪个日期产生的订单最多
  - 生成 SQL：`SELECT date_id AS 日期, COUNT(order_id) AS 订单数量 FROM fact_order GROUP BY date_id ORDER BY 订单数量 DESC LIMIT 1`
  - 金标准 SQL：`SELECT d.day AS 日, COUNT(*) AS 订单数 FROM fact_order f JOIN dim_date d ON f.date_id = d.date_id GROUP BY d.day ORDER BY 订单数 DESC LIMIT 1`
  - 重试次数：0
- **问句**：3 月的销售总额是多少
  - 生成 SQL：`SELECT SUM(order_amount) AS 销售总额 FROM fact_order WHERE date_id BETWEEN 20260301 AND 20260331`
  - 金标准 SQL：`SELECT SUM(f.order_amount) AS 销售总额 FROM fact_order f JOIN dim_date d ON f.date_id = d.date_id WHERE d.month = 3`
  - 重试次数：0

### graph_error（图执行异常）

- **问句**：3 月各周的销售额（按日期分组）
  - 生成 SQL：`-`
  - 金标准 SQL：`SELECT d.day AS 日, SUM(f.order_amount) AS 销售额 FROM fact_order f JOIN dim_date d ON f.date_id = d.date_id WHERE d.month = 3 GROUP BY d.day ORDER BY d.day`
  - 异常：图执行超时(>180s)
  - 重试次数：0
- **问句**：各品类的订单数量
  - 生成 SQL：`-`
  - 金标准 SQL：`SELECT p.category AS 品类, COUNT(*) AS 订单数 FROM fact_order f JOIN dim_product p ON f.product_id = p.product_id GROUP BY p.category ORDER BY 订单数 DESC`
  - 异常：图执行超时(>180s)
  - 重试次数：0
- **问句**：各品类的平均客单价
  - 生成 SQL：`-`
  - 金标准 SQL：`SELECT p.category AS 品类, SUM(f.order_amount) / COUNT(*) AS 平均客单价 FROM fact_order f JOIN dim_product p ON f.product_id = p.product_id GROUP BY p.category ORDER BY 平均客单价 DESC`
  - 异常：图执行超时(>180s)
  - 重试次数：0
- **问句**：平均客单价最高的品类
  - 生成 SQL：`-`
  - 金标准 SQL：`SELECT p.category AS 品类, SUM(f.order_amount) / COUNT(*) AS 平均客单价 FROM fact_order f JOIN dim_product p ON f.product_id = p.product_id GROUP BY p.category ORDER BY 平均客单价 DESC LIMIT 1`
  - 异常：图执行超时(>180s)
  - 重试次数：0

### wrong_empty（结果为空（金标准非空））

- **问句**：三个月里哪个月的销售额最高
  - 生成 SQL：`SELECT d.month AS 月份, SUM(f.order_amount) AS 销售额 FROM fact_order f JOIN dim_date d ON f.date_id = d.date_id WHERE f.date_id >= 20260701 AND f.date_id <= 20260930 GROUP BY d.month ORDER BY 销售额 DESC LIMIT 1`
  - 金标准 SQL：`SELECT d.month AS 月份, SUM(f.order_amount) AS 销售额 FROM fact_order f JOIN dim_date d ON f.date_id = d.date_id GROUP BY d.month ORDER BY 销售额 DESC LIMIT 1`
  - 重试次数：0
- **问句**：2 月每天的销售额，只列出销售额超过 1000 的日期
  - 生成 SQL：`SELECT date_id, SUM(order_amount) AS 销售额 FROM fact_order WHERE date_id BETWEEN 20260201 AND 20260228 GROUP BY date_id HAVING SUM(order_amount) > 1000`
  - 金标准 SQL：`SELECT d.day AS 日, SUM(f.order_amount) AS 销售额 FROM fact_order f JOIN dim_date d ON f.date_id = d.date_id WHERE d.month = 2 GROUP BY d.day HAVING SUM(f.order_amount) > 1000 ORDER BY d.day`
  - 重试次数：0
- **问句**：1 月、2 月、3 月各自的销售额
  - 生成 SQL：`SELECT MONTH(STR_TO_DATE(CAST(date_id AS CHAR), '%Y%m%d')) AS 月份, SUM(order_amount) AS 销售额 FROM fact_order WHERE date_id BETWEEN 20260101 AND 20260331 GROUP BY 月份 ORDER BY 月份`
  - 金标准 SQL：`SELECT d.month AS 月份, SUM(f.order_amount) AS 销售额 FROM fact_order f JOIN dim_date d ON f.date_id = d.date_id GROUP BY d.month ORDER BY d.month`
  - 重试次数：0
