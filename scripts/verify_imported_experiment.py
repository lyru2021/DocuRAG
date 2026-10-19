"""逐条验证实验数据库 Chunk 与原始 JSON 快照完全一致。"""

import json
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.retrieval_experiment_chunk import (
    RetrievalExperimentChunk,
)


SNAPSHOT_PATH = Path(
    "evaluation/snapshots/chunk500_overlap50.json"
)

FIELDS = (
    "chunk_index",
    "content",
    "start_char",
    "end_char",
    "page_start",
    "page_end",
)


def main() -> None:
    """逐篇、逐块对比 PostgreSQL 中的实验数据。"""

    snapshot = json.loads(
        SNAPSHOT_PATH.read_text(encoding="utf-8")
    )

    experiment_id = snapshot["experiment_id"]

    engine = create_engine(
        get_settings().DATABASE_URL,
        pool_pre_ping=True,
    )

    try:
        if engine.url.database != "docurag_dev":
            raise RuntimeError(
                "Expected docurag_dev"
            )

        checked = 0
        mismatches = []

        with Session(engine) as db:
            for paper in snapshot["papers"]:
                document_id = paper["document_id"]

                actual_chunks = db.scalars(
                    select(RetrievalExperimentChunk)
                    .where(
                        RetrievalExperimentChunk.experiment_id
                        == experiment_id,
                        RetrievalExperimentChunk.document_id
                        == document_id,
                    )
                    .order_by(
                        RetrievalExperimentChunk.chunk_index
                    )
                ).all()

                expected_chunks = paper["chunks"]

                if len(actual_chunks) != len(expected_chunks):
                    mismatches.append(
                        f"Document {document_id}: count mismatch"
                    )
                    continue

                for actual, expected in zip(
                    actual_chunks,
                    expected_chunks,
                ):
                    checked += 1

                    for field in FIELDS:
                        if getattr(actual, field) != expected[field]:
                            mismatches.append(
                                f"Document {document_id}, "
                                f"Chunk {expected['chunk_index']}: "
                                f"{field} mismatch"
                            )

            # 防止实验中混入快照之外的文档。
            all_experiment_rows = db.scalars(
                select(RetrievalExperimentChunk).where(
                    RetrievalExperimentChunk.experiment_id
                    == experiment_id
                )
            ).all()

            actual_document_ids = {
                row.document_id
                for row in all_experiment_rows
            }

            if actual_document_ids != set(snapshot["document_ids"]):
                mismatches.append(
                    "Experiment document set mismatch"
                )

            if len(all_experiment_rows) != snapshot["total_chunks"]:
                mismatches.append(
                    "Experiment total chunk count mismatch"
                )

        print("Database:", engine.url.database)
        print("Experiment:", experiment_id)
        print("Chunks checked:", checked)
        print("Mismatches:", len(mismatches))

        for mismatch in mismatches[:20]:
            print("-", mismatch)

        if mismatches:
            raise SystemExit("Verification failed.")

        print("Verification passed.")

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
