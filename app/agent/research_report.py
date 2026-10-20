"""将最终证据矩阵转换为带来源的跨论文 Markdown 报告。"""

from collections import defaultdict
from typing import Any

from app.agent.evidence_matrix import RESEARCH_FIELDS


FIELD_NAMES = {
    "method": "研究方法",
    "experimental_conditions": "实验条件",
    "conclusion": "研究结论",
}


def _format_reference(fact: dict[str, Any]) -> str:
    """根据已核验事实生成来源标识。"""

    return (
        f"Document {fact['document_id']}, "
        f"Chunk {fact['chunk_id']}, "
        f"p.{fact['page_start']}"
        + (
            f"–{fact['page_end']}"
            if fact["page_end"] != fact["page_start"]
            else ""
        )
    )


def render_research_report(
    question: str,
    matrix: list[dict],
) -> str:
    """生成跨论文报告，明确区分引文真实性与语义支持。"""

    if not question.strip():
        raise ValueError("question must not be blank")

    lines = [
        "# 跨论文科研比较报告",
        "",
        f"**研究问题：** {question.strip()}",
        "",
        "> 本报告中的模型陈述尚未完成独立语义审核。"
        "“引用已核验”仅表示引用文字及来源匹配，"
        "不代表相关科研结论已被证明。",
        "",
    ]

    if not matrix:
        lines.extend([
            "## 检索结果",
            "",
            "未找到充分证据。",
        ])
        return "\n".join(lines) + "\n"

    for row in matrix:
        document_id = row["document_id"]
        title = row.get("title") or f"Document {document_id}"

        lines.extend([
            f"## 论文 {document_id}：{title}",
            "",
        ])

        facts_by_field = defaultdict(list)

        for fact in row.get("quote_verified_facts", []):
            if (
                fact.get("verification_status") == "quote_verified"
                and fact.get("document_id") == document_id
                and fact.get("field") in RESEARCH_FIELDS
            ):
                facts_by_field[fact["field"]].append(fact)

        for field in RESEARCH_FIELDS:
            lines.extend([
                f"### {FIELD_NAMES[field]}",
                "",
            ])

            facts = facts_by_field[field]

            if not facts:
                lines.extend([
                    "证据不足：暂无经过原文匹配的字段事实。",
                    "",
                ])
                continue

            for fact in facts:
                lines.extend([
                    "**核验状态：引用已核验，陈述待审核**",
                    "",
                    f"**模型陈述：** {fact['claim']}",
                    "",
                    f"**原文引文：** {fact['quote']}",
                    "",
                    f"**来源：** {_format_reference(fact)}",
                    "",
                ])

    lines.extend([
        "## 比较结论",
        "",
        "当前仅整理了各论文的可追溯引文。"
        "尚未完成陈述与引文之间的独立语义审核，"
        "因此不自动生成跨论文性能优劣或因果性结论。",
        "",
    ])

    return "\n".join(lines) + "\n"