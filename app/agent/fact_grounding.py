"""验证模型提出的科研事实是否引用了本轮检索中的真实原文。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.research_state import EvidenceItem


ResearchField = Literal[
    "method",
    "experimental_conditions",
    "conclusion",
]


class ProposedFact(BaseModel):
    """表示模型提出的待核验研究事实。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    document_id: int = Field(gt=0)
    chunk_id: int = Field(gt=0)

    field: ResearchField

    claim: str = Field(min_length=1, max_length=2000)
    quote: str = Field(min_length=1, max_length=2000)

    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_content(self):
        """拒绝空白事实、空白引文与倒置页码。"""

        if not self.claim.strip():
            raise ValueError("claim must not be blank")

        if not self.quote.strip():
            raise ValueError("quote must not be blank")

        if self.page_end < self.page_start:
            raise ValueError("invalid page range")

        return self


class FactVerificationResult(BaseModel):
    """记录引用校验结果，不声称完成语义核验。"""

    model_config = ConfigDict(extra="forbid")

    fact: ProposedFact

    status: Literal[
        "quote_verified",
        "evidence_not_found",
        "page_mismatch",
        "quote_mismatch",
    ]

    reason: str


def verify_proposed_fact(
    fact: ProposedFact,
    evidence: list[EvidenceItem],
) -> FactVerificationResult:
    """只使用本轮检索证据核验 ID、页码和原文子串。"""

    matches = [
        item
        for item in evidence
        if (
            item["document_id"] == fact.document_id
            and item["chunk_id"] == fact.chunk_id
        )
    ]

    if not matches:
        return FactVerificationResult(
            fact=fact,
            status="evidence_not_found",
            reason="Evidence is absent from this retrieval run",
        )

    # 同一个数据库 Chunk 在本轮结果中应具有一致的来源信息。
    # 如有重复记录，必须至少存在一条完整匹配的记录。
    page_matches = [
        item
        for item in matches
        if (
            item["page_start"] == fact.page_start
            and item["page_end"] == fact.page_end
        )
    ]

    if not page_matches:
        return FactVerificationResult(
            fact=fact,
            status="page_mismatch",
            reason="Page range does not match retrieved evidence",
        )

    for item in page_matches:
        # 严格原文子串匹配，不进行大小写折叠或文本补全。
        if fact.quote in item["content"]:
            return FactVerificationResult(
                fact=fact,
                status="quote_verified",
                reason="Exact quotation found in retrieved chunk",
            )

    return FactVerificationResult(
        fact=fact,
        status="quote_mismatch",
        reason="Quotation is not an exact substring of the chunk",
    )


def verify_proposed_facts(
    facts: list[ProposedFact],
    evidence: list[EvidenceItem],
    *,
    max_facts: int = 20,
) -> list[FactVerificationResult]:
    """批量校验模型事实并限制单轮数量。"""

    if max_facts < 1:
        raise ValueError("max_facts must be positive")

    if len(facts) > max_facts:
        raise ValueError("too many proposed facts")

    return [
        verify_proposed_fact(fact, evidence)
        for fact in facts
    ]