"""识别论文 Chunk 中与方法、实验条件和结论相关的候选证据。"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agent.evidence_matrix import EvidenceReference
from app.agent.research_state import EvidenceItem


ResearchField = Literal[
    "method",
    "experimental_conditions",
    "conclusion",
]


# 只用于筛选候选证据，不能据此确认研究结论。
FIELD_PATTERNS: dict[ResearchField, tuple[str, ...]] = {
    "method": (
        r"\b(?:method|methods|architecture|framework|model|models)\b",
        r"\b(?:transformer|cnn|lstm|wav2vec|hubert|whisper)\b",
    ),
    "experimental_conditions": (
        r"\b(?:dataset|datasets|benchmark|training|test set)\b",
        r"\b(?:evaluation|experiment|experiments|metrics)\b",
    ),
    "conclusion": (
        r"\b(?:results|findings|conclusion|conclusions)\b",
        r"\b(?:outperform|outperforms|improve|improves)\b",
        r"\b(?:achieved|demonstrate|demonstrates)\b",
    ),
}


class FieldEvidenceCandidate(BaseModel):
    """记录与某个研究字段有关、但尚未语义核验的原文。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    field: ResearchField
    reference: EvidenceReference
    content: str = Field(min_length=1)
    matched_patterns: list[str] = Field(min_length=1)


def classify_evidence_fields(
    evidence: list[EvidenceItem],
    *,
    max_candidates_per_field: int = 5,
) -> dict[ResearchField, list[FieldEvidenceCandidate]]:
    """按研究字段筛选候选 Chunk，不生成或推断事实。"""

    if max_candidates_per_field < 1:
        raise ValueError("max_candidates_per_field must be positive")

    result: dict[
        ResearchField,
        list[FieldEvidenceCandidate],
    ] = {
        "method": [],
        "experimental_conditions": [],
        "conclusion": [],
    }

    seen: set[tuple[str, int, int]] = set()

    for item in evidence:
        reference = EvidenceReference(
            document_id=item["document_id"],
            chunk_id=item["chunk_id"],
            page_start=item["page_start"],
            page_end=item["page_end"],
        )

        content = item["content"]

        if not content.strip():
            continue

        for field, patterns in FIELD_PATTERNS.items():
            if len(result[field]) >= max_candidates_per_field:
                continue

            matches = [
                pattern
                for pattern in patterns
                if re.search(pattern, content, flags=re.IGNORECASE)
            ]

            if not matches:
                continue

            key = (
                field,
                reference.document_id,
                reference.chunk_id,
            )

            if key in seen:
                continue

            seen.add(key)

            result[field].append(
                FieldEvidenceCandidate(
                    field=field,
                    reference=reference,
                    content=content,
                    matched_patterns=matches,
                )
            )

    return result