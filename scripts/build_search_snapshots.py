"""从开发数据库导出 300/500 字符的独立检索实验快照。"""

import argparse
import json
from pathlib import Path

from app.db.session import SessionLocal
from app.evaluation.schemas import ChunkExperimentConfig
from app.evaluation.snapshot_builder import SnapshotBuilder


def main() -> None:
    """生成两组实验快照并输出实际 Chunk 数量。"""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--document-ids",
        type=int,
        nargs="+",
        required=True,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation/snapshots"),
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        builder = SnapshotBuilder(db)

        for size in (300, 500):
            config = ChunkExperimentConfig(
                experiment_id=f"chunk{size}_overlap50",
                chunk_size=size,
                overlap=50,
                document_ids=args.document_ids,
            )

            snapshot = builder.build(config)
            output = (
                args.output_dir
                / f"{config.experiment_id}.json"
            )

            if output.exists():
                raise FileExistsError(
                    f"Snapshot already exists: {output}"
                )

            builder.save(snapshot, output)

            print(
                json.dumps(
                    {
                        "experiment_id": config.experiment_id,
                        "file": str(output),
                        "total_chunks": snapshot["total_chunks"],
                        "documents": [
                            {
                                "document_id": paper["document_id"],
                                "text_sha256": paper["text_sha256"],
                                "chunk_count": paper["chunk_count"],
                            }
                            for paper in snapshot["papers"]
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )


if __name__ == "__main__":
    main()