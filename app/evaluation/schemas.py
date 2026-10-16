"""定义检索评估问题、证据标注及切分实验配置。"""

from pydantic import BaseModel, Field, model_validator


class EvidenceSpan(BaseModel):
    """使用原文半开字符区间定位标准证据。"""

    document_id: int = Field(gt=0)
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self):
        if self.end_char <= self.start_char:
            raise ValueError("end_char must exceed start_char")
        return self


class EvaluationQuestion(BaseModel):
    """保存问题及人工标注的真实证据。"""

    question_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    evidence: list[EvidenceSpan] = Field(min_length=1)


class ChunkExperimentConfig(BaseModel):
    """标识可独立重建的 Chunk 切分实验。"""

    experiment_id: str = Field(min_length=1)
    chunk_size: int = Field(gt=0)
    overlap: int = Field(ge=0)
    document_ids: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_overlap(self):
        if self.overlap >= self.chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")

        if len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError("document_ids must be unique")

        return self
