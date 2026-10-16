"""文档元数据 CRUD API 测试。"""

from sqlalchemy import select

from app.models.document import Chunk


def test_create_document(client):
    response = client.post(
        "/documents",
        json={
            "title": "PostgreSQL Guide",
            "filename": "postgres.pdf",
        },
    )

    assert response.status_code == 201

    data = response.json()
    assert isinstance(data["id"], int)
    assert data["title"] == "PostgreSQL Guide"
    assert data["filename"] == "postgres.pdf"
    assert data["created_at"]


def test_list_documents(client):
    created = client.post(
        "/documents",
        json={
            "title": "List Test",
            "filename": "list.pdf",
        },
    ).json()

    response = client.get("/documents")

    assert response.status_code == 200

    ids = [item["id"] for item in response.json()]
    assert created["id"] in ids


def test_get_document(client):
    created = client.post(
        "/documents",
        json={
            "title": "Get Test",
            "filename": "get.pdf",
        },
    ).json()

    response = client.get(
        f"/documents/{created['id']}"
    )

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_delete_document(client):
    created = client.post(
        "/documents",
        json={
            "title": "Delete Test",
            "filename": "delete.pdf",
        },
    ).json()

    document_id = created["id"]

    response = client.delete(
        f"/documents/{document_id}"
    )

    assert response.status_code == 204
    assert response.content == b""

    response = client.get(
        f"/documents/{document_id}"
    )

    assert response.status_code == 404


def test_invalid_document(client):
    response = client.post(
        "/documents",
        json={
            "title": "Invalid",
            "filename": "invalid.pdf",
            "admin": True,
        },
    )

    assert response.status_code == 422


def test_document_not_found(client):
    response = client.get("/documents/99999999")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Document not found"
    }


def test_delete_nonexistent_document(client):
    response = client.delete(
        "/documents/99999999"
    )

    assert response.status_code == 404


def test_delete_document_cascades_chunks(
    client,
    db_session,
):
    # Step 1: Create a document through the API.
    response = client.post(
        "/documents",
        json={
            "title": "Cascade Test",
            "filename": "cascade.pdf",
        },
    )

    assert response.status_code == 201
    document_id = response.json()["id"]

    # Step 2: Insert two chunks using SQLAlchemy.
    chunks = [
        Chunk(
            document_id=document_id,
            chunk_index=0,
            content="First chunk",
        ),
        Chunk(
            document_id=document_id,
            chunk_index=1,
            content="Second chunk",
        ),
    ]

    db_session.add_all(chunks)
    db_session.commit()

    # Step 3: Confirm two chunks exist.
    stmt = select(Chunk).where(
        Chunk.document_id == document_id
    )

    db_session.expire_all()

    before = db_session.scalars(stmt).all()
    assert len(before) == 2

    # Step 4: Delete document through API.
    response = client.delete(
        f"/documents/{document_id}"
    )

    assert response.status_code == 204

    # Step 5: Confirm chunks have been deleted.
    db_session.expire_all()

    after = db_session.scalars(stmt).all()
    assert len(after) == 0
