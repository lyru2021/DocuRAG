"""将经过完整性校验的实验快照导入独立 PostgreSQL 表。"""

import hashlib
import json
from pathlib import Path

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.document import Document
from app.models.retrieval_experiment_chunk import (
    RetrievalExperimentChunk,
)


SNAPSHOT_PATH = Path(
    "evaluation/snapshots/chunk500_overlap50.json"
)
EXPERIMENT_ID = "chunk500_overlap50"
EXPECTED_DOCUMENT_IDS = {31, 32}
EXPECTED_CHUNKS = 209


def verify_snapshot(db: Session, snapshot: dict) -> None:
    """验证实验配置、论文原文及每个 Chunk 的内容边界。"""

    if snapshot["experiment_id"] != EXPERIMENT_ID:
        raise ValueError("Unexpected experiment ID")

    if snapshot["chunk_size"] != 500:
        raise ValueError("Unexpected chunk size")

    if snapshot["overlap"] != 50:
        raise ValueError("Unexpected overlap")

    if set(snapshot["document_ids"]) != EXPECTED_DOCUMENT_IDS:
        raise ValueError("Unexpected document IDs")

    if snapshot["total_chunks"] != EXPECTED_CHUNKS:
        raise ValueError("Unexpected chunk count")

    if len(snapshot["papers"]) != len(EXPECTED_DOCUMENT_IDS):
        raise ValueError("Unexpected paper count")

    total = 0

    for paper in snapshot["papers"]:
        document_id = paper["document_id"]

        if document_id not in EXPECTED_DOCUMENT_IDS:
            raise ValueError("Unexpected paper")

        document = db.get(Document, document_id)

        if document is None or document.extracted_text is None:
            raise ValueError(f"Missing source document {document_id}")

        original = document.extracted_text

        digest = hashlib.sha256(
            original.encode("utf-8")
        ).hexdigest()

        if digest != paper["text_sha256"]:
            raise ValueError(
                f"Source text SHA-256 mismatch: {document_id}"
            )

        if len(original) != paper["text_length"]:
            raise ValueError(
                f"Source text length mismatch: {document_id}"
            )

        chunks = paper["chunks"]

        if len(chunks) != paper["chunk_count"]:
            raise ValueError("Paper chunk count mismatch")

        for expected_index, chunk in enumerate(chunks):
            if chunk["chunk_index"] != expected_index:
                raise ValueError("Invalid chunk sequence")

            start = chunk["start_char"]
            end = chunk["end_char"]

            if not (0 <= start < end <= len(original)):
                raise ValueError("Invalid chunk offsets")

            if original[start:end] != chunk["content"]:
                raise ValueError(
                    f"Chunk content mismatch: "
                    f"{document_id}/{expected_index}"
                )

        total += len(chunks)

    if total != EXPECTED_CHUNKS:
        raise ValueError("Total chunk count mismatch")


def main() -> None:
    """执行一次受校验保护的实验快照导入。"""

    snapshot = json.loads(
        SNAPSHOT_PATH.read_text(encoding="utf-8")
    )

    engine = create_engine(
        get_settings().DATABASE_URL,
        pool_pre_ping=True,
    )

    try:
        if engine.url.database != "docurag_dev":
            raise RuntimeError(
                "Import is only allowed into docurag_dev"
            )

        with Session(engine) as db:
            # 先验证所有数据，避免部分写入。
            verify_snapshot(db, snapshot)

            existing_count = db.scalar(
                select(func.count())
                .select_from(RetrievalExperimentChunk)
                .where(
                    RetrievalExperimentChunk.experiment_id
                    == EXPERIMENT_ID
                )
            )

            if existing_count:
                raise RuntimeError(
                    f"Experiment already contains "
                    f"{existing_count} chunks; refusing overwrite"
                )

            for paper in snapshot["papers"]:
                for chunk in paper["chunks"]:
                    db.add(
                        RetrievalExperimentChunk(
                            experiment_id=EXPERIMENT_ID,
                            document_id=paper["document_id"],
                            chunk_index=chunk["chunk_index"],
                            content=chunk["content"],
                            start_char=chunk["start_char"],
                            end_char=chunk["end_char"],
                            page_start=chunk["page_start"],
                            page_end=chunk["page_end"],
                        )
                    )

            # 统一 flush 后核对数量，成功才提交事务。
            db.flush()

            inserted_count = db.scalar(
                select(func.count())
                .select_from(RetrievalExperimentChunk)
                .where(
                    RetrievalExperimentChunk.experiment_id
                    == EXPERIMENT_ID
                )
            )

            if inserted_count != EXPECTED_CHUNKS:
                raise ValueError(
                    f"Inserted {inserted_count}, expected "
                    f"{EXPECTED_CHUNKS}"
                )

            db.commit()

            print("Database:", engine.url.database)
            print("Experiment:", EXPERIMENT_ID)
            print("Inserted chunks:", inserted_count)
            print("Source SHA-256: verified")
            print("Import completed.")

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
