"""验证分块快照不修改生产数据且能够还原原文证据。"""

from app.evaluation.schemas import ChunkExperimentConfig
from app.evaluation.snapshot_builder import SnapshotBuilder
from app.models.document import Chunk, Document, DocumentPage


def test_snapshot_preserves_original_offsets(db_session):
    """快照中每个 Chunk 必须对应真实原文区间。"""

    text = "A" * 260 + "B" * 260 + "C" * 100

    document = Document(
        title="Snapshot Test",
        filename="snapshot.pdf",
        parse_status="parsed",
        extracted_text=text,
        text_length=len(text),
    )
    db_session.add(document)
    db_session.flush()

    db_session.add(
        DocumentPage(
            document_id=document.id,
            page_number=1,
            content=text,
            start_char=0,
            end_char=len(text),
        )
    )
    db_session.commit()

    config = ChunkExperimentConfig(
        experiment_id="chunk300_overlap50",
        chunk_size=300,
        overlap=50,
        document_ids=[document.id],
    )

    snapshot = SnapshotBuilder(db_session).build(config)

    assert snapshot["total_chunks"] > 0

    for chunk in snapshot["papers"][0]["chunks"]:
        assert (
            text[chunk["start_char"]:chunk["end_char"]]
            == chunk["content"]
        )
        assert chunk["page_start"] == 1


def test_snapshot_does_not_modify_production_chunks(db_session):
    """300/500 实验不得覆盖现有生产 Chunk。"""

    text = "Graph neural networks. " * 30

    document = Document(
        title="Production Isolation Test",
        filename="production.pdf",
        parse_status="parsed",
        extracted_text=text,
        text_length=len(text),
    )
    db_session.add(document)
    db_session.flush()

    db_session.add(
        DocumentPage(
            document_id=document.id,
            page_number=1,
            content=text,
            start_char=0,
            end_char=len(text),
        )
    )

    original_chunk = Chunk(
        document_id=document.id,
        chunk_index=0,
        content="Production chunk must remain unchanged",
        page_start=1,
        page_end=1,
    )
    db_session.add(original_chunk)
    db_session.commit()

    builder = SnapshotBuilder(db_session)

    for size in (300, 500):
        builder.build(
            ChunkExperimentConfig(
                experiment_id=f"chunk{size}_overlap50",
                chunk_size=size,
                overlap=50,
                document_ids=[document.id],
            )
        )

    db_session.expire_all()

    existing = db_session.get(Chunk, original_chunk.id)

    assert existing is not None
    assert existing.content == (
        "Production chunk must remain unchanged"
    )