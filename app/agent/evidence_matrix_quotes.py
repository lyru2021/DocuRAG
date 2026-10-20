"""将经过原文校验的事实附加到论文证据矩阵。"""

from copy import deepcopy

from pydantic import BaseModel, ConfigDict, Field

from app.agent.fact_grounding import (
    ProposedFact,
    verify_proposed_fact,
)
from app.agent.research_state import EvidenceItem


class VerifiedMatrixFact(BaseModel):
    """保存引用真实但尚未完成语义审核的研究陈述。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    field: str
    claim: str
    quote: str
    document_id: int = Field(gt=0)
    chunk_id: int = Field(gt=0)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    verification_status: str = "quote_verified"


def attach_verified_facts(
    matrix: list[dict],
    verifications: list[dict],
    evidence: list[EvidenceItem],
) -> list[dict]:
    """仅将重新核实过的真实引文附加到对应论文行。"""

    enriched = deepcopy(matrix)

    # 为每篇论文建立定位，拒绝把计划外事实插入新行。
    rows = {
        row["document_id"]: row
        for row in enriched
    }

    for row in enriched:
        row["quote_verified_facts"] = []

    seen = set()

    for item in verifications:
        if item.get("status") != "quote_verified":
            continue

        # 即使状态声称已经通过，也必须重新检查来源，
        # 避免仅凭一个字符串状态信任上游结果。
        try:
            fact = ProposedFact.model_validate(item["fact"])
        except (KeyError, ValueError, TypeError):
            continue

        if fact.document_id not in rows:
            continue

        result = verify_proposed_fact(fact, evidence)

        if result.status != "quote_verified":
            continue

        key = (
            fact.document_id,
            fact.chunk_id,
            fact.field,
            fact.quote,
            fact.claim,
        )

        if key in seen:
            continue

        seen.add(key)

        record = VerifiedMatrixFact(
            field=fact.field,
            claim=fact.claim,
            quote=fact.quote,
            document_id=fact.document_id,
            chunk_id=fact.chunk_id,
            page_start=fact.page_start,
            page_end=fact.page_end,
        )

        rows[fact.document_id][
            "quote_verified_facts"
        ].append(record.model_dump(mode="json"))

    return enriched