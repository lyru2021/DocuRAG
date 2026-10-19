"""逐条核验 PostgreSQL Chunk 与独立 JSON 快照的一致性。"""

import json
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.document import Chunk


def main() -> None:
    """比较数据库中全部实验 Chunk 与快照字段。"""

    path = Path(
        "evaluation/snapshots/chunk300_overlap50.json"
    )

    snapshot = json.loads(
        path.read_text(encoding="utf-8")
    )

    engine = create_engine(
        get_settings().DATABASE_URL,
        pool_pre_ping=True,
    )

    try:
        if engine.url.database != "docurag_dev":
            raise RuntimeError(
                "Expected docurag_dev for snapshot verification"
            )

        mismatches = []
        checked = 0

        with Session(engine) as db:
            for paper in snapshot["papers"]:
                document_id = paper["document_id"]

                database_chunks = db.scalars(
                    select(Chunk)
                    .where(Chunk.document_id == document_id)
                    .order_by(Chunk.chunk_index)
                ).all()

                snapshot_chunks = paper["chunks"]

                if len(database_chunks) != len(snapshot_chunks):
                    mismatches.append(
                        f"Document {document_id}: "
                        f"count {len(database_chunks)} != "
                        f"{len(snapshot_chunks)}"
                    )
                    continue

                for actual, expected in zip(
                    database_chunks,
                    snapshot_chunks,
                ):
                    checked += 1

                    fields = (
                        "chunk_index",
                        "content",
                        "start_char",
                        "end_char",
                        "page_start",
                        "page_end",
                    )

                    for field in fields:
                        if getattr(actual, field) != expected[field]:
                            mismatches.append(
                                f"Document {document_id}, "
                                f"Chunk {expected['chunk_index']}: "
                                f"{field} mismatch"
                            )

        print("Database:", engine.url.database)
        print("Snapshot:", snapshot["experiment_id"])
        print("Chunks checked:", checked)
        print("Mismatches:", len(mismatches))

        for item in mismatches[:20]:
            print("-", item)

        if mismatches:
            raise SystemExit(
                "Verification failed: database differs from snapshot"
            )

        print("Verification passed.")

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
