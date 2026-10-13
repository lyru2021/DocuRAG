from app.models.document import Document
from app.services.chunk_repository import ChunkRepository


def test_save_and_read_chunks(db_session):
    document = Document(
        title="Chunk Test",
        filename="chunk.txt",
        extracted_text="A" * 620,
        parse_status="parsed",
    )

    db_session.add(document)
    db_session.flush()

    repository = ChunkRepository(db_session)

    saved = repository.replace_document_chunks(
        document_id=document.id,
        chunk_size=300,
        overlap=50,
    )

    assert len(saved) == 3

    loaded = repository.list_document_chunks(document.id)

    assert len(loaded) == 3

    assert [
        (chunk.start_char, chunk.end_char)
        for chunk in loaded
    ] == [
        (0, 300),
        (250, 550),
        (500, 620),
    ]

    for chunk in loaded:
        assert (
            document.extracted_text[
                chunk.start_char:chunk.end_char
            ]
            == chunk.content
        )


def test_rechunk_replaces_old_chunks(db_session):
    document = Document(
        title="Rechunk Test",
        filename="rechunk.txt",
        extracted_text="B" * 1000,
        parse_status="parsed",
    )

    db_session.add(document)
    db_session.flush()

    repository = ChunkRepository(db_session)

    first = repository.replace_document_chunks(
        document.id,
        chunk_size=300,
        overlap=50,
    )

    assert len(first) == 4

    second = repository.replace_document_chunks(
        document.id,
        chunk_size=500,
        overlap=50,
    )

    assert len(second) == 3

    loaded = repository.list_document_chunks(document.id)

    assert len(loaded) == 3
    assert all(len(chunk.content) <= 500 for chunk in loaded)
