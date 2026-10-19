"""读取真实检索结果，生成 Day 10 可复核的对比报告。"""

import json
from pathlib import Path

ROOT = Path("evaluation/results")
OUTPUT = ROOT / "README_day10.md"

rows = []
details = []

for size in (300, 500):
    experiment = f"chunk{size}_overlap50"
    experiments = {}

    for strategy in ("literal", "fts", "hybrid"):
        path = ROOT / f"{experiment}_{strategy}_postgres.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        summary = data["summary"]
        experiments[strategy] = {
            row["question_id"]: row
            for row in data["questions"]
        }

        rows.append(
            f"| {size}/50 | {strategy} | "
            f"{summary['evidence_recall_at_5']:.4f} | "
            f"{summary['hit_at_5']:.4f} | "
            f"{summary['mrr_at_5']:.4f} | "
            f"{summary['mean_latency_ms']:.4f} |"
        )

    for qid in experiments["literal"]:
        ranks = [
            experiments[strategy][qid]["first_complete_rank"]
            for strategy in ("literal", "fts", "hybrid")
        ]

        if len(set(ranks)) > 1:
            details.append(
                f"| {size}/50 | {qid} | "
                + " | ".join(
                    str(rank) if rank is not None else "未命中"
                    for rank in ranks
                )
                + " |"
            )

report = """# DocuRAG Day 10 检索质量对比报告

## 实验设置

- 数据：Document 31、32
- 任务：15 道关键词证据定位题
- 切分：300/50 与 500/50
- 检索：PostgreSQL Literal、FTS、Hybrid（RRF）
- Top-K：5
- 指标：Evidence Recall@5、Hit@5、MRR@5
- 环境、SHA-256 和逐题查询结果：见对应实验 JSON

## 真实实验结果

| Chunk | Strategy | Recall@5 | Hit@5 | MRR@5 | Mean latency (ms) |
|---|---|---:|---:|---:|---:|
""" + "\n".join(rows) + """

## 逐题排名差异

| Chunk | Question | Literal | FTS | Hybrid |
|---|---|---:|---:|---:|
""" + "\n".join(details) + """

## 结果分析

Literal 在当前关键词定位问题上取得最高 MRR@5。
Hybrid 相比 FTS 改善证据覆盖，但未超过 Literal 的排名表现。
500/50 在这套问题集上优于 300/50。
300/50 的 Q005 存在标准证据跨 Chunk 边界的问题。

## 局限性

1. 仅有两篇英文论文和 15 道关键词查询。
2. 当前任务不是开放式自然语言问答评估。
3. 证据完整覆盖规则会惩罚跨 Chunk 的证据。
4. 两种配置存储于不同 PostgreSQL 表，查询耗时存在环境差异。
5. 耗时来自单轮实验，没有重复测量或统计显著性检验。
6. Hybrid 使用各路 Top-5 候选池进行 RRF，未验证其他候选池大小。
7. 当前实验 Hybrid 结果保留原始单路分数和来源，不是完整融合贡献记录。
8. Vector Retriever、Embedding 和 pgvector 向量召回尚未实现、未评估。
9. 策略选择为确定性规则，不是 LLM 自主规划。

## 工程结论

保留 Metadata、Literal、FTS 和显式 Hybrid 四类检索能力。
暂不根据小样本结果调整生产默认路由。
后续优先扩大查询类型和论文数量，再评估自动策略选择。
"""

if OUTPUT.exists():
    raise FileExistsError(f"Refusing to overwrite {OUTPUT}")

OUTPUT.write_text(report, encoding="utf-8")
print("Report saved:", OUTPUT)