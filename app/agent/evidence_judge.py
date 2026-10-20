"""检查跨论文研究字段的引文覆盖情况，不代替语义真实性审核。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agent.evidence_matrix import (
    EvidenceReference,
    RESEARCH_FIELDS,
)
from app.agent.research_state import ResearchState


class FieldCoverage(BaseModel):
    """记录一篇论文中某个研究字段的引文覆盖状态。"""

    model_config = ConfigDict(extra="forbid")

    field: Literal[
        "method",
        "experimental_conditions",
        "conclusion",
    ]
    status: Literal[
        "quote_verified",
        "insufficient",
    ]
    quote_count: int = Field(ge=0)
    references: list[EvidenceReference] = Field(
        default_factory=list
    )


class PaperCoverage(BaseModel):
    """汇总一篇论文的三个研究维度。"""

    document_id: int = Field(gt=0)
    fields: list[FieldCoverage]


class EvidenceJudgement(BaseModel):
    """汇总跨论文证据覆盖情况及需要补检的字段。"""

    sufficient_quote_coverage: bool
    papers: list[PaperCoverage]
    missing_fields: dict[int, list[str]]


def judge_evidence_coverage(
    state: ResearchState,
) -> EvidenceJudgement:
    """检查本轮通过精确引文校验的字段覆盖度。"""

    # 以已规划的检索任务确定比较对象，
    # 不能只看成功返回证据的论文，否则缺失论文会被遗漏。
    document_ids = list(dict.fromkeys(
        task["arguments"]["document_id"]
        for task in state["retrieval_plan"]
        if (
            task["tool_name"] == "search_chunks"
            and type(task["arguments"].get("document_id")) is int
            and task["arguments"]["document_id"] > 0
        )
    ))

    papers = []
    missing_fields = {}

    for document_id in document_ids:
        field_results = []
        missing = []

        for field in RESEARCH_FIELDS:
            references = []
            seen = set()

            for item in state["fact_verifications"]:
                if item.get("status") != "quote_verified":
                    continue

                fact = item["fact"]

                if (
                    fact["document_id"] != document_id
                    or fact["field"] != field
                ):
                    continue

                key = (
                    fact["document_id"],
                    fact["chunk_id"],
                )

                if key in seen:
                    continue

                seen.add(key)

                references.append(
                    EvidenceReference(
                        document_id=fact["document_id"],
                        chunk_id=fact["chunk_id"],
                        page_start=fact["page_start"],
                        page_end=fact["page_end"],
                    )
                )

            covered = bool(references)

            field_results.append(
                FieldCoverage(
                    field=field,
                    status=(
                        "quote_verified"
                        if covered
                        else "insufficient"
                    ),
                    quote_count=len(references),
                    references=references,
                )
            )

            if not covered:
                missing.append(field)

        papers.append(
            PaperCoverage(
                document_id=document_id,
                fields=field_results,
            )
        )

        if missing:
            missing_fields[document_id] = missing

    return EvidenceJudgement(
        sufficient_quote_coverage=(
            len(document_ids) >= 2
            and not missing_fields
        ),
        papers=papers,
        missing_fields=missing_fields,
    )