import fitz
from sqlalchemy import func, select

from app.services.chunk_repository import ChunkRepository
from app.models.document import Document, DocumentPage


def upload_file(client, filename, content, content_type):
    return client.post(
        "/documents/upload",
        files={
            "file": (filename, content, content_type)
        },
    )


def create_pdf(text=None):
    pdf = fitz.open()
    page = pdf.new_page()

    if text:
        page.insert_text((72, 72), text)

    data = pdf.tobytes()
    pdf.close()
    return data


def test_upload_txt(client, db_session):
    response = upload_file(
        client,
        "sample.txt",
        b"Hello\n\nDocuRAG",
        "text/plain",
    )

    assert response.status_code == 201

    data = response.json()
    document = db_session.get(Document, data["id"])

    assert document is not None
    assert document.filename == "sample.txt"
    assert document.media_type == "text/plain"
    assert document.parse_status == "parsed"
    assert document.extracted_text == "Hello\n\nDocuRAG"
    assert document.text_length == len("Hello\n\nDocuRAG")
    assert document.file_id
    assert len(document.content_hash) == 64


def test_upload_valid_pdf(client, db_session):
    response = upload_file(
        client,
        "sample.pdf",
        create_pdf("DocuRAG PDF Test"),
        "application/pdf",
    )

    assert response.status_code == 201

    document = db_session.get(
        Document,
        response.json()["id"],
    )

    assert document is not None
    assert document.media_type == "application/pdf"
    assert "DocuRAG PDF Test" in document.extracted_text


def test_upload_empty_file(client):
    response = upload_file(
        client, "empty.txt", b"", "text/plain"
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_upload_unsupported_format(client):
    response = upload_file(
        client, "image.png", b"fake image", "image/png"
    )
    assert response.status_code == 415


def test_upload_invalid_utf8(client):
    response = upload_file(
        client, "bad.txt", b"\xff\xfe\xfa", "text/plain"
    )
    assert response.status_code == 422
    assert "UTF-8" in response.json()["detail"]


def test_upload_pdf_without_text(client):
    response = upload_file(
        client,
        "empty.pdf",
        create_pdf(),
        "application/pdf",
    )

    assert response.status_code == 422
    assert "No extractable text" in response.json()["detail"]


def test_upload_invalid_pdf_signature(client):
    response = upload_file(
        client,
        "fake.pdf",
        b"This is not a PDF",
        "application/pdf",
    )

    assert response.status_code == 415


def test_upload_oversized_file(client):
    response = upload_file(
        client,
        "large.txt",
        b"A" * (10 * 1024 * 1024 + 1),
        "text/plain",
    )

    assert response.status_code == 413


def test_failed_upload_does_not_create_document(
    client,
    db_session,
):
    before = db_session.scalar(
        select(func.count()).select_from(Document)
    )

    response = upload_file(
        client,
        "broken.txt",
        b"\xff\xfe\xfa",
        "text/plain",
    )

    assert response.status_code == 422

    after = db_session.scalar(
        select(func.count()).select_from(Document)
    )

    assert after == before


def test_same_filename_gets_different_file_ids(
    client,
    db_session,
):
    first = upload_file(
        client, "report.txt", b"First version", "text/plain"
    )

    second = upload_file(
        client, "report.txt", b"Second version", "text/plain"
    )

    assert first.status_code == 201
    assert second.status_code == 201

    first_data = first.json()
    second_data = second.json()

    assert first_data["id"] != second_data["id"]
    assert first_data["file_id"] != second_data["file_id"]

    first_document = db_session.get(
        Document, first_data["id"]
    )
    second_document = db_session.get(
        Document, second_data["id"]
    )

    assert first_document.filename == "report.txt"
    assert second_document.filename == "report.txt"
    assert first_document.extracted_text == "First version"
    assert second_document.extracted_text == "Second version"

def test_empty_file_does_not_create_document(
    client, db_session
):
    before = db_session.scalar(
        select(func.count()).select_from(Document)
    )

    response = upload_file(
        client, "empty.txt", b"", "text/plain"
    )

    assert response.status_code == 400

    after = db_session.scalar(
        select(func.count()).select_from(Document)
    )
    assert after == before


def test_no_text_pdf_does_not_create_document(
    client, db_session
):
    before = db_session.scalar(
        select(func.count()).select_from(Document)
    )

    response = upload_file(
        client,
        "image_only.pdf",
        create_pdf(),
        "application/pdf",
    )

    assert response.status_code == 422
    assert "No extractable text" in response.json()["detail"]

    after = db_session.scalar(
        select(func.count()).select_from(Document)
    )
    assert after == before


def test_pdf_upload_persists_page_mapping(
    client, db_session
):
    pdf = fitz.open()

    for text in ["Alpha first page", "Bravo second page"]:
        page = pdf.new_page()
        page.insert_text((72, 72), text)

    content = pdf.tobytes()
    pdf.close()

    response = upload_file(
        client,
        "two_pages.pdf",
        content,
        "application/pdf",
    )

    assert response.status_code == 201
    document_id = response.json()["id"]

    document = db_session.get(Document, document_id)

    pages = list(
        db_session.scalars(
            select(DocumentPage)
            .where(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_number)
        ).all()
    )

    assert len(pages) == 2
    assert [p.page_number for p in pages] == [1, 2]

    for page in pages:
        assert (
            document.extracted_text[
                page.start_char:page.end_char
            ]
            == page.content
        )


def test_cross_page_chunk_mapping(client, db_session):
    pdf = fitz.open()

    for text in [
        "A" * 120,
        "B" * 120,
    ]:
        page = pdf.new_page()
        page.insert_text((72, 72), text)

    content = pdf.tobytes()
    pdf.close()

    response = upload_file(
        client,
        "cross_page.pdf",
        content,
        "application/pdf",
    )

    assert response.status_code == 201
    document_id = response.json()["id"]

    repository = ChunkRepository(db_session)

    repository.replace_document_chunks(
        document_id,
        chunk_size=150,
        overlap=20,
    )

    chunks = repository.list_document_chunks(document_id)

    assert any(
        chunk.page_start == 1
        and chunk.page_end == 2
        for chunk in chunks
    )
