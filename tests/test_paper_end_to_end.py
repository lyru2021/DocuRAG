import hashlib

import fitz

from app.core.config import get_settings
from app.models.document import Document, DocumentPage
from app.services.chunk_repository import ChunkRepository


def test_paper_end_to_end(
    client,
    db_session,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        get_settings(),
        "UPLOAD_DIR",
        str(tmp_path),
    )

    # 1. Generate a real 3-page text PDF.
    pdf = fitz.open()

    texts = [
        "Introduction\n" + "Research background. " * 15,
        "Methods\n" + "Experimental procedure. " * 15,
        "Results\n" + "Experimental findings. " * 15,
    ]

    for text in texts:
        page = pdf.new_page()
        page.insert_textbox(
            fitz.Rect(50, 50, 550, 750),
            text,
            fontsize=11,
        )

    pdf_bytes = pdf.tobytes()
    pdf.close()

    # 2. Upload through the real API.
    response = client.post(
        "/documents/upload",
        files={
            "file": (
                "research.pdf",
                pdf_bytes,
                "application/pdf",
            )
        },
    )

    assert response.status_code == 201

    document_id = response.json()["id"]
    document = db_session.get(Document, document_id)

    assert document is not None
    assert document.content_hash == hashlib.sha256(
        pdf_bytes
    ).hexdigest()

    # 3. Verify page extraction through the API.
    page_response = client.get(
        f"/papers/{document_id}/pages"
    )

    assert page_response.status_code == 200

    pages = page_response.json()

    assert len(pages) == 3
    assert [p["page_number"] for p in pages] == [1, 2, 3]

    for page in pages:
        assert (
            document.extracted_text[
                page["start_char"]:page["end_char"]
            ]
            == page["content"]
        )

    # 4. Generate chunks and check real page mappings.
    repository = ChunkRepository(db_session)

    chunks = repository.replace_document_chunks(
        document_id,
        chunk_size=300,
        overlap=50,
    )

    assert len(chunks) >= 3

    cross_page_chunks = [
        chunk
        for chunk in chunks
        if (
            chunk.page_start is not None
            and chunk.page_end is not None
            and chunk.page_start < chunk.page_end
        )
    ]

    assert cross_page_chunks, (
        "Expected at least one cross-page chunk"
    )
    # 5. Query evidence through the real API.
    for chunk in chunks:
        evidence_response = client.get(
            f"/papers/{document_id}/evidence/{chunk.id}"
        )

        assert evidence_response.status_code == 200

        evidence = evidence_response.json()

        assert evidence["document_id"] == document_id
        assert evidence["chunk_id"] == chunk.id
        assert evidence["quote"] == chunk.content
        assert evidence["text_verified"] is True
        assert evidence["pages_verified"] is True
        assert evidence["verified"] is True

    # 6. Verify original PDF download.
    file_response = client.get(
        f"/papers/{document_id}/file"
    )

    assert file_response.status_code == 200
    assert file_response.content == pdf_bytes

    # 7. Check page records really exist.
    stored_pages = (
        db_session.query(DocumentPage)
        .filter(DocumentPage.document_id == document_id)
        .all()
    )

    assert len(stored_pages) == 3
