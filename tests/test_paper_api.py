"""论文查询 API 测试。"""

from app.models.document import Chunk, Document, DocumentPage


def make_paper(db_session):
    text = (
        "1 Introduction\n"
        "This is a scientific paper.\n\n"
        "2 Methods\n"
        "The method uses PDF parsing."
    )

    document = Document(
        title="Test Paper",
        filename="test.pdf",
        parse_status="parsed",
        extracted_text=text,
    )

    db_session.add(document)
    db_session.flush()

    page = DocumentPage(
        document_id=document.id,
        page_number=1,
        content=text,
        start_char=0,
        end_char=len(text),
    )

    chunk = Chunk(
        document_id=document.id,
        chunk_index=0,
        content=text[:30],
        start_char=0,
        end_char=30,
        page_start=1,
        page_end=1,
    )

    db_session.add_all([page, chunk])
    db_session.flush()

    return document, chunk


def test_get_paper_detail(client, db_session):
    document, _ = make_paper(db_session)

    response = client.get(f"/papers/{document.id}")

    assert response.status_code == 200
    assert response.json()["filename"] == "test.pdf"


def test_get_paper_pages(client, db_session):
    document, _ = make_paper(db_session)

    response = client.get(
        f"/papers/{document.id}/pages"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["page_number"] == 1


def test_get_paper_chunks(client, db_session):
    document, _ = make_paper(db_session)

    response = client.get(
        f"/papers/{document.id}/chunks"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["page_start"] == 1


def test_get_chunk_evidence(client, db_session):
    document, chunk = make_paper(db_session)

    response = client.get(
        f"/papers/{document.id}/evidence/{chunk.id}"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["verified"] is True
    assert data["quote"] == chunk.content


def test_missing_paper_returns_404(client):
    response = client.get("/papers/999999999")
    assert response.status_code == 404


def test_wrong_document_chunk_pair_returns_404(
    client, db_session
):
    first_document, _ = make_paper(db_session)
    second_document, second_chunk = make_paper(db_session)

    response = client.get(
        f"/papers/{first_document.id}/"
        f"evidence/{second_chunk.id}"
    )

    assert response.status_code == 404
