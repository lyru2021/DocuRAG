"""验证检索评估数据结构和实验配置约束。"""

import pytest
from pydantic import ValidationError

from app.evaluation.schemas import (
    ChunkExperimentConfig,
    EvaluationQuestion,
    EvidenceSpan,
)


def test_evidence_span_valid():
    """有效的原文证据区间能够通过验证。"""

    span = EvidenceSpan(
        document_id=1,
        start_char=20,
        end_char=60,
    )

    assert span.end_char - span.start_char == 40


def test_evidence_span_rejects_invalid_range():
    """结束位置不得早于或等于起始位置。"""

    with pytest.raises(ValidationError):
        EvidenceSpan(
            document_id=1,
            start_char=50,
            end_char=20,
        )


def test_evaluation_question_requires_evidence():
    """评估问题必须包含至少一处标准证据。"""

    with pytest.raises(ValidationError):
        EvaluationQuestion(
            question_id="q001",
            query="失超保护",
            evidence=[],
        )


def test_experiment_config_valid():
    """300 字符切分配置应具备独立实验身份。"""

    config = ChunkExperimentConfig(
        experiment_id="chunk300_overlap50",
        chunk_size=300,
        overlap=50,
        document_ids=[1, 2],
    )

    assert config.chunk_size == 300


def test_experiment_config_rejects_invalid_overlap():
    """重叠字符数必须小于 Chunk 大小。"""

    with pytest.raises(ValidationError):
        ChunkExperimentConfig(
            experiment_id="invalid",
            chunk_size=300,
            overlap=300,
            document_ids=[1],
        )


def test_experiment_config_rejects_duplicate_documents():
    """实验文档集合不允许重复 ID。"""

    with pytest.raises(ValidationError):
        ChunkExperimentConfig(
            experiment_id="invalid",
            chunk_size=500,
            overlap=50,
            document_ids=[1, 1],
        )
