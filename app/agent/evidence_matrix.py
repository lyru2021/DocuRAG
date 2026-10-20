"""构建按论文和研究维度组织的可追溯证据矩阵。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.research_state import EvidenceItem


EvidenceStatus = Literal[
    "supported",
    "insufficient",
    "not_searched",
    "inferred",
]

RESEARCH_FIELDS = (
    "method",
    "experimental_conditions",
    "conclusion",
)


class EvidenceReference(BaseModel):
    """记录能够追溯到真实 Chunk 的证据位置。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    document_id: int = Field(gt=0)
    chunk_id: int = Field(gt=0)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_page_range(self):
        """拒绝页码倒置。"""

        if self.page_end < self.page_start:
            raise ValueError("invalid page range")

        return self


class MatrixField(BaseModel):
    """表示研究维度的内容、状态和来源。"""

    model_config = ConfigDict(extra="forbid")

    status: EvidenceStatus
    value: str | None = None
    references: list[EvidenceReference] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_support(self):
        """受支持字段必须同时具有正文内容与证据。"""

        if self.status == "supported":
            if not self.value or not self.value.strip():
                raise ValueError(
                    "supported field requires a value"
                )

            if not self.references:
                raise ValueError(
                    "supported field requires references"
                )

        if self.status in {"insufficient", "not_searched"}:
            if self.value is not None or self.references:
                raise ValueError(
                    "unverified field cannot contain claims or references"
                )

        return self


class PaperEvidenceRow(BaseModel):
    """一篇论文对应一行跨论文比较记录。"""

    document_id: int = Field(gt=0)
    title: str | None = None

    method: MatrixField
    experimental_conditions: MatrixField
    conclusion: MatrixField

    candidate_references: list[EvidenceReference] = Field(
        default_factory=list
    )


def make_empty_field(
    *,
    searched: bool,
) -> MatrixField:
    """根据是否已有候选证据设置待核验状态。"""

    return MatrixField(
        status="insufficient" if searched else "not_searched"
    )


def build_evidence_matrix(
    document_ids: list[int],
    evidence: list[EvidenceItem],
) -> list[PaperEvidenceRow]:
    """从候选证据构建矩阵，不自动生成未经验证的研究结论。"""

    by_document: dict[int, list[EvidenceItem]] = {
        document_id: []
        for document_id in document_ids
    }

    # 只接收此次比较涉及的论文证据。
    for item in evidence:
        document_id = item["document_id"]

        if document_id not in by_document:
            continue

        by_document[document_id].append(item)

    rows = []

    for document_id in document_ids:
        candidates = by_document[document_id]

        references = []
        seen = set()

        for item in candidates:
            reference = EvidenceReference(
                document_id=item["document_id"],
                chunk_id=item["chunk_id"],
                page_start=item["page_start"],
                page_end=item["page_end"],
            )

            key = (
                reference.document_id,
                reference.chunk_id,
            )

            if key in seen:
                continue

            seen.add(key)
            references.append(reference)

        # 标题仅来自检索到的真实证据，不自行构造。
        title = candidates[0]["title"] if candidates else None

        rows.append(
            PaperEvidenceRow(
                document_id=document_id,
                title=title,
                method=make_empty_field(
                    searched=bool(candidates)
                ),
                experimental_conditions=make_empty_field(
                    searched=bool(candidates)
                ),
                conclusion=make_empty_field(
                    searched=bool(candidates)
                ),
                candidate_references=references,
            )
        )

    return rows